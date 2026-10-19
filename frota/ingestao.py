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


def _selecionar(db: Database, agora: datetime) -> list:
    return [d["_id"] for d in db[pipe.ORIGEM].find({"observadoEm": {"$lt": agora}}, {"_id": 1})]


def ingerir(db: Database, agora: datetime) -> dict:
    """Escolhe os `_id`s a mover, faz o `$merge` só deles e apaga só eles da fila:
    o que chegar na fila no meio do caminho não é perdido."""
    ids = _selecionar(db, agora)
    if ids:
        list(db[pipe.ORIGEM].aggregate(estagios(pipe.pipeline(agora, ids))))
        db[pipe.ORIGEM].delete_many({"_id": {"$in": ids}})
    return {"movidos": len(ids), "restantes": db[pipe.ORIGEM].count_documents({}),
            "simuladoAte": simulado_ate(db)}
