from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from frota import janela as j

UTC = timezone.utc


def dt(*a):
    return datetime(*a, tzinfo=UTC)


def test_janela_exclui_hoje():
    assert j.janela_padrao(date(2026, 10, 22)) == (dt(2026, 4, 25, 3), dt(2026, 10, 22, 3))


def test_janela_com_horario_de_verao_historico():
    assert j.janela_padrao(date(2018, 11, 10)) == (dt(2018, 5, 14, 3), dt(2018, 11, 10, 2))


def test_faixa_manha_e_noite():
    assert j.horas_da_faixa(6, 12) == [6, 7, 8, 9, 10, 11]
    assert j.horas_da_faixa(18, 6) == [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5]
    assert j.ATALHOS["noite"] == (18, 6)


def test_faixa_vazia_erro():
    with pytest.raises(ValueError):
        j.horas_da_faixa(6, 6)


def test_dow_iso():
    assert j.dow_iso(date(2026, 10, 23)) == 5
    assert j.DOW_NOMES[1] == "segunda" and j.DOW_NOMES[7] == "domingo"


def test_proximo_job():
    assert j.proximo_job(dt(2026, 10, 19, 13)) == dt(2026, 10, 20, 6, 10)
    assert j.proximo_job(dt(2026, 10, 19, 5)) == dt(2026, 10, 19, 6, 10)
    assert j.proximo_job(dt(2026, 10, 19, 6, 10)) == dt(2026, 10, 20, 6, 10)


def test_periodo_padrao_e_ultimos():
    agora = dt(2026, 10, 19, 13)
    assert j.periodo_para_intervalo({"tipo": "padrao"}, agora) == (
        dt(2026, 4, 22, 3), dt(2026, 10, 19, 3), "relativo")
    assert j.periodo_para_intervalo({"tipo": "ultimos", "dias": 30}, agora) == (
        dt(2026, 9, 19, 3), dt(2026, 10, 19, 3), "relativo")


def test_periodo_datas_inclusivo():
    ini, fim, kind = j.periodo_para_intervalo(
        {"tipo": "datas", "de": "2026-03-01", "ate": "2026-03-31"}, dt(2026, 10, 19))
    assert (ini, fim, kind) == (dt(2026, 3, 1, 3), dt(2026, 4, 1, 3), "absoluto")


@pytest.mark.parametrize("p", [
    {"tipo": "datas", "de": "2026-03-31", "ate": "2026-03-01"},
    {"tipo": "ultimos", "dias": 0},
    {"tipo": "ultimos", "dias": 201},
    {"tipo": "outro"},
    {"tipo": "datas", "de": "x", "ate": "y"},
])
def test_periodo_invalido(p):
    with pytest.raises(ValueError):
        j.periodo_para_intervalo(p, dt(2026, 10, 19))


def test_sao_paulo_sem_dst_proximo_ano():
    tz = ZoneInfo("America/Sao_Paulo")
    d0 = date(2026, 10, 19)
    for i in range(366):
        d = d0 + timedelta(days=i)
        off = datetime(d.year, d.month, d.day, 12, tzinfo=tz).utcoffset()
        assert off == timedelta(hours=-3), d
