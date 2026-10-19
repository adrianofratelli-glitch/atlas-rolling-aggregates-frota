"""Job diário: raw → trecho_media_dow_hora (dow × hora), `$merge` replace e limpeza."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from frota import job as job_mod
from frota import seed as seed_mod
from frota.janela import hoje_local, janela_padrao

AGORA = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
HOJE = hoje_local(AGORA)
COLECAO = "trecho_media_dow_hora"


@pytest.fixture
def base(db):
    seed_mod.resetar(db, AGORA, 1, perfil="teste")
    return db


def _docs(db):
    return {(d["origem"], d["destino"], d["tipoVeiculo"], d["dow"], d["hora"]): d
            for d in db[COLECAO].find({}, {"_id": 0})}


def _sem_run(d):
    return {k: v for k, v in d.items() if k not in ("runId", "atualizadoEm")}


def test_resetar_roda_job(base):
    assert base[COLECAO].count_documents({}) > 0
    assert base.job_runs.count_documents({"origem": "reset"}) == 1


def test_job_exclui_hoje(base):
    ini, fim = janela_padrao(HOJE)
    r = job_mod.rodar_job(base, HOJE, "cli")
    na_janela = base.trecho_observacoes.count_documents({"observadoEm": {"$gte": ini, "$lt": fim}})
    total = base.trecho_observacoes.count_documents({})
    assert total > na_janela  # há observações de hoje que não entram
    soma = next(base[COLECAO].aggregate([{"$group": {"_id": None, "n": {"$sum": "$n"}}}]))["n"]
    assert soma == na_janela == r["lidos"]


def test_job_idempotente(base):
    job_mod.rodar_job(base, HOJE, "cli")
    a = {k: _sem_run(v) for k, v in _docs(base).items()}
    r2 = job_mod.rodar_job(base, HOJE, "cli")
    b = {k: _sem_run(v) for k, v in _docs(base).items()}
    assert a == b
    assert base[COLECAO].count_documents({"runId": r2["runId"]}) == len(b)


def test_job_remove_chave_fora_da_janela(base):
    velho = dict(next(iter(_docs(base).values())))
    velho.update(origem="ZZZ", atualizadoEm=datetime(2020, 1, 1, tzinfo=timezone.utc))
    base[COLECAO].insert_one(velho)
    r = job_mod.rodar_job(base, HOJE, "cli")
    assert base[COLECAO].count_documents({"origem": "ZZZ"}) == 0
    assert r["removidos"] >= 1


def test_dois_runs_sobrepostos_nao_perdem(base):
    a = job_mod.rodar_job(base, HOJE, "cli")
    b = job_mod.rodar_job(base, HOJE, "botao")
    assert a["gravados"] == b["gravados"] == base[COLECAO].count_documents({})


def test_dow_iso_borda_meia_noite(db):
    # 2026-10-24T02:30Z = sexta 23:30 em São Paulo
    db.trecho_observacoes.insert_one({
        "origem": "A", "destino": "B", "tipoVeiculo": "TRUCK", "veiculoId": "v", "viagemId": "x",
        "seq": 1, "observadoEm": datetime(2026, 10, 24, 2, 30, tzinfo=timezone.utc),
        "distanciaKm": 10.0, "tempoMin": 20.0})
    job_mod.rodar_job(db, hoje_local(datetime(2026, 10, 30, 12, tzinfo=timezone.utc)), "cli")
    d = db[COLECAO].find_one({"origem": "A"})
    assert (d["dow"], d["hora"]) == (5, 23)


def test_somas_arredondadas(base):
    job_mod.rodar_job(base, HOJE, "cli")
    for d in base[COLECAO].find():
        for c in ("somaMin", "somaQuadMin", "somaKm"):
            assert round(d[c], 6) == d[c]
        assert d["dataRef"] == HOJE.isoformat()
        assert d["mediaMin"] == pytest.approx(d["somaMin"] / d["n"])


def test_job_runs_registra_erro_sem_host(db, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("falhou em cluster0-shard-00-00.abc12.mongodb.net:27017")
    monkeypatch.setattr(type(db.trecho_observacoes), "aggregate", quebra)
    with pytest.raises(RuntimeError):
        job_mod.rodar_job(db, HOJE, "cli")
    run = db.job_runs.find_one({"status": "erro"})
    assert run and "mongodb.net" not in run["erro"] and "<host>" in run["erro"]
