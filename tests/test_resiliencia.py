"""Bateria de aceite do ponto de vista do cliente: "o que acontece quando…".

Cada teste responde uma pergunta que um time de operação faria antes de aprovar.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from frota import config as config_mod
from frota import settings
from frota.bootstrap import bootstrap
from frota.consulta import fallback
from frota.db import get_db
from frota.janela import inicio_dia, janela
from frota.job import LockOcupado, materializar
from frota.pipelines import estagios, raw_onthefly
from frota.seed import seed
from tests.fixtures.dataset import ASOF, obs, sp

A = ("BASE-001", "POSTO-0042", "BITREM")
SEXTA_20H = "2026-10-16T20:00:00-03:00"
NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0}

TURNOS = {
    "padrao": [{"codigo": "M", "inicioHora": 6, "fimHora": 12},
               {"codigo": "T", "inicioHora": 12, "fimHora": 18},
               {"codigo": "N", "inicioHora": 18, "fimHora": 6}],
    "quatro_blocos": [{"codigo": "MAD", "inicioHora": 0, "fimHora": 6},
                      {"codigo": "M", "inicioHora": 6, "fimHora": 12},
                      {"codigo": "T", "inicioHora": 12, "fimHora": 19},
                      {"codigo": "N", "inicioHora": 19, "fimHora": 24}],
    "noite_longa": [{"codigo": "D", "inicioHora": 5, "fimHora": 20},
                    {"codigo": "N", "inicioHora": 20, "fimHora": 5}],
}


def equivalente(db, amostra=12, semente=3) -> int:
    """Média do agregado == média calculada na raw, para uma amostra de chaves."""
    cfg = config_mod.ler(db)
    asof = db.trecho_media_historica.find_one()["asOf"]
    ji, jf = janela(asof, cfg)
    pares = sorted({(d["origem"], d["destino"], d["tipoVeiculo"]) for d in
                    db.trecho_media_historica.find({}, {"origem": 1, "destino": 1, "tipoVeiculo": 1})})
    n = 0
    for o, d, t in random.Random(semente).sample(pares, min(amostra, len(pares))):
        mat = {(x["dow"], x["turno"]): x for x in db.trecho_media_historica.find(
            {"origem": o, "destino": d, "tipoVeiculo": t})}
        raw = {(x["dow"], x["turno"]): x for x in db.trecho_observacoes.aggregate(
            estagios(raw_onthefly.pipeline(o, d, t, ji, jf, cfg)))}
        assert mat.keys() == raw.keys(), (o, d, t)
        for k in mat:
            assert mat[k]["n"] == raw[k]["n"]
            assert mat[k]["mediaMin"] == pytest.approx(raw[k]["somaMin"] / raw[k]["n"])
            n += 1
    return n


# ---- "e se a gente mudar a regra de negócio?" ---------------------------------

@pytest.fixture(scope="module")
def sintetico():
    db = get_db("frota_eta_matriz_test")
    db.config.delete_many({})
    bootstrap(db)
    seed(db, "teste", 42, ASOF, log=None)
    materializar(db, ASOF)
    return db


@pytest.mark.parametrize("turnos", list(TURNOS))
@pytest.mark.parametrize("regra", ["dia_civil", "dia_operacional"])
@pytest.mark.parametrize("modo", ["merge_runid", "out"])
def test_matriz_de_opcoes_raw_igual_materializado(sintetico, turnos, regra, modo):
    """12 combinações de turnos × regra da noite × modo de limpeza: só a camada 2 roda,
    a raw não é relida e o resultado continua batendo com a raw."""
    db = sintetico
    buckets_antes = db.trecho_bucket_diario.count_documents({})
    config_mod.atualizar(db, {"turnos": TURNOS[turnos], "regraNoite": regra,
                              "modoLimpezaCamada2": modo})
    run = materializar(db, ASOF, camada="2")
    assert "camada1" not in run["stats"]
    assert db.trecho_bucket_diario.count_documents({}) == buckets_antes
    codigos = {t["codigo"] for t in TURNOS[turnos]}
    assert set(db.trecho_media_historica.distinct("turno")) <= codigos
    assert equivalente(db) > 10


# ---- "e se o fuso tiver horário de verão?" -------------------------------------

def test_fuso_com_horario_de_verao(monkeypatch):
    """America/New_York muda de horário em 01/11/2026: dia de 25 h. A janela continua em
    dias de calendário locais e o agregado continua igual à raw."""
    monkeypatch.setenv("FROTA_TIMEZONE", "America/New_York")
    db = get_db("frota_eta_dst_test")
    db.config.delete_many({})
    bootstrap(db)
    assert config_mod.ler(db)["timezone"] == "America/New_York"
    seed(db, "teste", 7, "2026-11-04", log=None)
    materializar(db, "2026-11-04")
    cfg = config_mod.ler(db)
    ji, jf = janela("2026-11-04", cfg)
    assert jf.isoformat() == "2026-11-04T05:00:00+00:00"      # EST, UTC-5
    assert ji.isoformat() == "2026-05-08T04:00:00+00:00"      # EDT, UTC-4
    dia_25h = inicio_dia(date(2026, 11, 1), cfg["timezone"])
    horas = sorted(db.trecho_bucket_diario.distinct("hora", {"dataLocal": dia_25h}))
    assert horas and all(0 <= h <= 23 for h in horas)
    assert equivalente(db, amostra=15) > 10


# ---- "o fallback fica fora do ar enquanto o job roda?" -------------------------

@pytest.mark.parametrize("modo", ["merge_runid", "out"])
def test_leituras_durante_o_job_nunca_ficam_sem_resposta(db, modo):
    config_mod.atualizar(db, {"modoLimpezaCamada2": modo})
    materializar(db, ASOF)
    parar, respostas, erros = threading.Event(), [], []

    def leitor():
        while not parar.is_set():
            try:
                respostas.append(fallback(db, *A, SEXTA_20H)["nivel"])
            except Exception as e:  # noqa: BLE001
                erros.append(repr(e))

    t = threading.Thread(target=leitor)
    t.start()
    for _ in range(3):
        materializar(db, ASOF)
    parar.set()
    t.join()
    assert not erros
    assert respostas and "sem_historico" not in respostas


# ---- "e se dois agendadores dispararem o job ao mesmo tempo?" ------------------

def test_dois_jobs_simultaneos_um_roda_outro_recusa(db):
    materializar(db, ASOF)
    ref = list(db.trecho_media_historica.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]))
    barreira, resultados = threading.Barrier(2), []

    def roda():
        barreira.wait()
        try:
            resultados.append(materializar(db, ASOF)["status"])
        except LockOcupado:
            resultados.append("recusado")
    ts = [threading.Thread(target=roda) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(resultados) in (["ok", "recusado"], ["ok", "ok"])  # "ok, ok" se não se sobrepuseram
    assert list(db.trecho_media_historica.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)])) == ref


# ---- "e se a frota parar (ou o job ficar meses sem rodar)?" --------------------

@pytest.mark.parametrize("modo", ["merge_runid", "out"])
def test_janela_sem_dados_esvazia_o_agregado(db, modo):
    config_mod.atualizar(db, {"modoLimpezaCamada2": modo})
    materializar(db, ASOF)
    run = materializar(db, "2027-12-01")   # janela inteira depois de todos os dados
    assert db.trecho_media_historica.count_documents({}) == 0
    assert run["stats"]["camada2"]["removidos"] > 0
    assert fallback(db, *A, SEXTA_20H)["nivel"] == "sem_historico"


def test_job_parado_varios_dias_recupera_tudo(db):
    """Último run em 10/10, próximo em 16/10: os dias 10…15 entram, não só D-1…D-3."""
    materializar(db, "2026-10-10")
    c1 = materializar(db, ASOF)["stats"]["camada1"]
    assert c1["diasReprocessados"][0] == "2026-10-10"
    assert db.trecho_media_historica.find_one({"origem": A[0], "destino": A[1], "tipoVeiculo": A[2],
                                               "dow": 5, "turno": "N"})["somaMin"] == 45


# ---- "e dado muito atrasado ou fora da janela?" --------------------------------

def test_atraso_anterior_a_janela_e_ignorado(db):
    materializar(db, ASOF)
    velho = obs("VELHO", *A, sp(2026, 3, 1, 10), 500, 39)
    velho["ingeridoEm"] = sp(2026, 10, 17)
    db.trecho_observacoes.insert_one(velho)
    run = materializar(db, ASOF)
    assert run["stats"]["camada1"]["atrasadosDetectados"] == 0
    assert db.trecho_media_historica.count_documents({"somaMin": {"$gte": 500}}) == 0


def test_rajada_de_atrasos_em_varios_dias(db):
    materializar(db, ASOF)
    rnd = random.Random(5)
    lote = []
    for i in range(300):
        d = date(2026, 10, 15) - timedelta(days=rnd.randint(1, 40))
        o = obs(f"RAJ{i}", *A, sp(d.year, d.month, d.day, rnd.randint(0, 23), rnd.randint(0, 59)),
                rnd.uniform(30, 90), 39)
        o["ingeridoEm"] = sp(2026, 10, 17) + timedelta(seconds=i)
        lote.append(o)
    db.trecho_observacoes.insert_many(lote)
    run = materializar(db, ASOF)
    assert run["stats"]["camada1"]["atrasadosDetectados"] == 300
    total = sum(d["n"] for d in db.trecho_media_historica.find(
        {"origem": A[0], "destino": A[1], "tipoVeiculo": A[2]}))
    assert total == 6 + 300
    assert equivalente(db, amostra=5) > 0


# ---- "e entradas ruins na API? e o banco fora?" --------------------------------

@pytest.fixture
def cli(db, monkeypatch):
    monkeypatch.setattr(settings, "MONGODB_DB", db.name)
    from api import main
    main._boot["ok"] = False
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.parametrize("rota,params,esperado", [
    ("/api/eta", {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM", "hora": 24}, 422),
    ("/api/eta", {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM", "hora": 3,
                  "asOf": "2026-13-01"}, 400),
    ("/eta/fallback", {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM",
                       "instante": "ontem à noite"}, 400),
    ("/eta/fallback", {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM",
                       "instante": SEXTA_20H, "minAmostras": 0}, 422),
    ("/eta/fallback", {"origem": "NAO-EXISTE", "destino": "X", "tipoVeiculo": "TOCO",
                       "instante": SEXTA_20H}, 200),
    ("/api/destinos", {"origem": "NAO-EXISTE"}, 200),
])
def test_entradas_hostis_na_api(cli, rota, params, esperado):
    assert cli.get(rota, params=params).status_code == esperado


@pytest.mark.parametrize("corpo", [
    {"mudancas": {"turnos": [{"codigo": "M", "inicioHora": 6, "fimHora": 12},
                             {"codigo": "X", "inicioHora": 10, "fimHora": 6}]}},   # sobreposição
    {"mudancas": {"timezone": "UTC"}},                                             # não editável
    {"mudancas": {"minAmostras": 0}},
])
def test_config_invalida_nao_altera_nada(cli, db, corpo):
    versao = config_mod.ler(db)["versao"]
    assert cli.post("/api/config", json=corpo).status_code == 400
    assert config_mod.ler(db)["versao"] == versao


def test_job_e_avanco_com_parametros_invalidos(cli):
    assert cli.post("/api/job", json={"camada": "9"}).status_code == 400
    assert cli.post("/api/avancar", json={"dias": 500}).status_code == 400


def test_banco_fora_do_ar_responde_503_com_acao(cli, monkeypatch):
    from pymongo import MongoClient
    from api import main
    morto = MongoClient("mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
                        serverSelectionTimeoutMS=300)
    monkeypatch.setattr(main, "get_db", lambda nome=None: morto["frota_eta_test"])
    main._boot["ok"] = False
    r = cli.get("/api/estado")
    assert r.status_code == 503 and "make up" in r.json()["acao"]
    assert cli.get("/health/live").status_code == 200   # processo vivo, banco fora


def test_banco_vazio_nao_quebra_nenhuma_tela(cli, db):
    from frota.bootstrap import limpar_dados
    limpar_dados(db)
    for rota, p in [("/api/estado", {}), ("/api/catalogo", {}), ("/api/janela", {}),
                    ("/api/job_runs", {}), ("/api/capo", {}),
                    ("/api/eta", {"origem": "A", "destino": "B", "tipoVeiculo": "TOCO", "hora": 8})]:
        assert cli.get(rota, params=p).status_code == 200, rota
    assert cli.post("/api/job", json={"asOf": ASOF}).status_code == 200


# ---- "e se mudarem a config e o job ainda não rodou?" --------------------------

def test_fallback_usa_a_config_que_gerou_o_agregado(db):
    """Turno N passa a começar às 21h, mas a camada 2 ainda não rodou: 20:00 de sexta
    continua sendo 'N' para o agregado existente, e a resposta avisa a divergência."""
    materializar(db, ASOF)
    config_mod.atualizar(db, {"turnos": [{"codigo": "M", "inicioHora": 6, "fimHora": 12},
                                         {"codigo": "T", "inicioHora": 12, "fimHora": 21},
                                         {"codigo": "N", "inicioHora": 21, "fimHora": 6}]})
    r = fallback(db, *A, SEXTA_20H, min_amostras=3)
    assert r["chaveSolicitada"] == {"dow": 6, "turno": "N"} and r["mediaMin"] == 56.0
    assert "rode a camada 2" in r["avisoConfig"]
    materializar(db, ASOF, camada="2")
    r2 = fallback(db, *A, SEXTA_20H, min_amostras=1)
    assert r2["chaveSolicitada"]["turno"] == "T" and "avisoConfig" not in r2


def test_duas_pessoas_mudando_a_config_ao_mesmo_tempo(db, monkeypatch):
    atual = config_mod.ler(db)
    db.config.update_one({"_id": "ativa"}, {"$inc": {"versao": 1}})  # outra pessoa salvou
    monkeypatch.setattr(config_mod, "ler", lambda _db: atual)
    with pytest.raises(ValueError, match="outra pessoa"):
        config_mod.atualizar(db, {"minAmostras": 9})
