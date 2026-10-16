"""Calendário da POV: janela semiaberta, dia local, dow e turno.

Toda a interpretação de "dia", "hora" e "dia da semana" é feita no fuso da config.
Em Python isso existe só para (1) calcular os limites que o pipeline recebe prontos e
(2) derivar a chave da consulta de fallback a partir de um instante. Os buckets e o
agregado são calculados no servidor, com operadores que recebem `timezone`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def parse_asof(valor: str | date) -> date:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    return date.fromisoformat(str(valor))


def hoje_local(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def inicio_dia(d: date, tz: str) -> datetime:
    """00:00 local do dia `d`, como instante UTC."""
    return datetime.combine(d, time(0), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def dia_local(instante: datetime, tz: str) -> date:
    return instante.astimezone(ZoneInfo(tz)).date()


def janela(asof: str | date, cfg: dict) -> tuple[datetime, datetime]:
    """[início do dia (asOf − janelaDias), início do dia asOf) — semiaberta.

    A subtração é feita em dias de calendário local e só depois convertida para UTC,
    para não depender de o fuso ter ou não horário de verão.
    """
    d = parse_asof(asof)
    tz = cfg["timezone"]
    return inicio_dia(d - timedelta(days=cfg["janelaDias"]), tz), inicio_dia(d, tz)


def dias(inicio: date, fim_exclusivo: date) -> list[date]:
    return [inicio + timedelta(days=i) for i in range((fim_exclusivo - inicio).days)]


# ---- turnos ---------------------------------------------------------------

def turno_cruza_meia_noite(t: dict) -> bool:
    return t["inicioHora"] >= t["fimHora"]


def horas_do_turno(t: dict) -> list[int]:
    if turno_cruza_meia_noite(t):
        return list(range(t["inicioHora"], 24)) + list(range(0, t["fimHora"]))
    return list(range(t["inicioHora"], t["fimHora"]))


def validar_turnos(turnos: list[dict]) -> None:
    """Cada hora 0–23 pertence a exatamente um turno; no máximo um cruza a meia-noite."""
    cobertura: dict[int, str] = {}
    for t in turnos:
        if not (0 <= t["inicioHora"] <= 23 and 0 <= t["fimHora"] <= 24):
            raise ValueError(f"turno {t['codigo']}: horas fora de 0–24")
        for h in horas_do_turno(t):
            if h in cobertura:
                raise ValueError(f"hora {h} está em {cobertura[h]} e {t['codigo']}")
            cobertura[h] = t["codigo"]
    faltando = sorted(set(range(24)) - set(cobertura))
    if faltando:
        raise ValueError(f"horas sem turno: {faltando}")
    if sum(turno_cruza_meia_noite(t) for t in turnos) > 1:
        raise ValueError("só um turno pode cruzar a meia-noite")


def turno_da_hora(hora: int, turnos: list[dict]) -> str:
    for t in turnos:
        if hora in horas_do_turno(t):
            return t["codigo"]
    raise ValueError(f"hora {hora} sem turno")


def corte_madrugada(turnos: list[dict]) -> int:
    """Hora em que termina o turno que cruza a meia-noite (0 se nenhum cruza).

    Com `regraNoite = dia_operacional`, horas antes desse corte contam no dia anterior.
    """
    for t in turnos:
        if turno_cruza_meia_noite(t):
            return t["fimHora"]
    return 0


def dow_civil(d: date) -> int:
    """Mesma numeração do `$dayOfWeek`: 1 = domingo … 7 = sábado."""
    return d.isoweekday() % 7 + 1


def derivar_chave(instante: datetime, cfg: dict) -> dict:
    """Chave do agregado (dow, turno) para um instante, com a mesma regra do pipeline."""
    tz = cfg["timezone"]
    local = instante.astimezone(ZoneInfo(tz))
    hora = local.hour
    dia = local.date()
    dow = dow_civil(dia)
    if cfg["regraNoite"] == "dia_operacional" and hora < corte_madrugada(cfg["turnos"]):
        dow = dow_civil(dia - timedelta(days=1))
    return {"dow": dow, "turno": turno_da_hora(hora, cfg["turnos"]), "hora": hora,
            "dowCivil": dow_civil(dia), "dataLocal": dia.isoformat()}


DOW_NOMES = {1: "domingo", 2: "segunda", 3: "terça", 4: "quarta", 5: "quinta",
             6: "sexta", 7: "sábado"}
