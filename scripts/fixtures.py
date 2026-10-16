"""Carrega o dataset determinístico de `tests/fixtures` e materializa com asOf 2026-10-16."""
from __future__ import annotations

import argparse

import _path  # noqa: F401

from frota import settings
from frota.bootstrap import bootstrap
from frota.db import get_db, guardar_escrita
from frota.job import materializar
from tests.fixtures import dataset

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.MONGODB_FIXTURES_DB)
    a = ap.parse_args()
    guardar_escrita(a.db)
    db = get_db(a.db)
    bootstrap(db)
    dataset.carregar(db)
    run = materializar(db, dataset.ASOF)
    print(f"{a.db}: {db.trecho_observacoes.count_documents({})} observações, "
          f"{db.trecho_bucket_diario.count_documents({})} buckets, "
          f"{db.trecho_media_historica.count_documents({})} médias (asOf {dataset.ASOF}, "
          f"run {run['runId']})")
