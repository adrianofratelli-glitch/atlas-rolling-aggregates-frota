"""Ingestão simulada e prévia do próximo job."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frota import ingestao, previa
from frota import seed as seed_mod
from frota.schemas import VALIDATORS

AGORA = datetime(2026, 10, 19, 13, tzinfo=timezone.utc)


def _obs(i, quando, seq=1):
    return {"viagemId": f"V{i}", "veiculoId": "VE1", "seq": seq, "origem": "A", "destino": "B", "tipoVeiculo": "TRUCK",
            "observadoEm": quando, "tempoMin": 10.0, "distanciaKm": 5.0}


def _fila(db):
    db.ingestao_simulada.insert_many([_obs(1, AGORA - timedelta(hours=2)), _obs(2, AGORA - timedelta(minutes=1)),
                                      _obs(3, AGORA + timedelta(hours=1)), _obs(4, AGORA + timedelta(days=2))])


def test_ingerir_move_so_passado(db):
    _fila(db)
    r = ingestao.ingerir(db, AGORA)
    assert r["movidos"] == 2 and r["restantes"] == 2
    assert r["simuladoAte"] == AGORA + timedelta(days=2)
    assert db.trecho_observacoes.count_documents({}) == 2
    assert db.ingestao_simulada.count_documents({"observadoEm": {"$lt": AGORA}}) == 0
    assert db.trecho_observacoes.count_documents({"_id": {"$in": [d["_id"] for d in db.ingestao_simulada.find()]}}) == 0


def test_ingerir_idempotente(db):
    _fila(db)
    ingestao.ingerir(db, AGORA)
    assert ingestao.ingerir(db, AGORA)["movidos"] == 0
    # a mesma observação reaparece na fila: o índice único (viagemId, seq) não cria 2º doc
    db.ingestao_simulada.insert_one(_obs(1, AGORA - timedelta(hours=2)))
    ingestao.ingerir(db, AGORA)
    assert db.trecho_observacoes.count_documents({"viagemId": "V1"}) == 1


def test_simulado_ate(db):
    assert ingestao.simulado_ate(db) is None
    _fila(db)
    assert ingestao.simulado_ate(db) == AGORA + timedelta(days=2)


def test_previa_nao_escreve(db):
    seed_mod.resetar(db, AGORA, 1, perfil="teste")
    antes = {n: db[n].count_documents({}) for n in VALIDATORS}
    previa.proximo(db, AGORA)
    assert {n: db[n].count_documents({}) for n in VALIDATORS} == antes


def test_previa_dias(db):
    db.trecho_observacoes.insert_many([
        _obs(1, datetime(2026, 10, 19, 12, tzinfo=timezone.utc)),   # dia que entra
        _obs(2, datetime(2026, 4, 22, 12, tzinfo=timezone.utc)),    # dia que sai
        _obs(3, datetime(2026, 4, 22, 15, tzinfo=timezone.utc))])
    db.trecho_media_dow_hora.insert_one({"origem": "A", "destino": "B", "tipoVeiculo": "TRUCK",
                                         "dow": 1, "hora": 9, "n": 3, "somaMin": 30.0,
                                         "somaQuadMin": 300.0, "somaKm": 15.0, "mediaMin": 10.0,
                                         "mediaKm": 5.0, "dataRef": "2026-10-19", "janelaInicio": AGORA,
                                         "janelaFim": AGORA, "runId": "r", "atualizadoEm": AGORA})
    r = previa.proximo(db, AGORA)
    assert r["entra"] == {"dia": "2026-10-19", "observacoes": 1}
    assert r["sai"] == {"dia": "2026-04-22", "observacoes": 2}
    assert r["dataRef"] == "2026-10-20"
    assert r["quando"] == datetime(2026, 10, 20, 6, 10, tzinfo=timezone.utc)
    assert r["chavesQueSomem"] == 0
    db.trecho_observacoes.delete_many({"viagemId": "V1"})
    assert previa.proximo(db, AGORA)["chavesQueSomem"] == 1
