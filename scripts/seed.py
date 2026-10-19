"""Recria o banco da demo em torno de agora (reset). Exige ALLOW_DEMO_DB_WRITE=1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import _path  # noqa: F401

from frota import settings
from frota.db import get_db
from frota.gerador import PERFIS
from frota.seed import resetar

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.MONGODB_DB)
    ap.add_argument("--profile", default="demo", choices=sorted(PERFIS))
    ap.add_argument("--seed", type=int, default=settings.SEED)
    a = ap.parse_args()
    r = resetar(get_db(a.db), datetime.now(timezone.utc), a.seed, perfil=a.profile,
                progresso=lambda e, p: print(f"  {e} {p:.0%}"))
    print(json.dumps(r, ensure_ascii=False, indent=2))
