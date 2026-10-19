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


def test_ingerir_nao_perde_chegada_no_meio(db, monkeypatch):
    _fila(db)
    original = ingestao._selecionar

    def selecionar_e_chega_outro(d, agora):
        ids = original(d, agora)
        d.ingestao_simulada.insert_one(_obs(9, AGORA - timedelta(minutes=5)))  # chega depois da escolha
        return ids

    monkeypatch.setattr(ingestao, "_selecionar", selecionar_e_chega_outro)
    assert ingestao.ingerir(db, AGORA)["movidos"] == 2
    assert db.ingestao_simulada.count_documents({"viagemId": "V9"}) == 1
    assert db.trecho_observacoes.count_documents({"viagemId": "V9"}) == 0
