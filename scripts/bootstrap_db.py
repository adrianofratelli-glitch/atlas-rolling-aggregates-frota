"""Cria collections, validators e índices; imprime `listIndexes` ao final."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.db import get_db  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    db = get_db(a.db)
    print(f"bootstrap em {a.db} · alvo {settings.ALVO} · MongoDB {db.client.server_info()['version']}")
    bootstrap(db, verbose=True)
