"""Camada 1: raw → buckets (dia local × hora local)."""
from __future__ import annotations

from frota.job import materializar
from tests.fixtures.dataset import ASOF, sp

NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0}


def buckets(db, **filtro):
    return list(db.trecho_bucket_diario.find(filtro, NEG).sort([("dataLocal", 1), ("hora", 1)]))


def test_carga_inicial_gera_buckets_por_dia_e_hora_local(db):
    run = materializar(db, ASOF, camada="1")
    assert run["status"] == "ok"
    a = buckets(db, origem="BASE-001", destino="POSTO-0042", tipoVeiculo="BITREM")
    chaves = [(b["dataLocal"], b["hora"], b["n"], b["somaMin"]) for b in a]
    assert chaves == [
        (sp(2026, 4, 19), 0, 1, 30.0),
        (sp(2026, 9, 25), 20, 1, 50.0),
        (sp(2026, 10, 2), 20, 1, 56.0),
        (sp(2026, 10, 9), 20, 1, 62.0),
        (sp(2026, 10, 10), 1, 1, 70.0),
        (sp(2026, 10, 15), 23, 1, 45.0),
    ]
    assert {b["dowCivil"] for b in a if b["dataLocal"] == sp(2026, 10, 10)} == {7}


def test_hoje_e_d181_nao_viram_bucket(db):
    materializar(db, ASOF, camada="1")
    assert db.trecho_bucket_diario.count_documents({"somaMin": {"$gte": 999}}) == 0
    assert db.trecho_bucket_diario.count_documents({"dataLocal": {"$gte": sp(2026, 10, 16)}}) == 0
    assert db.trecho_bucket_diario.count_documents({"dataLocal": {"$lt": sp(2026, 4, 19)}}) == 0


def test_fuso_23h30_sp_cai_no_dia_e_hora_locais(db):
    """23:30 SP de 13/10 = 02:30 UTC de 14/10. O bucket é 13/10, hora 23 — não 14/10 hora 2."""
    materializar(db, ASOF, camada="1")
    b = buckets(db, origem="BASE-001", destino="POSTO-0007", tipoVeiculo="CARRETA", hora=23)
    assert len(b) == 1
    assert b[0]["dataLocal"] == sp(2026, 10, 13)
    assert b[0]["dowCivil"] == 3  # terça
    assert db.trecho_bucket_diario.count_documents({"destino": "POSTO-0007", "hora": 2}) == 0


def test_bucket_guarda_soma_contagem_min_max(db):
    from tests.fixtures.dataset import obs
    db.trecho_observacoes.insert_one(
        obs("EXTRA", "BASE-001", "POSTO-0042", "BITREM", sp(2026, 10, 9, 20, 40), 70, 43))
    materializar(db, ASOF, camada="1")
    b = buckets(db, destino="POSTO-0042", dataLocal=sp(2026, 10, 9), hora=20)[0]
    assert (b["n"], b["somaMin"], b["somaKm"], b["minMin"], b["maxMin"]) == (2, 132, 84, 62, 70)


def test_reexecucao_idempotente_byte_a_byte(db):
    materializar(db, ASOF, camada="1")
    antes = buckets(db)
    run2 = materializar(db, ASOF, camada="1")
    assert buckets(db) == antes
    assert run2["stats"]["camada1"]["inseridos"] == 0  # só D-1…D-k relidos e substituídos


def test_segundo_run_e_incremental_d1_a_dk(db):
    materializar(db, ASOF, camada="1")
    run2 = materializar(db, ASOF, camada="1")
    c1 = run2["stats"]["camada1"]
    assert c1["modo"] == "incremental"
    assert c1["diasReprocessados"] == ["2026-10-13", "2026-10-14", "2026-10-15"]


def test_bucket_que_deixou_de_existir_na_raw_e_removido(db):
    materializar(db, ASOF, camada="1")
    db.trecho_observacoes.delete_many({"viagemId": "VIA-FIX-A8"})  # D-1, dentro de k
    run = materializar(db, ASOF, camada="1")
    assert run["stats"]["camada1"]["removidos"] == 1
    assert buckets(db, dataLocal=sp(2026, 10, 15)) == []
