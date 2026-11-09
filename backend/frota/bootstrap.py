"""Cria collections (com validator) e índices de forma idempotente.

Rodar duas vezes não muda nada: collection existente recebe `collMod` só quando o
validator mudou, índice existente é mantido e TTL divergente é ajustado via `collMod`.
"""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.database import Database

from . import settings
from .schemas import VALIDATORS

DIA_S = 86400


def indices() -> dict[str, list[IndexModel]]:
    """Índices por collection. Justificativa de cada um no README."""
    return {
        "trechos": [IndexModel([("origem", ASCENDING), ("destino", ASCENDING)],
                               unique=True, name="origem_1_destino_1")],
        "trecho_observacoes": [
            # identidade da observação: reenvio do mesmo trecho da mesma viagem é ignorado
            IndexModel([("viagemId", ASCENDING), ("seq", ASCENDING)], unique=True,
                       name="viagemId_1_seq_1"),
            # cenários fora da janela padrão agregam na raw por chave + período
            IndexModel([("origem", ASCENDING), ("destino", ASCENDING),
                        ("tipoVeiculo", ASCENDING), ("observadoEm", ASCENDING)],
                       name="origem_1_destino_1_tipoVeiculo_1_observadoEm_1"),
            # range do job diário + retenção
            IndexModel([("observadoEm", ASCENDING)], name="observadoEm_1_ttl",
                       expireAfterSeconds=settings.TTL_RAW_DIAS * DIA_S),
        ],
        "ingestao_simulada": [
            IndexModel([("viagemId", ASCENDING), ("seq", ASCENDING)], unique=True,
                       name="viagemId_1_seq_1"),
            IndexModel([("observadoEm", ASCENDING)], name="observadoEm_1"),
        ],
        "trecho_media_dow_hora": [
            # exigido pelo `on` do $merge e serve à leitura por chave
            IndexModel([("origem", ASCENDING), ("destino", ASCENDING),
                        ("tipoVeiculo", ASCENDING), ("dow", ASCENDING),
                        ("hora", ASCENDING)], unique=True, name="chave_unica"),
        ],
        "consultas_salvas": [IndexModel([("expiraEm", ASCENDING)], name="expiraEm_ttl",
                                        expireAfterSeconds=0)],
        "job_runs": [IndexModel([("iniciadoEm", DESCENDING)], name="iniciadoEm_-1")],
    }


def bootstrap(db: Database) -> dict:
    existentes = {c["name"]: c.get("options", {}) for c in
                  db.command("listCollections", filter={"type": "collection"})["cursor"]["firstBatch"]}
    for nome, validator in VALIDATORS.items():
        opts = {"validator": validator, "validationLevel": "strict",
                "validationAction": "error"}
        atual = existentes.get(nome)
        if atual is None:
            db.create_collection(nome, **opts)
        elif any(atual.get(k) != v for k, v in opts.items()):
            db.command("collMod", nome, **opts)  # só quando o contrato mudou
    for nome, modelos in indices().items():
        coll = db[nome]
        atuais = {i["name"]: i for i in coll.list_indexes()}
        # índice que não está no contrato (ex.: resto de banco criado pelo desenho v1)
        previstos = {m.document["name"] for m in modelos} | {"_id_"}
        for velho in set(atuais) - previstos:
            coll.drop_index(velho)
        for m in modelos:
            doc = m.document
            atual = atuais.get(doc["name"])
            if atual and "expireAfterSeconds" in doc and \
                    atual.get("expireAfterSeconds") != doc["expireAfterSeconds"]:
                db.command("collMod", nome, index={"name": doc["name"],
                                                   "expireAfterSeconds": doc["expireAfterSeconds"]})
            elif not atual:
                coll.create_indexes([m])
    return {nome: list(db[nome].list_indexes()) for nome in VALIDATORS}
