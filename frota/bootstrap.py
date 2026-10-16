"""Cria collections (com validator) e índices de forma idempotente.

Rodar duas vezes não muda nada: collection existente recebe `collMod` com o validator
atual, índice existente com a mesma chave é mantido e TTLs são ajustados via `collMod`
quando a config muda.
"""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.database import Database

from . import config as config_mod
from .schemas import VALIDATORS

DIA_S = 86400


def indices(cfg: dict) -> dict[str, list[IndexModel]]:
    """Índices por collection. Justificativa de cada um no README."""
    return {
        "pontos": [IndexModel([("tipo", ASCENDING)], name="tipo_1")],
        "veiculos": [IndexModel([("baseId", ASCENDING), ("tipoVeiculo", ASCENDING)],
                                name="baseId_1_tipoVeiculo_1")],
        "trechos": [IndexModel([("origem", ASCENDING), ("destino", ASCENDING)],
                               unique=True, name="origem_1_destino_1")],
        "trecho_observacoes": [
            # range do job da camada 1 + retenção (o mesmo índice serve aos dois)
            IndexModel([("observadoEm", ASCENDING)], name="observadoEm_1_ttl",
                       expireAfterSeconds=cfg["ttlRawDias"] * DIA_S),
            # detecção de atrasados pelo watermark de ingestão
            IndexModel([("ingeridoEm", ASCENDING)], name="ingeridoEm_1"),
            # identidade da observação: reenvio do mesmo trecho da mesma viagem é ignorado
            IndexModel([("viagemId", ASCENDING), ("seq", ASCENDING)], unique=True,
                       name="viagemId_1_seq_1"),
            # consulta on-the-fly na raw (comparação da aba 2)
            IndexModel([("origem", ASCENDING), ("destino", ASCENDING),
                        ("tipoVeiculo", ASCENDING), ("observadoEm", ASCENDING)],
                       name="origem_1_destino_1_tipoVeiculo_1_observadoEm_1"),
        ],
        "trecho_bucket_diario": [
            # exigido pelo `on` do $merge da camada 1
            IndexModel([("origem", ASCENDING), ("destino", ASCENDING),
                        ("tipoVeiculo", ASCENDING), ("dataLocal", ASCENDING),
                        ("hora", ASCENDING)], unique=True, name="chave_bucket_unica"),
            # recorte da janela na camada 2 + retenção
            IndexModel([("dataLocal", ASCENDING)], name="dataLocal_1_ttl",
                       expireAfterSeconds=cfg["ttlBucketDias"] * DIA_S),
        ],
        "trecho_media_historica": [
            # serve ao `on` do $merge e à consulta de fallback (prefixo o/d/tipo)
            IndexModel([("origem", ASCENDING), ("destino", ASCENDING),
                        ("tipoVeiculo", ASCENDING), ("dow", ASCENDING),
                        ("turno", ASCENDING)], unique=True, name="chave_media_unica"),
        ],
        "ingestao_pendente": [IndexModel([("ingeridoEm", ASCENDING)], name="ingeridoEm_1"),
                              IndexModel([("viagemId", ASCENDING), ("seq", ASCENDING)],
                                         unique=True, name="viagemId_1_seq_1")],
        "job_runs": [IndexModel([("iniciadoEm", DESCENDING)], name="iniciadoEm_-1")],
        "job_locks": [IndexModel([("expiraEm", ASCENDING)], name="expiraEm_ttl",
                                 expireAfterSeconds=0)],
    }


def bootstrap(db: Database, verbose: bool = False) -> dict:
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
    cfg = config_mod.garantir(db)
    for nome, modelos in indices(cfg).items():
        coll = db[nome]
        atuais = {i["name"]: i for i in coll.list_indexes()}
        for m in modelos:
            doc = m.document
            atual = atuais.get(doc["name"])
            if atual and "expireAfterSeconds" in doc and \
                    atual.get("expireAfterSeconds") != doc["expireAfterSeconds"]:
                db.command("collMod", nome, index={"name": doc["name"],
                                                   "expireAfterSeconds": doc["expireAfterSeconds"]})
            elif not atual:
                coll.create_indexes([m])
    resumo = {nome: list(db[nome].list_indexes()) for nome in VALIDATORS}
    if verbose:
        for nome, idx in resumo.items():
            print(f"{nome}:")
            for i in idx:
                extra = []
                if i.get("unique"):
                    extra.append("unique")
                if "expireAfterSeconds" in i:
                    extra.append(f"TTL {i['expireAfterSeconds'] // DIA_S if i['expireAfterSeconds'] else 0} d"
                                 if i["expireAfterSeconds"] else "TTL expiraEm")
                print(f"  {i['name']:<48} {dict(i['key'])} {' '.join(extra)}")
    return resumo


COLECOES_DADOS = ["pontos", "tipos_veiculo", "veiculos", "trechos", "trecho_observacoes",
                  "trecho_bucket_diario", "trecho_media_historica", "job_runs", "job_locks",
                  "ingestao_pendente"]


def limpar_dados(db: Database) -> None:
    """Esvazia as collections de dados preservando validators e índices."""
    for nome in COLECOES_DADOS:
        db[nome].delete_many({})
