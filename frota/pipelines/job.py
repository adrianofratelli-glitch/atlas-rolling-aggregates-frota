"""Pipeline do job diário: raw → média por rota × dia da semana × hora.

O `$merge` grava o resultado numa collection persistente, substituindo o documento de
mesma chave: é a "materialized view" que o MongoDB não tem pronta.
"""
from __future__ import annotations

from datetime import date, datetime

from frota.settings import TZ

from . import Estagio

COLECAO = "trecho_media_dow_hora"
CHAVE = ["origem", "destino", "tipoVeiculo", "dow", "hora"]


def pipeline(inicio: datetime, fim: datetime, data_ref: date, run_id: str) -> list[Estagio]:
    return [
        Estagio("Pega só as observações dos últimos 180 dias, sem o dia de hoje.",
                {"$match": {"observadoEm": {"$gte": inicio, "$lt": fim}}}),
        Estagio("Descobre o dia da semana (1 = segunda … 7 = domingo) e a hora, no horário de São Paulo.",
                {"$set": {"dow": {"$isoDayOfWeek": {"date": "$observadoEm", "timezone": TZ}},
                          "hora": {"$hour": {"date": "$observadoEm", "timezone": TZ}}}}),
        Estagio("Agrupa por rota, tipo de veículo, dia da semana e hora, guardando contagem e somas.",
                {"$group": {"_id": {c: f"${c}" for c in CHAVE},
                            "n": {"$sum": 1},
                            "somaMin": {"$sum": "$tempoMin"},
                            "somaQuadMin": {"$sum": {"$multiply": ["$tempoMin", "$tempoMin"]}},
                            "somaKm": {"$sum": "$distanciaKm"}}}),
        Estagio("Arredonda as somas, calcula as médias e carimba o resultado com a data e o número da execução.",
                {"$project": {
                    "_id": 0,
                    **{c: f"$_id.{c}" for c in CHAVE},
                    "n": 1,
                    "somaMin": {"$round": ["$somaMin", 6]},
                    "somaQuadMin": {"$round": ["$somaQuadMin", 6]},
                    "somaKm": {"$round": ["$somaKm", 6]},
                    "mediaMin": {"$divide": ["$somaMin", "$n"]},
                    "mediaKm": {"$divide": ["$somaKm", "$n"]},
                    "janelaInicio": {"$literal": inicio},
                    "janelaFim": {"$literal": fim},
                    "dataRef": {"$literal": data_ref.isoformat()},
                    "runId": {"$literal": run_id},
                    "atualizadoEm": "$$NOW"}}),
        Estagio("Grava o resultado numa collection persistente (a \"materialized view\"): "
                "se já existe um documento com a mesma chave, ele é substituído; se não, é inserido.",
                {"$merge": {"into": COLECAO, "on": CHAVE,
                            "whenMatched": "replace", "whenNotMatched": "insert"}}),
    ]
