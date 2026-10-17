"""Os três desenhos — simples, incremental por turno, incremental por hora — produzem o
mesmo agregado. Muda só como (e quanto) se recalcula."""
from __future__ import annotations

import pytest

from frota import config as config_mod
from frota.bootstrap import bootstrap
from frota.consulta import fallback
from frota.db import get_db
from frota.job import materializar
from frota.seed import seed
from tests.fixtures.dataset import ASOF, obs, sp

A = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}
NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0, "configVersao": 0}
ORDEM = [("origem", 1), ("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]
MODOS = {
    "simples": {"modoMaterializacao": "simples"},
    "incremental_turno": {"modoMaterializacao": "incremental", "granularidadeBucket": "turno"},
    "incremental_hora": {"modoMaterializacao": "incremental", "granularidadeBucket": "hora"},
}


def usar(db, modo, **extra):
    return config_mod.atualizar(db, {**MODOS[modo], **extra})


def media(db, **chave):
    return db.trecho_media_historica.find_one({**A, **chave}, NEG)


def agregado(db):
    return list(db.trecho_media_historica.find({}, {**NEG, "asOf": 0}).sort(ORDEM))


@pytest.mark.parametrize("modo", list(MODOS))
def test_contrato_14_1_em_todos_os_modos(db, modo):
    usar(db, modo)
    materializar(db, ASOF)
    m = media(db, dow=6, turno="N")
    assert (m["n"], m["somaMin"], m["mediaMin"], m["mediaKm"]) == (3, 168, 56.0, 40.0)
    assert db.trecho_media_historica.count_documents({"somaMin": {"$gte": 999}}) == 0
    usar(db, modo, regraNoite="dia_operacional")
    materializar(db, ASOF)
    m = media(db, dow=6, turno="N")
    assert (m["n"], m["somaMin"], m["mediaKm"]) == (4, 238, 40.5)
    assert media(db, dow=7, turno="N")["somaMin"] == 30 and media(db, dow=1, turno="N") is None


@pytest.mark.parametrize("modo", list(MODOS))
def test_avanco_da_janela_em_todos_os_modos(db, modo):
    usar(db, modo)
    materializar(db, ASOF)
    run = materializar(db, "2026-10-17")
    assert media(db, dow=1, turno="N") is None
    assert (media(db, dow=6, turno="N")["n"], media(db, dow=6, turno="N")["somaMin"]) == (5, 2166)
    parte = run["stats"]["simples" if modo == "simples" else "camada2"]
    assert parte["removidos"] >= 1


def test_simples_absorve_atraso_antigo_sem_watermark(db):
    usar(db, "simples")
    materializar(db, ASOF)
    late = obs("LATE-D60", *A.values(), sp(2026, 8, 18, 10), 33, 39)   # ter, D-59
    db.trecho_observacoes.insert_one(late)
    run = materializar(db, ASOF)
    assert "camada1" not in run["stats"] and run["stats"]["simples"]["lidos"] == 12
    assert media(db, dow=3, turno="M")["mediaMin"] == 33.0


def test_simples_nao_tem_camada_1(db):
    usar(db, "simples")
    with pytest.raises(ValueError, match="modo simples"):
        materializar(db, ASOF, camada="1")


def test_turno_grava_config_e_recarrega_quando_ela_muda(db):
    usar(db, "incremental_turno")
    materializar(db, ASOF)
    assert db.trecho_bucket_turno.count_documents({}) > 0
    assert materializar(db, ASOF)["stats"]["camada1"]["modo"] == "incremental"
    usar(db, "incremental_turno", turnos=[{"codigo": "M", "inicioHora": 6, "fimHora": 12},
                                          {"codigo": "T", "inicioHora": 12, "fimHora": 21},
                                          {"codigo": "N", "inicioHora": 21, "fimHora": 6}])
    c1 = materializar(db, ASOF)["stats"]["camada1"]
    assert c1["modo"] == "recarga_por_config" and len(c1["diasReprocessados"]) == 180
    assert db.trecho_bucket_turno.count_documents({"turno": "N", "dataLocal": sp(2026, 10, 9)}) == 0
    assert media(db, dow=6, turno="T")["n"] == 3   # as 20:00 de sexta agora são tarde


def test_sem_dow_a_chave_e_so_o_turno(db):
    usar(db, "simples", incluirDow=False)
    materializar(db, ASOF)
    docs = list(db.trecho_media_historica.find(A))
    assert {d["dow"] for d in docs} == {0} and len(docs) == 1   # só turno N neste trecho
    r = fallback(db, *A.values(), "2026-10-16T20:00:00-03:00", min_amostras=1)
    assert (r["chaveSolicitada"], r["nivel"], r["n"]) == ({"dow": 0, "turno": "N"}, "turno", 6)


# ---- dados sintéticos: os três modos dão o mesmo resultado ------------------------

@pytest.fixture(scope="module")
def sintetico():
    db = get_db("frota_eta_modos_test")
    db.config.delete_many({})
    db.config_versoes.delete_many({})
    bootstrap(db)
    seed(db, "teste", 42, ASOF, log=None)
    return db


@pytest.mark.parametrize("extra", [{}, {"regraNoite": "dia_operacional"}, {"incluirDow": False}],
                         ids=["civil", "operacional", "sem_dow"])
def test_tres_modos_mesmo_agregado(sintetico, extra):
    db = sintetico
    resultados = {}
    for modo in MODOS:
        usar(db, modo, **extra)
        materializar(db, ASOF)
        resultados[modo] = agregado(db)
    assert resultados["simples"] and len(resultados["simples"]) > 50
    assert resultados["simples"] == resultados["incremental_turno"] == resultados["incremental_hora"]


def test_grao_turno_compacta_mais_que_hora(sintetico):
    db = sintetico
    for modo in ("incremental_turno", "incremental_hora"):
        usar(db, modo)
        materializar(db, ASOF)
    raw = db.trecho_observacoes.count_documents({})
    turno, hora = (db.trecho_bucket_turno.count_documents({}),
                   db.trecho_bucket_diario.count_documents({}))
    assert turno < hora < raw


def test_alternar_grao_e_modo_ao_longo_dos_dias_continua_igual_ao_simples(sintetico):
    """Regressão: depois de runs por hora, o grão turno confiava no histórico do outro grão
    e reprocessava só k dias. Cada grão agora parte do próprio último run."""
    from frota.simulacao import avancar
    db = sintetico
    sequencia = ["incremental_hora", "incremental_turno", "simples", "incremental_hora",
                 "incremental_turno", "incremental_turno"]
    for modo in sequencia:
        usar(db, modo)
        avancar(db, 1)
        obtido = agregado(db)
        usar(db, "simples")
        materializar(db, db.trecho_media_historica.find_one()["asOf"])
        assert obtido == agregado(db), modo


def test_buckets_apagados_ou_historico_antigo_forcam_recarga(db):
    usar(db, "incremental_turno")
    materializar(db, ASOF)
    # simula histórico sem cobertura (versão antiga, ou run que só gravou k dias)
    db.job_runs.update_many({}, {"$unset": {"stats.camada1.coberturaDesde": ""}})
    c1 = materializar(db, ASOF)["stats"]["camada1"]
    assert c1["modo"] == "recarga_por_config" and len(c1["diasReprocessados"]) == 180
    assert materializar(db, ASOF)["stats"]["camada1"]["modo"] == "incremental"
