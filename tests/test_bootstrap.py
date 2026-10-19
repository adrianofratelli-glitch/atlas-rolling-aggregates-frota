from datetime import datetime, timezone

import pytest
from pymongo.errors import WriteError

from frota import db as dbmod
from frota.bootstrap import bootstrap

INDICES = {
    "trecho_observacoes": {"_id_", "viagemId_1_seq_1",
                           "origem_1_destino_1_tipoVeiculo_1_observadoEm_1", "observadoEm_1_ttl"},
    "ingestao_simulada": {"_id_", "viagemId_1_seq_1", "observadoEm_1"},
    "trecho_media_dow_hora": {"_id_", "chave_unica"},
    "consultas_salvas": {"_id_", "expiraEm_ttl"},
    "pontos": {"_id_"},
    "trechos": {"_id_", "origem_1_destino_1"},
    "job_runs": {"_id_", "iniciadoEm_-1"},
}
UTC = timezone.utc


def _obs(**kw):
    base = {"origem": "A", "destino": "B", "tipoVeiculo": "TOCO", "veiculoId": "V1",
            "viagemId": "VG1", "seq": 1, "observadoEm": datetime(2026, 10, 1, tzinfo=UTC),
            "distanciaKm": 10.0, "tempoMin": 20.0}
    return {**base, **kw}


def test_bootstrap_idempotente(db_sessao):
    bootstrap(db_sessao)
    bootstrap(db_sessao)
    for nome, esperado in INDICES.items():
        assert {i["name"] for i in db_sessao[nome].list_indexes()} == esperado, nome
    ttl = {i["name"]: i for i in db_sessao.trecho_observacoes.list_indexes()}
    assert ttl["observadoEm_1_ttl"]["expireAfterSeconds"] == 200 * 86400


def test_validator_recusa_data_string(db):
    with pytest.raises(WriteError):
        db.trecho_observacoes.insert_one(_obs(observadoEm="2026-10-01"))


def test_validator_recusa_dow_8(db):
    doc = {"origem": "A", "destino": "B", "tipoVeiculo": "TOCO", "dow": 8, "hora": 3,
           "n": 1, "somaMin": 1.0, "somaQuadMin": 1.0, "somaKm": 1.0, "mediaMin": 1.0,
           "mediaKm": 1.0, "janelaInicio": datetime(2026, 4, 1, tzinfo=UTC),
           "janelaFim": datetime(2026, 10, 1, tzinfo=UTC), "dataRef": "2026-10-01",
           "runId": "r", "atualizadoEm": datetime(2026, 10, 1, tzinfo=UTC)}
    with pytest.raises(WriteError):
        db.trecho_media_dow_hora.insert_one(doc)
    db.trecho_media_dow_hora.insert_one({**doc, "dow": 7})


def test_guardar_escrita_recusa_demo(monkeypatch):
    monkeypatch.delenv("ALLOW_DEMO_DB_WRITE", raising=False)
    with pytest.raises(dbmod.EscritaRecusada):
        dbmod.guardar_escrita("frota_eta")
    assert dbmod.guardar_escrita("frota_eta", permitir=True) == "frota_eta"
    assert dbmod.guardar_escrita("x_test") == "x_test"


def test_mascarar_host():
    assert dbmod.mascarar("x.mongodb.net:27017") == "<host>"
