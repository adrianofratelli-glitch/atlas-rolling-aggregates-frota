"""Consulta de fallback: hierarquia de níveis, formato da resposta e explain."""
from __future__ import annotations

from datetime import datetime

import pytest
from pymongo.errors import WriteError

from frota.consulta import fallback, onthefly
from frota.job import materializar
from frota.simulacao import agora_simulado
from tests.fixtures.dataset import ASOF, ATRASADO_D2, obs, sp

O, D, T = "BASE-001", "POSTO-0042", "BITREM"
SEXTA_20H = "2026-10-16T20:00:00-03:00"


@pytest.fixture
def mat(db):
    materializar(db, ASOF)
    return db


def test_contrato_14_4_com_min_amostras_3(mat):
    r = fallback(mat, O, D, T, SEXTA_20H, asof=ASOF, min_amostras=3)
    esperado = {
        "origem": O, "destino": D, "tipoVeiculo": T,
        "instanteLocal": "2026-10-16T20:00:00-03:00",
        "chaveSolicitada": {"dow": 6, "turno": "N"}, "nivel": "dow+turno",
        "mediaMin": 56.0, "mediaKm": 40.0, "n": 3, "minAmostras": 3, "abaixoDoMinimo": False,
        "janela": {"inicio": "2026-04-19T00:00:00-03:00",
                   "fimExclusivo": "2026-10-16T00:00:00-03:00"},
        "asOf": "2026-10-16", "docsLidos": 4,
    }
    assert {k: r[k] for k in esperado} == esperado
    assert r["configVersao"] >= 1


def test_default_min5_desce_para_turno(mat):
    """dow+turno tem n = 3 < 5 → turno N soma todos os dow: obs 1,2,3,4,6,8."""
    r = fallback(mat, O, D, T, SEXTA_20H, asof=ASOF)
    assert (r["nivel"], r["n"], r["abaixoDoMinimo"]) == ("turno", 6, False)
    assert r["mediaMin"] == pytest.approx((50 + 56 + 62 + 70 + 30 + 45) / 6)
    assert r["mediaKm"] == pytest.approx((39 + 40 + 41 + 42 + 38 + 39) / 6)


def test_nivel_geral(mat):
    """Terça 10:00 = turno M: não há M nesse trecho/veículo → geral (todos os docs)."""
    r = fallback(mat, O, D, T, "2026-10-13T10:00:00-03:00", asof=ASOF)
    assert (r["chaveSolicitada"], r["nivel"], r["n"]) == ({"dow": 3, "turno": "M"}, "geral", 6)
    assert r["mediaMin"] == pytest.approx(313 / 6)


def test_nenhum_nivel_atinge_minimo(mat):
    r = fallback(mat, O, D, T, SEXTA_20H, asof=ASOF, min_amostras=50)
    assert (r["nivel"], r["n"], r["abaixoDoMinimo"]) == ("geral", 6, True)


def test_sem_historico(mat):
    r = fallback(mat, O, "POSTO-9999", "TOCO", SEXTA_20H, asof=ASOF)
    assert (r["nivel"], r["mediaMin"], r["mediaKm"], r["n"], r["docsLidos"]) == \
        ("sem_historico", None, None, 0, 0)
    assert r["janela"]["fimExclusivo"] == "2026-10-16T00:00:00-03:00"


def test_instante_respeita_regra_noite(mat):
    """Sábado 01:00: dia_civil → dow 7; o instante usa a mesma regra do pipeline."""
    r = fallback(mat, O, D, T, "2026-10-17T01:00:00-03:00", min_amostras=1)
    assert (r["chaveSolicitada"], r["mediaMin"]) == ({"dow": 7, "turno": "N"}, 70.0)


def test_atrasado_aparece_na_consulta(mat):
    mat.trecho_observacoes.insert_one(dict(ATRASADO_D2, ingeridoEm=agora_simulado(mat)))
    materializar(mat, ASOF)
    r = fallback(mat, O, D, T, "2026-10-14T08:30:00-03:00", min_amostras=1)
    assert (r["nivel"], r["mediaMin"], r["docsLidos"]) == ("dow+turno", 40.0, 5)


def test_explain_ixscan_no_maximo_21(mat):
    r = fallback(mat, O, D, T, SEXTA_20H, asof=ASOF, com_explain=True)
    ex = r["explain"]
    assert ex["usaIndice"] and "chave_media_unica" in ex["indices"]
    assert "IXSCAN" in ex["estagioVencedor"]
    assert ex["totalKeysExamined"] <= 21 and ex["totalDocsExamined"] <= 21
    assert ex["nReturned"] == 4


def test_onthefly_responde_igual_ao_materializado(mat):
    for inst, minimo in [(SEXTA_20H, 3), (SEXTA_20H, 5), ("2026-10-13T10:00:00-03:00", 5)]:
        a = fallback(mat, O, D, T, inst, asof=ASOF, min_amostras=minimo)
        b = onthefly(mat, O, D, T, inst, asof=ASOF, min_amostras=minimo, com_explain=True)
        assert (a["nivel"], a["n"]) == (b["nivel"], b["n"])
        assert a["mediaMin"] == pytest.approx(b["mediaMin"])
        assert a["mediaKm"] == pytest.approx(b["mediaKm"])
    assert "IXSCAN" in b["explain"]["estagioVencedor"]


# ---- validators -------------------------------------------------------------

def _valida(db, **troca):
    base = obs("V", O, D, T, sp(2026, 10, 1, 10), 40, 39)
    base.update(troca)
    db.trecho_observacoes.insert_one(base)


@pytest.mark.parametrize("troca", [
    {"observadoEm": "2026-10-15T20:00:00-03:00"},   # data como string (anti-exemplo 14.7)
    {"tempoMin": 0},
    {"distanciaKm": -1.0},
    {"tipoVeiculo": "MOTO"},
    {"seq": 0},
])
def test_validator_rejeita_observacao_invalida(db, troca):
    with pytest.raises(WriteError) as e:
        _valida(db, **troca)
    assert e.value.code == 121  # DocumentValidationFailure


def test_validator_rejeita_sem_campo_obrigatorio(db):
    doc = obs("V", O, D, T, sp(2026, 10, 1, 10), 40, 39)
    doc.pop("ingeridoEm")
    with pytest.raises(WriteError):
        db.trecho_observacoes.insert_one(doc)


def test_validator_rejeita_bucket_e_media_sem_soma(db):
    with pytest.raises(WriteError):
        db.trecho_media_historica.insert_one({"origem": O, "destino": D, "tipoVeiculo": T,
                                              "dow": 6, "turno": "N", "mediaMin": 50.0})
    with pytest.raises(WriteError):
        db.trecho_bucket_diario.insert_one({"origem": O, "destino": D, "tipoVeiculo": T,
                                            "dataLocal": datetime(2026, 10, 1), "hora": 25})
