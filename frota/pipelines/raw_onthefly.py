"""A mesma pergunta do fallback, calculada direto na raw (para comparação)."""
from __future__ import annotations

from datetime import datetime

from . import Estagio
from .expressoes import expr_dow, expr_turno


def pipeline(origem: str, destino: str, tipo: str, janela_inicio: datetime,
             janela_fim: datetime, cfg: dict) -> list[Estagio]:
    tz = cfg["timezone"]
    return [
        Estagio(
            "Todas as observações do trecho/veículo na janela [início, fim). Usa o índice "
            "{ origem, destino, tipoVeiculo, observadoEm }.",
            {"$match": {"origem": origem, "destino": destino, "tipoVeiculo": tipo,
                        "observadoEm": {"$gte": janela_inicio, "$lt": janela_fim}}},
        ),
        Estagio(
            "Hora e dia da semana locais de cada observação, no momento da consulta.",
            {"$set": {"hora": {"$hour": {"date": "$observadoEm", "timezone": tz}},
                      "dowCivil": {"$dayOfWeek": {"date": "$observadoEm", "timezone": tz}}}},
        ),
        Estagio(
            "Mesmas expressões de turno/dow da camada 2.",
            {"$set": {"turno": expr_turno(cfg["turnos"]), "dow": expr_dow(cfg)}},
        ),
        Estagio(
            "Mesmo grão do agregado: dow × turno.",
            {"$group": {"_id": {"dow": "$dow", "turno": "$turno"},
                        "somaMin": {"$sum": "$tempoMin"}, "somaKm": {"$sum": "$distanciaKm"},
                        "n": {"$sum": 1}}},
        ),
        Estagio(
            "Mesmo formato dos documentos de trecho_media_historica.",
            {"$project": {"_id": 0, "dow": "$_id.dow", "turno": "$_id.turno",
                          "somaMin": 1, "somaKm": 1, "n": 1}},
        ),
    ]
