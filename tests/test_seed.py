"""Gerador determinístico e reset pela data do clique."""
from __future__ import annotations

import sys
import types
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

import frota
from frota import seed as seed_mod
from frota.db import EscritaRecusada, get_db
from frota.gerador import FATOR_TIPO, gerar
from frota.janela import hoje_local, inicio_dia

AGORA = datetime(2026, 10, 19, 15, 20, tzinfo=timezone.utc)


def test_gerador_deterministico():
    assert gerar(AGORA, 7, "teste") == gerar(AGORA, 7, "teste")


def test_gerador_sem_futuro_na_raw():
    g = gerar(AGORA, 1, "teste")
    assert g["observacoes"] and g["futuras"]
    assert all(o["observadoEm"] < AGORA for o in g["observacoes"])
    assert all(AGORA <= o["observadoEm"] < AGORA + timedelta(days=14) for o in g["futuras"])
    ids = [(o["viagemId"], o["seq"]) for o in g["observacoes"] + g["futuras"]]
    assert len(ids) == len(set(ids))


def test_cobertura_regulares():
    g = gerar(AGORA, 1, "teste")
    reg = {t["_id"] for t in g["trechos"] if not t["esparso"]}
    hoje = hoje_local(AGORA)
    ini, fim = inicio_dia(hoje - timedelta(days=35)), inicio_dia(hoje)
    from zoneinfo import ZoneInfo
    c = Counter()
    for o in g["observacoes"]:
        if f"{o['origem']}|{o['destino']}" in reg and ini <= o["observadoEm"] < fim:
            l = o["observadoEm"].astimezone(ZoneInfo("America/Sao_Paulo"))
            c[(o["origem"], o["destino"], o["tipoVeiculo"], l.isoweekday(), l.hour)] += 1
    assert len(c) == len(reg) * 2 * 7 * 24
    assert min(c.values()) >= 5


def test_esparsos_tem_celulas_raras():
    g = gerar(AGORA, 1, "teste")
    esp = {f"{t['origem']}|{t['destino']}" for t in g["trechos"] if t["esparso"]}
    assert esp
    obs = [o for o in g["observacoes"] if f"{o['origem']}|{o['destino']}" in esp]
    assert 0 < len(obs) < 0.1 * 40 * 24 * 2 * len(esp)


def test_perfil_demo_formato():
    g = gerar(AGORA, 42, "demo")
    assert len(g["trechos"]) == 60 and sum(t["esparso"] for t in g["trechos"]) == 2
    assert sum(p["tipo"] == "base" for p in g["pontos"]) == 4
    assert sum(p["tipo"] == "posto" for p in g["pontos"]) == 12
    assert 700_000 <= len(g["observacoes"]) <= 900_000
    # N × N: toda base atende todo posto; viagem longa só com os tipos pesados
    ids = {t["_id"] for t in g["trechos"]}
    assert all(f"BASE-00{b}|POSTO-{i}{j}" in ids for b in range(1, 5) for i in range(1, 5) for j in range(1, 4))
    longos = [t for t in g["trechos"] if t["distanciaBaseKm"] >= 120]
    assert longos and all(t["tiposVeiculo"] == ["CARRETA", "BITREM"] for t in longos)
    por_tipo = {}
    for o in g["observacoes"]:
        por_tipo.setdefault(o["tipoVeiculo"], set()).add(o["veiculoId"])
    assert {t: len(v) for t, v in por_tipo.items()} == {t: 15 for t in FATOR_TIPO}
    assert por_tipo["TOCO"] == {f"VEI-TOCO-{i}" for i in range(1, 16)}


def test_veiculos_espalhados_por_trecho_e_hora():
    """Cada veículo aparece em todo trecho regular e em várias horas (sem viés fixo)."""
    g = gerar(AGORA, 1, "teste")
    reg = {t["_id"] for t in g["trechos"] if not t["esparso"]}
    from zoneinfo import ZoneInfo
    z = ZoneInfo("America/Sao_Paulo")
    horas = {}
    for o in g["observacoes"]:
        if f"{o['origem']}|{o['destino']}" in reg:
            horas.setdefault((o["origem"], o["destino"], o["veiculoId"]), set()).add(
                o["observadoEm"].astimezone(z).hour)
    assert len(horas) == len(reg) * 2 * 3
    assert min(len(h) for h in horas.values()) >= 20


def test_resetar_recusa_demo_sem_permissao(monkeypatch):
    monkeypatch.delenv("ALLOW_DEMO_DB_WRITE", raising=False)
    with pytest.raises(EscritaRecusada):
        seed_mod.resetar(get_db("frota_eta"), AGORA, 1)


def test_resetar_popula(db, monkeypatch):
    chamadas = []
    stub = types.SimpleNamespace(rodar_job=lambda d, ref, origem: chamadas.append((ref, origem)))
    monkeypatch.setitem(sys.modules, "frota.job", stub)
    monkeypatch.setattr(frota, "job", stub, raising=False)
    etapas = []
    r = seed_mod.resetar(db, AGORA, 1, perfil="teste", progresso=lambda e, p: etapas.append(e))
    assert db.trecho_observacoes.count_documents({}) == r["observacoes"] > 0
    assert db.ingestao_simulada.count_documents({}) == r["futuras"] > 0
    assert db.trechos.count_documents({}) == r["trechos"]
    assert chamadas == [(hoje_local(AGORA), "reset")] and etapas[-1] == "pronto"
    assert r["simuladoAte"].startswith("2026-11-02")


def test_resetar_progresso_por_lote(db, monkeypatch):
    stub = types.SimpleNamespace(rodar_job=lambda d, ref, origem: None)
    monkeypatch.setitem(sys.modules, "frota.job", stub)
    monkeypatch.setattr(frota, "job", stub, raising=False)
    monkeypatch.setattr(seed_mod, "LOTE", 1_000)  # perfil de teste é pequeno: lotes menores
    marcas = []
    seed_mod.resetar(db, AGORA, 1, perfil="teste", progresso=lambda e, p: marcas.append((e, p)))
    pcts = [p for e, p in marcas if e == "inserindo"]
    assert len(pcts) > 10  # um aviso por lote, não só no começo e no fim
    assert pcts == sorted(pcts) and pcts[0] >= 0.3 and pcts[-1] == pytest.approx(0.85)
    assert max(b - a for a, b in zip(pcts, pcts[1:])) < 0.06
    assert [p for _, p in marcas] == sorted(p for _, p in marcas)
