"""Job diário: lê a raw da janela padrão e materializa `trecho_media_dow_hora`.

Roda uma vez por dia (e no reset). Idempotente: o `$merge` com `replace` recalcula a chave
inteira. Quem some da janela é removido por horário do servidor (`atualizadoEm` anterior
ao início do run), sem depender do relógio da máquina que chamou.
"""
from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone

from pymongo.database import Database

from .db import mascarar
from .janela import janela_padrao
from .pipelines import comentados, estagios
from .pipelines import job as pl

UTC = timezone.utc


def novo_run_id(agora: datetime) -> str:
    return f"{agora.strftime('%Y-%m-%dT%H:%M:%SZ')}-{uuid.uuid4().hex[:4]}"


def rodar_job(db: Database, data_ref: date, origem: str) -> dict:
    inicio, fim = janela_padrao(data_ref)
    inicio_run = db.command("hello")["localTime"]
    if inicio_run.tzinfo is None:
        inicio_run = inicio_run.replace(tzinfo=UTC)
    run_id = novo_run_id(inicio_run)
    p = pl.pipeline(inicio, fim, data_ref, run_id)
    t0 = time.perf_counter()
    base = {"_id": run_id, "runId": run_id, "origem": origem,
            "dataRef": data_ref.isoformat(), "iniciadoEm": inicio_run}
    try:
        lidos = db.trecho_observacoes.count_documents({"observadoEm": {"$gte": inicio, "$lt": fim}})
        db.trecho_observacoes.aggregate(estagios(p), allowDiskUse=True)
        gravados = db[pl.COLECAO].count_documents({"runId": run_id})
        removidos = db[pl.COLECAO].delete_many(
            {"atualizadoEm": {"$lt": inicio_run}}).deleted_count
        ms = round((time.perf_counter() - t0) * 1000, 1)
        db.job_runs.insert_one({**base, "status": "ok", "janelaInicio": inicio,
                                "janelaFim": fim, "lidos": lidos, "gravados": gravados,
                                "removidos": removidos, "ms": ms})
    except Exception as e:
        db.job_runs.insert_one({**base, "status": "erro",
                                "erro": mascarar(f"{type(e).__name__}: {e}"),
                                "ms": round((time.perf_counter() - t0) * 1000, 1)})
        raise
    return {"runId": run_id, "dataRef": data_ref.isoformat(), "janela": [inicio, fim],
            "lidos": lidos, "gravados": gravados, "removidos": removidos, "ms": ms,
            "pipeline": comentados(p)}
