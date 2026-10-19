"""Job diário de materialização. Em produção quem chama é o Scheduled Trigger.

    python jobs/materializar.py [--data YYYY-MM-DD] [--db frota_eta]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.db import get_db  # noqa: E402
from frota.janela import hoje_local  # noqa: E402
from frota.job import rodar_job  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="YYYY-MM-DD (padrão: hoje em America/Sao_Paulo)")
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    db = get_db(a.db)
    bootstrap(db)
    ref = date.fromisoformat(a.data) if a.data else hoje_local(datetime.now(timezone.utc))
    r = rodar_job(db, ref, origem="cli")
    r.pop("pipeline")
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
