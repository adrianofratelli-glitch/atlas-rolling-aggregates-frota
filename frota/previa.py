"""Prévia do próximo job diário, só leitura: o que entra e o que sai da janela.

Nada aqui escreve: são `count_documents` e um `$group` sobre a raw. `agora` por parâmetro.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from pymongo.database import Database

from frota.janela import inicio_dia, hoje_local, proximo_job
from frota.pipelines import job as job_pipe
from frota.pipelines.job import CHAVE, COLECAO
from frota.settings import JANELA_DIAS

RAW = "trecho_observacoes"


def _chaves_na_raw(db: Database, ini: datetime, fim: datetime, data_ref) -> set[tuple]:
    """Chaves (rota × dow × hora) com observação na janela, derivando dow/hora com o `$set` do job."""
    set_job = job_pipe.pipeline(ini, fim, data_ref, "previa")[1].estagio
    pipe = [{"$match": {"observadoEm": {"$gte": ini, "$lt": fim}}}, set_job,
            {"$group": {"_id": {c: f"${c}" for c in CHAVE}}}]
    return {tuple(d["_id"][c] for c in CHAVE) for d in db[RAW].aggregate(pipe)}


def proximo(db: Database, agora: datetime) -> dict:
    quando = proximo_job(agora)
    data_ref = hoje_local(quando)  # o job de amanhã fecha o dia anterior
    entra_dia = data_ref - timedelta(days=1)
    sai_dia = data_ref - timedelta(days=JANELA_DIAS + 1)

    def contar(d):
        return db[RAW].count_documents({"observadoEm": {"$gte": inicio_dia(d), "$lt": inicio_dia(d + timedelta(days=1))}})

    ini, fim = inicio_dia(data_ref - timedelta(days=JANELA_DIAS)), inicio_dia(data_ref)
    com_dado = _chaves_na_raw(db, ini, fim, data_ref)
    base = {tuple(d["_id"][c] for c in CHAVE)
            for d in db[COLECAO].aggregate([{"$group": {"_id": {c: f"${c}" for c in CHAVE}}}])}
    return {"quando": quando, "dataRef": data_ref.isoformat(),
            "entra": {"dia": entra_dia.isoformat(), "observacoes": contar(entra_dia)},
            "sai": {"dia": sai_dia.isoformat(), "observacoes": contar(sai_dia)},
            "chavesQueSomem": len(base - com_dado)}
