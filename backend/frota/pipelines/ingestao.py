"""Pipeline da ingestão simulada: fila `ingestao_simulada` → raw `trecho_observacoes`.

Simula a chegada de dados novos: a cada hora, o que já "aconteceu" (observadoEm < agora)
sai da fila e entra na raw. O `$merge` pelo índice único (viagemId, seq) evita duplicar.
"""
from __future__ import annotations

from datetime import datetime

from . import Estagio

ORIGEM = "ingestao_simulada"
DESTINO = "trecho_observacoes"
CHAVE = ["viagemId", "seq"]


def filtro_pendentes(agora: datetime) -> dict:
    """O que já "aconteceu" e pode sair da fila (usado também pela Function do trigger)."""
    return {"observadoEm": {"$lt": agora}}


def pipeline(agora: datetime, ids: list | None = None) -> list[Estagio]:
    """Com `ids`, move exatamente esses documentos (evita perder os que chegam durante a execução)."""
    if ids is None:
        match = Estagio("Pega da fila só as observações cujo horário já passou.",
                        {"$match": filtro_pendentes(agora)})
    else:
        match = Estagio("Pega da fila só as observações já escolhidas (as de horário já passado).",
                        {"$match": {"_id": {"$in": ids}}})
    return [
        match,
        Estagio("Tira o _id para que cada documento ganhe um novo na collection de destino.",
                {"$project": {"_id": 0}}),
        Estagio("Grava na collection de observações; se a mesma viagem e trecho já estiverem lá, "
                "o documento é substituído (não duplica).",
                {"$merge": {"into": DESTINO, "on": CHAVE,
                            "whenMatched": "replace", "whenNotMatched": "insert"}}),
    ]
