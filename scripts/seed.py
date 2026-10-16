"""Gera malha, frota e observações sintéticas (seed determinística)."""
from __future__ import annotations

import argparse
import json

import _path  # noqa: F401

from frota import settings
from frota.db import get_db
from frota.gerador import PERFIS
from frota.seed import seed

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="small", choices=sorted(PERFIS))
    ap.add_argument("--db", default=settings.MONGODB_DB)
    ap.add_argument("--asof", help="dia simulado de hoje (default: hoje em SP)")
    ap.add_argument("--dias", type=int)
    ap.add_argument("--seed", type=int, default=settings.SEED)
    a = ap.parse_args()
    db = get_db(a.db)
    print(f"seed perfil={a.profile} db={a.db} seed={a.seed}")
    r = seed(db, a.profile, a.seed, a.asof, a.dias)
    print(json.dumps(r, ensure_ascii=False, indent=2))
