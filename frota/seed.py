"""Carga completa de um perfil sintético (usado por `make seed` e pelos testes)."""
from __future__ import annotations

import time
from datetime import date, timedelta

from pymongo.database import Database

from . import config as config_mod
from .bootstrap import bootstrap, limpar_dados
from .db import guardar_escrita
from .gerador import PERFIS, Malha, gerar_dia, gerar_malha, inserir
from .janela import hoje_local, inicio_dia, parse_asof


def seed(db: Database, perfil: str, seed_n: int, asof: str | date | None = None,
         dias: int | None = None, log=print) -> dict:
    guardar_escrita(db.name)
    bootstrap(db)
    cfg = config_mod.ler(db)
    asof_d = parse_asof(asof) if asof else hoje_local(cfg["timezone"])
    n_dias = dias or PERFIS[perfil]["dias"]
    limpar_dados(db)
    malha = gerar_malha(perfil, seed_n)
    for nome in ("pontos", "tipos_veiculo", "veiculos", "trechos"):
        db[nome].insert_many(malha[nome])
    m = Malha.do_banco(db)
    t0, total, taxas = time.perf_counter(), 0, []
    primeiro = asof_d - timedelta(days=n_dias - 1)
    # relógio simulado = fim do dia asOf: o dia de hoje inteiro já existe na raw (e
    # precisa ser excluído das médias); atrasos que "chegam" depois ficam pendentes
    relogio = inicio_dia(asof_d + timedelta(days=1), cfg["timezone"])
    for i in range(n_dias):  # inclui o dia de hoje (asOf), que nunca entra nas médias
        dia = primeiro + timedelta(days=i)
        docs = gerar_dia(m, dia, seed_n, cfg["timezone"], cfg["kReprocessamento"])
        taxas.append(inserir(db, docs, relogio))
        total += len(docs)
        if log and (i % 20 == 0 or i == n_dias - 1):
            log(f"  {dia}  {total:>10,} observações")
    dur = time.perf_counter() - t0
    resumo = {"perfil": perfil, "asOf": asof_d.isoformat(), "dias": n_dias,
              "primeiroDia": primeiro.isoformat(),
              "pontos": len(malha["pontos"]), "veiculos": len(malha["veiculos"]),
              "trechos": len(malha["trechos"]),
              "observacoes": db.trecho_observacoes.estimated_document_count(),
              "pendentesDeIngestao": db.ingestao_pendente.estimated_document_count(),
              "segundos": round(dur, 1), "docsPorSegundo": round(total / dur)}
    return resumo
