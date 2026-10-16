"""Job de materialização. Em produção é isto que o agendador chama.

    python jobs/materializar.py --asof 2026-10-16 [--camada 1|2|todas] [--db frota_eta]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.db import get_db  # noqa: E402
from frota.job import LockOcupado, materializar  # noqa: E402


def _resumo(run: dict) -> dict:
    s = run["stats"]
    saida = {"runId": run["runId"], "asOf": run["asOf"], "camada": run["camada"],
             "status": run["status"], "atrasadosForaDaJanelaK": run["atrasadosForaDaJanelaK"]}
    for c in ("camada1", "camada2"):
        if c in s:
            saida[c] = {k: v for k, v in s[c].items()
                        if k not in ("removidosAmostra", "pipeline", "diasReprocessados", "watermarkIngeridoEm",
                                     "janelaInicio", "janelaFim")}
            if c == "camada1":
                dias = s[c]["diasReprocessados"]
                saida[c]["diasReprocessados"] = (dias if len(dias) <= 6
                                                 else f"{len(dias)} dias ({dias[0]} … {dias[-1]})")
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", help="YYYY-MM-DD (default: hoje em America/Sao_Paulo)")
    ap.add_argument("--camada", default="todas", choices=["1", "2", "todas"])
    ap.add_argument("--db", default=settings.MONGODB_DB)
    a = ap.parse_args()
    db = get_db(a.db)
    bootstrap(db)
    try:
        run = materializar(db, a.asof, a.camada)
    except LockOcupado as e:
        print(f"job recusado: {e}", file=sys.stderr)
        sys.exit(3)
    print(json.dumps(_resumo(run), ensure_ascii=False, indent=2, default=str))
