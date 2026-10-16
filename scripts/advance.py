"""Simula a passagem de N dias: gera os dias novos e roda o job com asOf avançado."""
from __future__ import annotations

import argparse

import _path  # noqa: F401

from frota import settings
from frota.db import get_db
from frota.simulacao import avancar

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    for p in avancar(get_db(a.db), a.days):
        c1, c2 = p["run"]["stats"]["camada1"], p["run"]["stats"]["camada2"]
        print(f"asOf {p['asOf']}: +{p['observacoesGeradas']} obs geradas, {p['atrasadosLiberados']} atrasadas chegaram · entra {p['diaQueEntra']} · "
              f"sai {p['diaQueSai']} · atrasados fora de k {c1['atrasadosForaDaJanelaK']} · buckets +{c1['inseridos']}/~{c1['atualizados']}/-{c1['removidos']} · "
              f"médias +{c2['inseridos']}/~{c2['atualizados']}/-{c2['removidos']}")
