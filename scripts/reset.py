"""Esvazia as collections de dados e restaura a config default (validators/índices ficam)."""
from __future__ import annotations

import argparse

import _path  # noqa: F401

from frota import settings
from frota.bootstrap import bootstrap, limpar_dados
from frota.db import get_db, guardar_escrita

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    guardar_escrita(a.db)
    db = get_db(a.db)
    limpar_dados(db)
    db.config.delete_many({})
    db.config_versoes.delete_many({})
    bootstrap(db)
    print(f"{a.db}: dados removidos, config restaurada ao default do .env")
