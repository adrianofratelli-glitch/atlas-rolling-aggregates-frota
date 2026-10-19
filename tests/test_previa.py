"""Prévia do próximo job: só leitura."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frota import previa
from frota import seed as seed_mod
from frota.schemas import VALIDATORS

AGORA = datetime(2026, 10, 19, 13, tzinfo=timezone.utc)


def _obs(i, quando, seq=1):
    return {"viagemId": f"V{i}", "veiculoId": "VE1", "seq": seq, "origem": "A", "destino": "B",
            "tipoVeiculo": "TRUCK", "observadoEm": quando, "tempoMin": 10.0, "distanciaKm": 5.0}


def _base(db, dow, hora):
    db.trecho_media_dow_hora.insert_one({
        "origem": "A", "destino": "B", "tipoVeiculo": "TRUCK", "dow": dow, "hora": hora, "n": 3,
        "somaMin": 30.0, "somaQuadMin": 300.0, "somaKm": 15.0, "mediaMin": 10.0, "mediaKm": 5.0,
        "dataRef": "2026-10-19", "janelaInicio": AGORA, "janelaFim": AGORA, "runId": "r",
        "atualizadoEm": AGORA})


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


def test_chaves_que_somem_usa_celula_completa(db):
    # mesma rota: a raw da próxima janela só cobre (seg 09h); a célula (qua 09h) tem dado só no dia que sai
    db.trecho_observacoes.insert_many([
        _obs(1, datetime(2026, 10, 19, 12, tzinfo=timezone.utc)),   # segunda 09h local
        _obs(2, datetime(2026, 4, 22, 12, tzinfo=timezone.utc))])   # quarta 09h local, fora da janela
    _base(db, 1, 9)
    _base(db, 3, 9)
    assert previa.proximo(db, AGORA)["chavesQueSomem"] == 1


class _CacheLimpoNoMeio(dict):
    """Simula outra thread limpando o cache entre o teste de presença e a leitura."""
    def __contains__(self, k):
        r = super().__contains__(k)
        self.clear()
        return r


def test_previa_cache_sem_corrida(db):
    seed_mod.resetar(db, AGORA, 1, perfil="teste")
    cache = _CacheLimpoNoMeio()
    a = previa.proximo(db, AGORA, cache)
    assert previa.proximo(db, AGORA, cache) == a
