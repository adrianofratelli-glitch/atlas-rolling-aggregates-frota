"""Camada 1 — raw (`trecho_observacoes`) → buckets diários por hora (Bucket Pattern)."""
from __future__ import annotations

from datetime import datetime

from . import Estagio

COLECAO_DESTINO = "trecho_bucket_diario"
CHAVE_BUCKET = ["origem", "destino", "tipoVeiculo", "dataLocal", "hora"]
PRECISAO = 6  # casas decimais das somas (minutos/km): resultado determinístico


def filtro_intervalos(intervalos: list[tuple[datetime, datetime]]) -> dict:
    """Filtro de `observadoEm` para um ou mais intervalos semiabertos [início, fim)."""
    faixas = [{"observadoEm": {"$gte": a, "$lt": b}} for a, b in intervalos]
    return faixas[0] if len(faixas) == 1 else {"$or": faixas}


def pipeline(intervalos: list[tuple[datetime, datetime]], run_id: str, tz: str) -> list[Estagio]:
    return [
        Estagio(
            "Só os dias a reprocessar (D-1…D-k ∪ dias com atraso detectado). Limites "
            "semiabertos, já calculados no fuso local: usa o índice { observadoEm: 1 }.",
            {"$match": filtro_intervalos(intervalos)},
        ),
        Estagio(
            "Grão do bucket: trecho × tipo de veículo × dia local × hora local. "
            "$dateTrunc/$hour com timezone — nunca o dia/hora UTC. Guarda soma e contagem "
            "(componíveis), não média.",
            {"$group": {
                "_id": {
                    "origem": "$origem", "destino": "$destino", "tipoVeiculo": "$tipoVeiculo",
                    "dataLocal": {"$dateTrunc": {"date": "$observadoEm", "unit": "day",
                                                 "timezone": tz}},
                    "hora": {"$hour": {"date": "$observadoEm", "timezone": tz}},
                },
                "somaMin": {"$sum": "$tempoMin"}, "somaKm": {"$sum": "$distanciaKm"},
                "n": {"$sum": 1},
                "minMin": {"$min": "$tempoMin"}, "maxMin": {"$max": "$tempoMin"},
            }},
        ),
        Estagio(
            "Achata a chave e deriva dowCivil (1=domingo … 7=sábado) do dia local. Somas "
            "arredondadas a 6 casas: $sum de doubles depende da ordem de leitura, e sem isso "
            "dois runs sobre a mesma raw diferem em ~1e-14. $$NOW só para auditoria.",
            {"$project": {
                "_id": 0,
                "origem": "$_id.origem", "destino": "$_id.destino",
                "tipoVeiculo": "$_id.tipoVeiculo",
                "dataLocal": "$_id.dataLocal", "hora": "$_id.hora",
                "dowCivil": {"$dayOfWeek": {"date": "$_id.dataLocal", "timezone": tz}},
                "somaMin": {"$round": ["$somaMin", PRECISAO]},
                "somaKm": {"$round": ["$somaKm", PRECISAO]},
                "n": 1, "minMin": 1, "maxMin": 1,
                "atualizadoEm": "$$NOW",
                "runId": {"$literal": run_id},
            }},
        ),
        Estagio(
            "Upsert pela chave única do bucket. whenMatched: replace recalcula o dia "
            "inteiro a partir da raw — reexecutar dá o mesmo resultado (idempotente). "
            "$inc duplicaria a cada reexecução.",
            {"$merge": {"into": COLECAO_DESTINO, "on": CHAVE_BUCKET,
                        "whenMatched": "replace", "whenNotMatched": "insert"}},
        ),
    ]
