"""Dados atrasados (dentro e fora de k) e exclusão mútua do job."""
from __future__ import annotations

import pytest

from frota.job import LockOcupado, adquirir_lock, liberar_lock, materializar
from frota.simulacao import agora_simulado
from tests.fixtures.dataset import ASOF, ATRASADO_D2, obs, sp

A = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}
NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0}


def negocio(db):
    return (list(db.trecho_bucket_diario.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dataLocal", 1), ("hora", 1)])),
            list(db.trecho_media_historica.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)])))


def test_atrasado_d2_corrige_e_terceiro_run_nao_muda_nada(db):
    materializar(db, ASOF)
    late = dict(ATRASADO_D2, ingeridoEm=agora_simulado(db))
    db.trecho_observacoes.insert_one(late)
    materializar(db, ASOF)
    b = db.trecho_bucket_diario.find_one({**A, "dataLocal": sp(2026, 10, 14), "hora": 8})
    assert b["n"] == 1
    assert db.trecho_media_historica.find_one({**A, "dow": 4, "turno": "M"})["mediaMin"] == 40.0
    depois_2 = negocio(db)
    materializar(db, ASOF)
    assert negocio(db) == depois_2


def test_atrasado_fora_de_k_detectado_pelo_watermark(db):
    materializar(db, ASOF)
    # ter 06/10 10:00 = D-10, fora de D-1…D-3
    late = obs("LATE-D10", *A.values(), sp(2026, 10, 6, 10), 33, 39)
    late["ingeridoEm"] = agora_simulado(db)
    db.trecho_observacoes.insert_one(late)
    run = materializar(db, ASOF)
    c1 = run["stats"]["camada1"]
    assert c1["atrasadosForaDaJanelaK"] == 1 and run["atrasadosForaDaJanelaK"] == 1
    assert "2026-10-06" in c1["diasReprocessados"] and c1["diasAtrasados"] == ["2026-10-06"]
    assert db.trecho_media_historica.find_one({**A, "dow": 3, "turno": "M"})["mediaMin"] == 33.0
    # o watermark avançou: o mesmo atrasado não é contado de novo
    assert materializar(db, ASOF)["atrasadosForaDaJanelaK"] == 0


def test_job_concorrente_falha_limpo_e_registra(db):
    adquirir_lock(db, "outro-processo")
    try:
        with pytest.raises(LockOcupado):
            materializar(db, ASOF)
        run = db.job_runs.find_one(sort=[("iniciadoEm", -1)])
        assert run["status"] == "erro" and "ocupado por outro-processo" in run["erro"]
        assert db.trecho_bucket_diario.count_documents({}) == 0
    finally:
        liberar_lock(db, "outro-processo")
    assert materializar(db, ASOF)["status"] == "ok"
    assert db.job_locks.count_documents({}) == 0


def test_lock_expirado_pode_ser_retomado(db):
    adquirir_lock(db, "morto", lease_s=-1)  # lease já vencido (processo morreu)
    assert materializar(db, ASOF)["status"] == "ok"


def test_retomada_apos_falha_produz_mesmo_resultado(db, monkeypatch):
    import frota.job as job
    referencia_db = db
    materializar(referencia_db, ASOF)
    ref = negocio(db)
    db.trecho_bucket_diario.delete_many({})
    db.trecho_media_historica.delete_many({})
    db.job_runs.delete_many({})

    original = job.executar_camada2

    def quebra(*a, **k):
        raise RuntimeError("falha simulada depois da camada 1")
    monkeypatch.setattr(job, "executar_camada2", quebra)
    with pytest.raises(RuntimeError):
        materializar(db, ASOF)
    assert db.job_runs.find_one(sort=[("iniciadoEm", -1)])["status"] == "erro"
    monkeypatch.setattr(job, "executar_camada2", original)
    materializar(db, ASOF)
    assert negocio(db) == ref


def test_retry_em_erro_transitorio(db, monkeypatch):
    import frota.job as job
    from pymongo.errors import AutoReconnect
    chamadas = {"n": 0}
    original = job.executar_camada1

    def instavel(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise AutoReconnect("queda simulada")
        return original(*a, **k)
    monkeypatch.setattr(job, "executar_camada1", instavel)
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    run = materializar(db, ASOF)
    assert run["status"] == "ok" and chamadas["n"] == 2
    assert run["stats"]["camada1"]["tentativas"] == 2
    assert "AutoReconnect" in run["stats"]["camada1"]["errosTransitorios"][0]


def test_retry_depois_de_escrita_parcial_conta_certo(db, monkeypatch):
    """A 1ª tentativa grava os buckets e cai; a 2ª não pode contá-los como 'atualizados'."""
    import frota.job as job
    from pymongo.errors import AutoReconnect
    original = job.executar_camada1
    chamadas = {"n": 0}

    def cai_depois_de_gravar(*a, **k):
        chamadas["n"] += 1
        r = original(*a, **k)
        if chamadas["n"] == 1:
            raise AutoReconnect("queda depois do $merge")
        return r
    monkeypatch.setattr(job, "executar_camada1", cai_depois_de_gravar)
    monkeypatch.setattr(job.time, "sleep", lambda s: None)
    c1 = materializar(db, ASOF)["stats"]["camada1"]
    total = db.trecho_bucket_diario.count_documents({})
    assert (c1["inseridos"], c1["atualizados"], c1["tentativas"]) == (total, 0, 2)


def test_run_anterior_com_raw_vazia_nao_cega_o_watermark(db):
    """Revisão: watermark None no run anterior não pode desligar a detecção de atrasos."""
    guardadas = list(db.trecho_observacoes.find())
    db.trecho_observacoes.delete_many({})
    materializar(db, ASOF)                      # raw vazia: watermark None
    db.trecho_observacoes.insert_many(guardadas)  # histórico chega depois, dias antigos
    run = materializar(db, ASOF)
    assert run["stats"]["camada1"]["atrasadosForaDaJanelaK"] > 0
    assert db.trecho_media_historica.find_one({**A, "dow": 6, "turno": "N"})["n"] == 3


def test_lease_perdido_para_antes_de_apagar(db, monkeypatch):
    import frota.job as job
    original = job.executar_camada2

    def outro_assume(db_, *a, **k):
        db_.job_locks.update_one({"_id": job.LOCK_ID}, {"$set": {"owner": "intruso"}})
        return original(db_, *a, **k)
    monkeypatch.setattr(job, "executar_camada2", outro_assume)
    materializar(db, ASOF, camada="1")
    with pytest.raises(job.LockPerdido):
        materializar(db, ASOF, camada="2")
    assert db.job_runs.find_one(sort=[("iniciadoEm", -1)])["status"] == "erro"


def test_reenvio_do_mesmo_dia_nao_duplica(db):
    from frota.gerador import inserir
    docs = [dict(o) for o in db.trecho_observacoes.find({}, {"_id": 0})]
    antes = db.trecho_observacoes.count_documents({})
    inserir(db, docs)
    assert db.trecho_observacoes.count_documents({}) == antes


def test_atrasado_em_trecho_inexistente_e_recusado(db):
    from frota.simulacao import injetar_atrasado
    with pytest.raises(ValueError):
        injetar_atrasado(db, ASOF, "BASE-001", "POSTO-NAO-EXISTE", "BITREM")
