"""Equivalência: média do agregado == média on-the-fly na raw, mesma janela.

Roda sobre o perfil sintético `teste` (gerador completo, com atrasos e outliers),
numa amostra aleatória de chaves com seed fixa.
"""
from __future__ import annotations

import random

import pytest

from frota import config as config_mod
from frota.bootstrap import bootstrap
from frota.db import get_db
from frota.gerador import Malha, gerar_dia
from frota.job import materializar
from frota.janela import janela
from frota.pipelines import estagios, raw_onthefly
from frota.seed import seed
from frota.simulacao import avancar

ASOF = "2026-10-16"
DB = "frota_eta_equiv_test"


@pytest.fixture(scope="module")
def gerado():
    db = get_db(DB)
    db.config.delete_many({})
    bootstrap(db)
    resumo = seed(db, "teste", 42, ASOF, log=None)
    materializar(db, ASOF)
    return db, resumo


def _comparar(db, amostra: int, semente: int):
    cfg = config_mod.ler(db)
    ji, jf = janela(cfg_asof(db), cfg)
    pares = sorted({(d["origem"], d["destino"], d["tipoVeiculo"])
                    for d in db.trecho_media_historica.find({}, {"_id": 0, "origem": 1,
                                                                 "destino": 1, "tipoVeiculo": 1})})
    sorteados = random.Random(semente).sample(pares, min(amostra, len(pares)))
    comparados = 0
    for o, d, t in sorteados:
        mat = {(x["dow"], x["turno"]): x for x in db.trecho_media_historica.find(
            {"origem": o, "destino": d, "tipoVeiculo": t})}
        raw = {(x["dow"], x["turno"]): x for x in db.trecho_observacoes.aggregate(
            estagios(raw_onthefly.pipeline(o, d, t, ji, jf, cfg)))}
        assert mat.keys() == raw.keys(), (o, d, t)
        for k, m in mat.items():
            assert m["n"] == raw[k]["n"]
            assert m["mediaMin"] == pytest.approx(raw[k]["somaMin"] / raw[k]["n"], rel=1e-9)
            assert m["mediaKm"] == pytest.approx(raw[k]["somaKm"] / raw[k]["n"], rel=1e-9)
            comparados += 1
    return comparados


def cfg_asof(db):
    return db.trecho_media_historica.find_one()["asOf"]


def test_gerador_e_deterministico(gerado):
    db, _ = gerado
    m = Malha.do_banco(db)
    from datetime import date
    a = gerar_dia(m, date(2026, 10, 1), 42, "America/Sao_Paulo")
    b = gerar_dia(m, date(2026, 10, 1), 42, "America/Sao_Paulo")
    assert a == b and len(a) > 0


def test_perfil_gera_atrasos_e_hoje(gerado):
    db, resumo = gerado
    assert resumo["observacoes"] > 1000
    from frota.janela import inicio_dia
    from datetime import date
    hoje = inicio_dia(date(2026, 10, 16), "America/Sao_Paulo")
    assert db.trecho_observacoes.count_documents({"observadoEm": {"$gte": hoje}}) > 0


def test_equivalencia_dia_civil(gerado):
    db, _ = gerado
    assert _comparar(db, amostra=25, semente=7) > 25


def test_equivalencia_dia_operacional_e_apos_avancar(gerado):
    db, _ = gerado
    config_mod.atualizar(db, {"regraNoite": "dia_operacional"})
    materializar(db, ASOF, camada="2")
    assert _comparar(db, amostra=25, semente=11) > 25
    avancar(db, 2)  # dias novos + atrasados chegando + job incremental
    assert cfg_asof(db) == "2026-10-18"
    assert _comparar(db, amostra=25, semente=13) > 25
