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
    monkeypatch.setattr(main, "_cache_veiculos", {})  # outro módulo pode ter semeado o banco
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
    # perfil de teste: 3 veículos por tipo, em ordem natural
    assert o["veiculos"] == {t: [f"VEI-{t}-{i}" for i in (1, 2, 3)] for t in ("TRUCK", "CARRETA")}


def test_veiculos_cache_por_run_do_job(cli, db_sessao, monkeypatch):
    from datetime import timedelta
    chamadas = []
    original = main.cenario.veiculos_por_tipo
    monkeypatch.setattr(main.cenario, "veiculos_por_tipo",
                        lambda d: chamadas.append(1) or original(d))
    a = cli.get("/api/opcoes").json()["veiculos"]
    cli.get("/api/opcoes")
    assert len(chamadas) == 1
    ok = db_sessao.job_runs.find_one({"status": "ok"}, sort=[("iniciadoEm", -1)])
    novo = {**ok, "_id": "run-cache-teste", "runId": "run-cache-teste",
            "iniciadoEm": ok["iniciadoEm"] + timedelta(minutes=1)}
    db_sessao.job_runs.insert_one(novo)  # um seed/job pela CLI gera um run novo
    try:
        assert cli.get("/api/opcoes").json()["veiculos"] == a
        assert len(chamadas) == 2
    finally:
        db_sessao.job_runs.delete_one({"_id": "run-cache-teste"})


def test_aquecer_veiculos_nao_quebra(monkeypatch):
    monkeypatch.setattr(main, "_cache_veiculos", {})
    monkeypatch.setattr(main, "db", lambda: (_ for _ in ()).throw(RuntimeError("fora")))
    main._aquecer_veiculos()  # falha engolida: a primeira requisição calcula
    assert main._cache_veiculos == {}


def test_cenario_veiculo_invalido_422(cli):
    r = cli.post("/api/cenario", json={**CEN, "veiculoId": "VEI-TRUCK-77"})
    assert r.status_code == 422 and "veículo" in r.json()["erro"].lower()


def test_colecoes_schema_do_banco(cli):
    r = cli.get("/api/colecoes").json()
    por_nome = {c["nome"]: c for c in r["colecoes"]}
    assert set(por_nome) == set(VALIDATORS)
    raw = por_nome["trecho_observacoes"]
    assert "amostra" not in raw and raw["exemplo"]["origem"]
    obrig = {c["nome"]: c["obrigatorio"] for c in raw["campos"]}
    assert obrig["tempoMin"] is True
    assert all(c["schema"] for c in raw["campos"])  # tipo vem do validator do banco
    assert any(i["nome"] == "viagemId_1_seq_1" and i["porque"] for i in raw["indices"])
    ing = r["ingestao"]
    assert ing["le"] == ["ingestao_simulada"] and ing["grava"] == ["trecho_observacoes"]
    for trecho in ("$match", "$project", "_id: 0", "$merge", "viagemId", "replace", "insert"):
        assert trecho in ing["mongosh"], trecho


def test_campos_documentados_existem_no_schema():
    from frota.colecoes import COLECOES
    for c in COLECOES:
        props = VALIDATORS[c["nome"]]["$jsonSchema"]["properties"]
        for k in c["campos"]:
            assert k in props or k.startswith("(") or k in {"uf", "location", "esparso", "lidos",
                   "gravados", "removidos", "ms"}, (c["nome"], k)


def test_trigger_script(cli):
    r = cli.get("/api/trigger-script").json()
    assert "exports = async function" in r["funcao"]["codigo"]
    assert r["funcao"]["arquivo"] == "atlas-trigger/functions/rodarJob.js"
    assert '"function_name": "rodarJob"' in r["trigger"]["codigo"]
    assert r["cron"] == "10 6 * * *" and r["horarioLocal"] == "03:10"
    assert "mongodb+srv" not in str(r) and "mongodb.net" not in str(r)


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
    assert r.json()["origem"] in {"base", "raw", "salvo"}


def test_cenario_422_sem_dias(cli):
    r = cli.post("/api/cenario", json={**CEN, "dias": []})
    assert r.status_code == 422 and "dia" in r.json()["erro"]


def test_cenario_409_durante_reset(cli, monkeypatch):
    monkeypatch.setitem(main._reset, "resetando", True)
    for r in (cli.post("/api/cenario", json=CEN), cli.post("/api/job"), cli.get("/api/colecoes")):
        assert r.status_code == 409
        assert r.json() == {"erro": "a demo está sendo recriada",
                            "acao": "aguarde o reset terminar"}


def test_reset_409_concorrente(cli, monkeypatch):
    monkeypatch.setitem(main._reset, "resetando", True)
    assert cli.post("/api/reset").status_code == 409


@pytest.fixture
def reset_limpo(monkeypatch):
    monkeypatch.setattr(main, "_reset", dict(main._reset))


def _esperar(cli):
    import time
    for _ in range(100):
        s = cli.get("/api/reset/status").json()
        if not s["resetando"]:
            return s
        time.sleep(0.05)
    return s


def test_reset_inicia_e_status(cli, reset_limpo, monkeypatch):
    chamadas = []
    monkeypatch.setattr(main.seed_mod, "resetar",
                        lambda db, agora, seed, permitir, progresso: chamadas.append(
                            (db.name, permitir)) or progresso("gerando", 0.5))
    r = cli.post("/api/reset")
    assert r.status_code == 202 and r.json() == {"iniciado": True}
    s = _esperar(cli)
    assert s["pct"] == 1.0 and s["erro"] is None and s["fim"]
    assert chamadas == [(settings.MONGODB_TEST_DB, True)]


def test_reset_com_erro_mascarado(cli, reset_limpo, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("falhou em x.mongodb.net:27017")
    monkeypatch.setattr(main.seed_mod, "resetar", quebra)
    assert cli.post("/api/reset").status_code == 202
    s = _esperar(cli)
    assert s["resetando"] is False and s["erro"] and "mongodb.net" not in s["erro"]


def test_estado_responde_durante_reset_sem_bootstrap(cli, reset_limpo, monkeypatch):
    chamou = []
    monkeypatch.setattr(main, "bootstrap", lambda d: chamou.append(1))
    main._boot.clear()
    monkeypatch.setitem(main._reset, "resetando", True)
    r = cli.get("/api/estado")
    assert r.status_code == 200 and r.json()["resetando"] is True
    assert chamou == []


def test_503_sem_host(cli, monkeypatch):
    def quebra(*a, **k):
        raise ServerSelectionTimeoutError("x.mongodb.net:27017 timed out")
    monkeypatch.setattr(main.previa, "proximo", quebra)
    r = cli.get("/api/proximo-job")
    assert r.status_code == 503
    assert "mongodb.net" not in r.text
    assert r.json()["acao"] == "verifique a conexão com o MongoDB"


def test_estado_ultimo_job_ok_e_erro_separado(cli, db_sessao):
    from datetime import timedelta
    ok = db_sessao.job_runs.find_one({"status": "ok"}, sort=[("iniciadoEm", -1)])
    e = cli.get("/api/estado").json()
    assert e["ultimoJob"]["runId"] == ok["runId"] and e["ultimoErro"] is None
    db_sessao.job_runs.insert_one({"_id": "run-erro-api", "runId": "run-erro-api",
                                   "origem": "cli", "status": "erro", "erro": "falhou",
                                   "dataRef": ok["dataRef"],
                                   "iniciadoEm": ok["iniciadoEm"] + timedelta(minutes=5)})
    try:
        e = cli.get("/api/estado").json()
        assert e["ultimoJob"]["runId"] == ok["runId"] and e["ultimoJob"]["status"] == "ok"
        assert e["ultimoErro"]["runId"] == "run-erro-api" and e["ultimoErro"]["erro"] == "falhou"
    finally:
        db_sessao.job_runs.delete_one({"_id": "run-erro-api"})


def test_proximo_job_em_cache(cli, monkeypatch):
    chamadas = []
    original = main.previa._chaves_na_raw
    monkeypatch.setattr(main.previa, "_chaves_na_raw",
                        lambda *a: chamadas.append(1) or original(*a))
    main._cache_previa.clear()
    a = cli.get("/api/proximo-job").json()
    b = cli.get("/api/proximo-job").json()
    assert a == b and len(chamadas) == 1
    cli.post("/api/job")  # novo run: a base mudou, a prévia recalcula
    cli.get("/api/proximo-job")
    assert len(chamadas) == 2


def test_veiculos_cache_sem_corrida(semeado, monkeypatch):
    class Limpa(dict):
        def __contains__(self, k):
            r = super().__contains__(k)
            self.clear()
            return r
    monkeypatch.setattr(main, "_cache_veiculos", Limpa())
    monkeypatch.setattr(settings, "MONGODB_DB", settings.MONGODB_TEST_DB)
    a = main._veiculos(semeado)
    assert main._veiculos(semeado) == a
