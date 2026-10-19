"""Rotas da API v2 sobre o banco de teste (nunca a demo)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from api import main
from frota import seed as seed_mod
from frota import settings
from frota.schemas import VALIDATORS

CEN = {"origem": "A", "destino": "B", "tipoVeiculo": "TRUCK", "dias": [1],
       "horaInicio": 6, "horaFim": 12}


@pytest.fixture(scope="module")
def semeado(db_sessao):
    for nome in VALIDATORS:
        db_sessao[nome].delete_many({})
    seed_mod.resetar(db_sessao, main.agora_utc(), 1, perfil="teste")
    return db_sessao


@pytest.fixture
def cli(semeado, monkeypatch):
    monkeypatch.setattr(settings, "MONGODB_DB", settings.MONGODB_TEST_DB)
    monkeypatch.setitem(main._reset, "resetando", False)
    return TestClient(main.app, raise_server_exceptions=False)


def test_health(cli):
    assert cli.get("/health/live").json() == {"ok": True}
    assert cli.get("/health/ready").json()["db"] == settings.MONGODB_TEST_DB


def test_estado_local_trigger_nao_implantado(cli, monkeypatch):
    monkeypatch.setattr(settings, "ALVO", "local")
    monkeypatch.setenv("APPSERVICES_APP_ID", "app-x")
    e = cli.get("/api/estado").json()
    assert {"alvo", "agora", "dataRef", "janela", "ultimoJob", "simuladoAte",
            "resetando", "trigger"} <= set(e)
    assert e["trigger"]["implantado"] is False
    assert e["trigger"]["horarioLocal"] == "03:10"
    monkeypatch.setattr(settings, "ALVO", "atlas")
    assert cli.get("/api/estado").json()["trigger"]["implantado"] is True
    monkeypatch.setenv("APPSERVICES_APP_ID", "")
    assert cli.get("/api/estado").json()["trigger"]["implantado"] is False


def test_opcoes(cli):
    o = cli.get("/api/opcoes").json()
    assert o["trechos"] and {"origem", "destino", "nomeOrigem", "nomeDestino",
                             "esparso"} <= set(o["trechos"][0])
    assert "CARRETA" in o["tipos"] and set(o["atalhos"]) == {"manha", "tarde", "noite"}
    assert o["dias"]["1"] == "segunda"


def test_raw_schema_do_banco(cli):
    r = cli.get("/api/raw").json()
    assert set(r) >= {"amostra", "schema", "query"}
    assert len(r["amostra"]) <= 12
    assert r["schema"]["validator"] == VALIDATORS["trecho_observacoes"]
    assert any(i["nome"] == "viagemId_1_seq_1" for i in r["schema"]["indices"])
    assert r["query"]["operacao"] == "find" and ".find(" in r["query"]["mongosh"]


def test_job_proximo_runs(cli):
    r = cli.post("/api/job").json()
    assert r["query"]["le"] == ["trecho_observacoes"]
    assert r["query"]["grava"] == ["trecho_media_dow_hora"]
    assert cli.get("/api/proximo-job").json()["dataRef"]
    runs = cli.get("/api/job_runs?limite=3").json()
    assert 1 <= len(runs) <= 3


def test_cenario_contrato(cli):
    r = cli.post("/api/cenario", json=CEN)
    assert r.status_code == 200 and "query" in r.json()


def test_cenario_422_sem_dias(cli):
    r = cli.post("/api/cenario", json={**CEN, "dias": []})
    assert r.status_code == 422 and "dia" in r.json()["erro"]


def test_cenario_409_durante_reset(cli, monkeypatch):
    monkeypatch.setitem(main._reset, "resetando", True)
    for r in (cli.post("/api/cenario", json=CEN), cli.post("/api/job"), cli.get("/api/raw")):
        assert r.status_code == 409
        assert r.json() == {"erro": "a demo está sendo recriada",
                            "acao": "aguarde o reset terminar"}


def test_reset_409_concorrente(cli, monkeypatch):
    monkeypatch.setitem(main._reset, "resetando", True)
    assert cli.post("/api/reset").status_code == 409


def test_reset_inicia_e_status(cli, monkeypatch):
    chamadas = []
    monkeypatch.setattr(main.seed_mod, "resetar",
                        lambda db, agora, seed, permitir, progresso: chamadas.append(
                            (db.name, permitir)) or progresso("gerando", 0.5))
    r = cli.post("/api/reset")
    assert r.status_code == 202 and r.json() == {"iniciado": True}
    for _ in range(100):
        s = cli.get("/api/reset/status").json()
        if not s["resetando"]:
            break
        import time; time.sleep(0.05)
    assert s["pct"] == 1.0 and s["erro"] is None and s["fim"]
    assert chamadas == [(settings.MONGODB_TEST_DB, True)]


def test_503_sem_host(cli, monkeypatch):
    def quebra(*a, **k):
        raise ServerSelectionTimeoutError("x.mongodb.net:27017 timed out")
    monkeypatch.setattr(main.previa, "proximo", quebra)
    r = cli.get("/api/proximo-job")
    assert r.status_code == 503
    assert "mongodb.net" not in r.text
    assert r.json()["acao"] == "verifique a conexão com o MongoDB"
