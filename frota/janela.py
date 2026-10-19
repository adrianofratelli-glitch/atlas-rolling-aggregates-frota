"""Calendário da POV: janela semiaberta, dia local, faixas de hora e próximo job.

Funções puras: nenhuma lê o relógio. `agora` e `dataRef` chegam por parâmetro; só os
entrypoints (API, CLI) chamam `datetime.now()`. A subtração de dias é feita no calendário
local e só depois convertida para UTC, para não depender do fuso ter horário de verão.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from frota.settings import JANELA_DIAS, JOB_HORA_LOCAL, TZ

UTC = timezone.utc
_TZ = ZoneInfo(TZ)

ATALHOS = {"manha": (6, 12), "tarde": (12, 18), "noite": (18, 6)}
DOW_NOMES = {1: "segunda", 2: "terça", 3: "quarta", 4: "quinta",
             5: "sexta", 6: "sábado", 7: "domingo"}
DIAS_MAX_ULTIMOS = 200


def inicio_dia(d: date) -> datetime:
    """00:00 local do dia `d`, como instante UTC."""
    return datetime.combine(d, time(0), tzinfo=_TZ).astimezone(UTC)


def hoje_local(agora: datetime) -> date:
    return agora.astimezone(_TZ).date()


def janela_padrao(data_ref: date) -> tuple[datetime, datetime]:
    """[início do dia (dataRef − 180), início do dia dataRef) — limite superior exclusivo."""
    return inicio_dia(data_ref - timedelta(days=JANELA_DIAS)), inicio_dia(data_ref)


def horas_da_faixa(inicio: int, fim: int) -> list[int]:
    """Faixa semiaberta [inicio, fim); se cruza a meia-noite (18→6) = 18–23 e 0–5."""
    if not (0 <= inicio <= 23 and 0 <= fim <= 24):
        raise ValueError("Horas devem estar entre 0 e 24.")
    if inicio == fim:
        raise ValueError("A faixa de horas não pode ser vazia (início igual ao fim).")
    if inicio < fim:
        return list(range(inicio, fim))
    return list(range(inicio, 24)) + list(range(0, fim))


def dow_iso(d: date) -> int:
    """Mesma numeração do `$isoDayOfWeek`: 1 = segunda … 7 = domingo."""
    return d.isoweekday()


def proximo_job(agora: datetime) -> datetime:
    """Próxima ocorrência (estritamente após `agora`) do horário local do job, em UTC."""
    local = agora.astimezone(_TZ)
    hora, minuto = JOB_HORA_LOCAL
    d = local.date()
    cand = datetime.combine(d, time(hora, minuto), tzinfo=_TZ)
    if cand <= local:
        cand = datetime.combine(d + timedelta(days=1), time(hora, minuto), tzinfo=_TZ)
    return cand.astimezone(UTC)


def periodo_para_intervalo(periodo: dict, agora: datetime) -> tuple[datetime, datetime, str]:
    """Traduz o período pedido em (início, fim, "absoluto"|"relativo"); fim exclusivo."""
    tipo = periodo.get("tipo")
    hoje = hoje_local(agora)
    if tipo == "padrao":
        ini, fim = janela_padrao(hoje)
        return ini, fim, "relativo"
    if tipo == "ultimos":
        n = periodo.get("dias")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= DIAS_MAX_ULTIMOS:
            raise ValueError(f"'dias' deve ser um inteiro entre 1 e {DIAS_MAX_ULTIMOS}.")
        return inicio_dia(hoje - timedelta(days=n)), inicio_dia(hoje), "relativo"
    if tipo == "datas":
        try:
            de = date.fromisoformat(str(periodo.get("de")))
            ate = date.fromisoformat(str(periodo.get("ate")))
        except ValueError:
            raise ValueError("Datas inválidas: use o formato AAAA-MM-DD.") from None
        if de > ate:
            raise ValueError("A data inicial não pode ser posterior à final.")
        return inicio_dia(de), inicio_dia(ate + timedelta(days=1)), "absoluto"
    raise ValueError("Tipo de período inválido: use 'padrao', 'datas' ou 'ultimos'.")
