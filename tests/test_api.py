"""API sobre o banco de teste (mesmos módulos dos testes de domínio)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from frota import settings


@pytest.fixture
def cli(db, monkeypatch):
    monkeypatch.setattr(settings, "MONGODB_DB", db.name)
    from api import main
    main._boot["ok"] = False
    return TestClient(main.app)


Q = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}


def test_contrato_eta_fallback(cli):
    assert cli.post("/api/job", json={"asOf": "2026-10-16"}).status_code == 200
    r = cli.get("/eta/fallback", params={**Q, "instante": "2026-10-16T20:00:00-03:00",
                                         "asOf": "2026-10-16", "minAmostras": 3}).json()
    assert (r["nivel"], r["mediaMin"], r["n"], r["docsLidos"]) == ("dow+turno", 56.0, 3, 4)
    assert r["janela"] == {"inicio": "2026-04-19T00:00:00-03:00",
                           "fimExclusivo": "2026-10-16T00:00:00-03:00"}


def test_eta_ui_mostra_contexto_derivado(cli):
    cli.post("/api/job", json={"asOf": "2026-10-16"})
    r = cli.get("/api/eta", params={**Q, "hora": 20, "asOf": "2026-10-16"}).json()
    c = r["contexto"]
    assert (c["dow"], c["dowNome"], c["turno"]) == (6, "sexta", "N")
    assert c["janela"]["inicioLocal"] == "2026-04-19"
    assert c["janela"]["ultimoDiaIncluido"] == "2026-10-15"
    assert c["chaveConsultada"] == {**Q, "dow": 6, "turno": "N"}
    nomes = {b["badge"] for b in r["badges"]}
    assert {"Computed Pattern", "$jsonSchema"} <= nomes


def test_comparar_e_badges_derivados(cli):
    cli.post("/api/job", json={"asOf": "2026-10-16"})
    r = cli.get("/api/comparar", params={**Q, "hora": 20, "asOf": "2026-10-16"}).json()
    assert r["mesmaResposta"]
    assert r["materializado"]["explain"]["totalDocsExamined"] <= 21
    assert "unique index" in {b["badge"] for b in r["materializado"]["badges"]}
    assert "$merge" not in {b["badge"] for b in r["materializado"]["badges"]}


def test_job_badges_e_pipeline_executado(cli):
    r = cli.post("/api/job", json={"asOf": "2026-10-16"}).json()
    nomes = {b["badge"] for b in r["badges"]}
    assert {"$merge", "Bucket Pattern", "Computed Pattern", "$dateTrunc com timezone",
            "unique index", "TTL", "$jsonSchema"} <= nomes
    assert "$out" in nomes  # default da camada 2 (medido mais rápido no Atlas)
    assert "$merge" in r["mongosh"]["camada1"] and "whenMatched" in r["mongosh"]["camada1"]


def test_config_rerroda_so_camada2(cli):
    cli.post("/api/job", json={"asOf": "2026-10-16"})
    r = cli.post("/api/config", json={"mudancas": {"modoLimpezaCamada2": "out"},
                                      "rerodarCamada2": True, "asOf": "2026-10-16"}).json()
    assert r["provaRawIntacta"]["camada1Executada"] is False
    assert r["provaRawIntacta"]["ultimoBucketRunIdAntes"] == r["provaRawIntacta"]["ultimoBucketRunIdDepois"]
    assert "$out" in {b["badge"] for b in r["badges"]}


def test_atrasado_e_capo(cli):
    cli.post("/api/job", json={"asOf": "2026-10-16"})
    r = cli.post("/api/atrasado", json={**Q, "asOf": "2026-10-16"}).json()
    assert r["inserido"]["observadoEm"].startswith("2026-10-14T11:00")
    capo = cli.get("/api/capo", params={"asOf": "2026-10-16"}).json()
    raw = capo["colecoes"]["trecho_observacoes"]
    assert raw["validationLevel"] == "strict"
    assert any(i.get("ttlDias") == 200 for i in raw["indices"])


def test_config_invalida_400(cli):
    r = cli.post("/api/config", json={"mudancas": {"regraNoite": "x"}})
    assert r.status_code == 400


def test_atrasado_sem_campos_400(cli):
    assert cli.post("/api/atrasado", json={"origem": "BASE-001"}).status_code == 400
