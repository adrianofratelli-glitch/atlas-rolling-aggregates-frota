"""Roda uma rodada da ingestão simulada (o que a trigger faz de hora em hora)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import _path  # noqa: F401

from frota import settings
from frota.db import get_db
from frota.ingestao import ingerir

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    print(json.dumps(ingerir(get_db(a.db), datetime.now(timezone.utc)), ensure_ascii=False, default=str, indent=2))
