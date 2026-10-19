"""Prévia do próximo job diário, só leitura: o que entra e o que sai da janela.

Nada aqui escreve: são `count_documents` e um `$group` sobre a raw. `agora` por parâmetro.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from pymongo.database import Database

from frota.janela import inicio_dia, hoje_local, proximo_job
from frota.pipelines.job import COLECAO
from frota.settings import JANELA_DIAS

RAW = "trecho_observacoes"
CHAVE_ROTA = ["origem", "destino", "tipoVeiculo"]


def _chaves_na_raw(db: Database, ini: datetime, fim: datetime) -> set[tuple]:
    pipe = [{"$match": {"observadoEm": {"$gte": ini, "$lt": fim}}},
            {"$group": {"_id": {c: f"${c}" for c in CHAVE_ROTA}}}]
    return {tuple(d["_id"][c] for c in CHAVE_ROTA) for d in db[RAW].aggregate(pipe)}


def proximo(db: Database, agora: datetime) -> dict:
    quando = proximo_job(agora)
    data_ref = hoje_local(quando)  # o job de amanhã fecha o dia anterior
    entra_dia = data_ref - timedelta(days=1)
    sai_dia = data_ref - timedelta(days=JANELA_DIAS + 1)

    def contar(d):
        return db[RAW].count_documents({"observadoEm": {"$gte": inicio_dia(d), "$lt": inicio_dia(d + timedelta(days=1))}})

    ini, fim = inicio_dia(data_ref - timedelta(days=JANELA_DIAS)), inicio_dia(data_ref)
    com_dado = _chaves_na_raw(db, ini, fim)
    base = {tuple(d["_id"][c] for c in CHAVE_ROTA)
            for d in db[COLECAO].aggregate([{"$group": {"_id": {c: f"${c}" for c in CHAVE_ROTA}}}])}
    return {"quando": quando, "dataRef": data_ref.isoformat(),
            "entra": {"dia": entra_dia.isoformat(), "observacoes": contar(entra_dia)},
            "sai": {"dia": sai_dia.isoformat(), "observacoes": contar(sai_dia)},
            "chavesQueSomem": len(base - com_dado)}
