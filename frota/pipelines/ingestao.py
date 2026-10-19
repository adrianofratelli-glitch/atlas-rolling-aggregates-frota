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


def pipeline(agora: datetime) -> list[Estagio]:
    return [
        Estagio("Pega da fila só as observações cujo horário já passou.",
                {"$match": {"observadoEm": {"$lt": agora}}}),
        Estagio("Tira o _id para que cada documento ganhe um novo na collection de destino.",
                {"$project": {"_id": 0}}),
        Estagio("Grava na collection de observações; se a mesma viagem e trecho já estiverem lá, "
                "o documento é substituído (não duplica).",
                {"$merge": {"into": DESTINO, "on": CHAVE,
                            "whenMatched": "replace", "whenNotMatched": "insert"}}),
    ]
