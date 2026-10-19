"""Lista (e, com --confirmar, remove) bancos de teste/bench da POV e sobras da v1 em frota_eta.

Só toca bancos que começam com `frota_eta`; `frota_eta` em si nunca é dropado (só collections
fora de frota.schemas.VALIDATORS). Não imprime host nem URI.
"""
import _path  # noqa: F401
import argparse

from frota import settings
from frota.db import client, get_db
from frota.schemas import VALIDATORS

DEMO = "frota_eta"  # literal: nunca é dropado, independente de env


def selecionar_bancos(nomes: list[str]) -> list[str]:
    """Allowlist exata: frota_eta_bench e frota_eta_*_test. A demo nunca entra."""
    return sorted(n for n in nomes if n != DEMO and (
        n == "frota_eta_bench" or (n.startswith("frota_eta_") and n.endswith("_test"))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirmar", action="store_true", help="executa o drop (padrão: só lista)")
    a = ap.parse_args()
    c = client()
    alvo_bancos = selecionar_bancos(c.list_database_names())
    sobras = []
    db = get_db(DEMO)
    for nome in sorted(db.list_collection_names()):
        if nome not in VALIDATORS and not nome.startswith("system."):
            sobras.append((nome, db[nome].estimated_document_count()))
    print(f"alvo: {settings.ALVO} | {'EXECUTANDO' if a.confirmar else 'dry-run'}")
    for n in alvo_bancos:
        d = c[n]
        cols = {k: d[k].estimated_document_count() for k in d.list_collection_names()}
        print(f"banco {n}: {cols}")
        if a.confirmar:
            c.drop_database(n)
            print(f"  dropado {n}")
    for nome, n in sobras:
        print(f"{DEMO}.{nome}: {n} docs (fora do schema v2)")
        if a.confirmar:
            db.drop_collection(nome)
            print(f"  dropada {nome}")
    if not alvo_bancos and not sobras:
        print("nada a limpar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
