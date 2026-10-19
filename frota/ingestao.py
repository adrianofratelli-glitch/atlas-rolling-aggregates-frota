"""Ingestão simulada: move da fila `ingestao_simulada` para a raw o que já aconteceu.

`agora` vem por parâmetro (a hora cheia do trigger ou do clique). O aggregate com `$merge`
é idempotente pelo índice único (viagemId, seq); só depois a fila é limpa.
"""
from __future__ import annotations

from datetime import datetime

from pymongo.database import Database

from frota.operadores import bloco_query
from frota.pipelines import comentados, estagios
from frota.pipelines import ingestao as pipe


def simulado_ate(db: Database) -> datetime | None:
    """Maior `observadoEm` ainda na fila (até onde a simulação tem dado)."""
    r = next(db[pipe.ORIGEM].aggregate([{"$group": {"_id": None, "m": {"$max": "$observadoEm"}}}]), None)
    return r["m"] if r else None


def bloco(agora: datetime) -> dict:
    return bloco_query(pipe.ORIGEM, comentados(pipe.pipeline(agora)), [pipe.ORIGEM], [pipe.DESTINO])


def ingerir(db: Database, agora: datetime) -> dict:
    filtro = {"observadoEm": {"$lt": agora}}
    movidos = db[pipe.ORIGEM].count_documents(filtro)
    if movidos:
        list(db[pipe.ORIGEM].aggregate(estagios(pipe.pipeline(agora))))
        db[pipe.ORIGEM].delete_many(filtro)
    return {"movidos": movidos, "restantes": db[pipe.ORIGEM].count_documents({}),
            "simuladoAte": simulado_ate(db)}
