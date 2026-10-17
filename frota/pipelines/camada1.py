"""Camada 1 — raw (`trecho_observacoes`) → buckets diários por hora (Bucket Pattern)."""
from __future__ import annotations

from datetime import datetime

from . import Estagio
from .expressoes import expr_dow, expr_turno, set_hora_dow_civil

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


COLECAO_TURNO = "trecho_bucket_turno"
CHAVE_BUCKET_TURNO = ["origem", "destino", "tipoVeiculo", "dataLocal", "turno", "dow"]


def pipeline_turno(intervalos: list[tuple[datetime, datetime]], run_id: str,
                   cfg: dict) -> list[Estagio]:
    """Grão de turno: até 4 buckets por dia e trecho/veículo (M, T, N, N da madrugada).

    Turno e dow são calculados aqui, com a config vigente: mudar turnos ou regra da noite
    exige reprocessar a camada 1 (o job detecta e refaz a janela inteira).
    """
    tz = cfg["timezone"]
    return [
        Estagio(
            "Só os dias a reprocessar (dia local civil). Limites semiabertos já no fuso local; "
            "usa o índice { observadoEm: 1 }.",
            {"$match": filtro_intervalos(intervalos)},
        ),
        Estagio("Hora e dia da semana locais por observação.", set_hora_dow_civil(tz)),
        Estagio(
            f"Turno (config v{cfg['versao']}) e dow pela regraNoite = {cfg['regraNoite']}: "
            "gravados no bucket.",
            {"$set": {"turno": expr_turno(cfg["turnos"]), "dow": expr_dow(cfg)}},
        ),
        Estagio(
            "Grão: trecho × tipo × dia local civil × turno × dow. O dow fica na chave porque "
            "com dia_operacional a madrugada do dia civil pertence ao dow anterior; assim "
            "cada dia civil continua sendo reprocessado sozinho.",
            {"$group": {
                "_id": {"origem": "$origem", "destino": "$destino",
                        "tipoVeiculo": "$tipoVeiculo",
                        "dataLocal": {"$dateTrunc": {"date": "$observadoEm", "unit": "day",
                                                     "timezone": tz}},
                        "turno": "$turno", "dow": "$dow"},
                "somaMin": {"$sum": "$tempoMin"}, "somaKm": {"$sum": "$distanciaKm"},
                "n": {"$sum": 1},
                "minMin": {"$min": "$tempoMin"}, "maxMin": {"$max": "$tempoMin"},
            }},
        ),
        Estagio(
            "Achata a chave; somas a 6 casas (determinístico); versão da config gravada.",
            {"$project": {
                "_id": 0,
                "origem": "$_id.origem", "destino": "$_id.destino",
                "tipoVeiculo": "$_id.tipoVeiculo", "dataLocal": "$_id.dataLocal",
                "turno": "$_id.turno", "dow": "$_id.dow",
                "somaMin": {"$round": ["$somaMin", PRECISAO]},
                "somaKm": {"$round": ["$somaKm", PRECISAO]},
                "n": 1, "minMin": 1, "maxMin": 1,
                "configVersao": {"$literal": cfg["versao"]},
                "atualizadoEm": "$$NOW", "runId": {"$literal": run_id},
            }},
        ),
        Estagio(
            "Upsert pela chave única do bucket de turno; replace = idempotente.",
            {"$merge": {"into": COLECAO_TURNO, "on": CHAVE_BUCKET_TURNO,
                        "whenMatched": "replace", "whenNotMatched": "insert"}},
        ),
    ]
