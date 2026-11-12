"""Pipeline do job diário: raw → média por rota × dia da semana × hora.

O `$merge` grava o resultado numa collection persistente, substituindo o documento de
mesma chave: é a "materialized view" que o MongoDB não tem pronta.
"""
from __future__ import annotations

from datetime import date, datetime

from backend.frota.settings import JANELA_DIAS, TZ

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


def janela_no_servidor(agora: datetime) -> list[Estagio]:
    """Janela padrão e relógio calculados pelo próprio MongoDB, no fuso de São Paulo.

    É o que a Function do trigger usa: em vez de somar um offset fixo ao UTC, pede ao servidor
    o 00:00 local de hoje (`$dateTrunc` com `timezone`) e o de 180 dias antes
    (`$dateSubtract` com `timezone`), que seguem a base de fusos do servidor (horário de verão
    incluído). `agora` chega como valor; `$$NOW` só dá o relógio do servidor para o corte da
    limpeza (o mesmo papel do `hello.localTime` no Python). Roda em qualquer collection, vazia
    ou não: o `$match` impossível descarta tudo e o `$unionWith` com `$documents` (6.0+) põe
    um único documento no fluxo. `tests/test_live_trigger.py` confere contra `janela_padrao`.
    """
    hoje = {"$dateTrunc": {"date": agora, "unit": "day", "timezone": TZ}}
    return [
        Estagio("Descarta os documentos da collection: só o cálculo de datas interessa.",
                {"$match": {"$expr": False}}),
        Estagio("Põe um único documento vazio no fluxo, mesmo com a collection vazia.",
                {"$unionWith": {"pipeline": [{"$documents": [{}]}]}}),
        Estagio("Calcula no servidor, no horário de São Paulo, o 00:00 de hoje (fim da janela), "
                f"o de {JANELA_DIAS} dias antes (início), a data de referência e o relógio do servidor.",
                {"$project": {
                    "_id": 0,
                    "t": "$$NOW",
                    # truncar de novo: no dia em que o horário de verão começa, o 00:00 não
                    # existe e o dia local começa à 01:00; subtrair dias manteria essa 01:00
                    "inicio": {"$dateTrunc": {
                        "date": {"$dateSubtract": {"startDate": hoje, "unit": "day",
                                                   "amount": JANELA_DIAS, "timezone": TZ}},
                        "unit": "day", "timezone": TZ}},
                    "fim": hoje,
                    "dataRef": {"$dateToString": {"date": agora, "format": "%Y-%m-%d",
                                                  "timezone": TZ}}}}),
    ]
