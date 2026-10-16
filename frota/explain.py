"""Leitura do `explain("executionStats")` real — nada estimado."""
from __future__ import annotations

from typing import Any

from pymongo.database import Database


def _achar(no: Any, chave: str) -> list:
    achados = []
    if isinstance(no, dict):
        if chave in no:
            achados.append(no[chave])
        for v in no.values():
            achados.extend(_achar(v, chave))
    elif isinstance(no, list):
        for v in no:
            achados.extend(_achar(v, chave))
    return achados


def _cadeia(plano: dict | None) -> list[str]:
    """Estágios do plano vencedor, da raiz para a folha (inclui SBE `queryPlan`)."""
    saida, no = [], plano
    while isinstance(no, dict):
        if "queryPlan" in no:
            no = no["queryPlan"]
            continue
        if "stage" in no:
            rotulo = no["stage"]
            if no.get("indexName"):
                rotulo += f" {no['indexName']}"
            saida.append(rotulo)
        no = no.get("inputStage") or (no.get("inputStages") or [None])[0]
    return saida


def resumir(bruto: dict) -> dict:
    stats = [s for s in _achar(bruto, "executionStats") if isinstance(s, dict)
             and "totalDocsExamined" in s]
    planos = _achar(bruto, "winningPlan")
    es = stats[0] if stats else {}
    cadeia = _cadeia(planos[0]) if planos else []
    return {
        "estagioVencedor": " → ".join(cadeia) if cadeia else None,
        "usaIndice": any(s.startswith("IXSCAN") or s.startswith("EXPRESS") for s in cadeia),
        "indices": sorted({s.split(" ", 1)[1] for s in cadeia if " " in s}),
        "totalKeysExamined": es.get("totalKeysExamined"),
        "totalDocsExamined": es.get("totalDocsExamined"),
        "nReturned": es.get("nReturned"),
        "executionTimeMillis": es.get("executionTimeMillis"),
    }


def explain_find(db: Database, colecao: str, filtro: dict) -> dict:
    bruto = db.command({"explain": {"find": colecao, "filter": filtro},
                        "verbosity": "executionStats"})
    return {**resumir(bruto), "bruto": bruto}


def explain_aggregate(db: Database, colecao: str, pipeline: list[dict]) -> dict:
    bruto = db.command({"explain": {"aggregate": colecao, "pipeline": pipeline, "cursor": {}},
                        "verbosity": "executionStats"})
    return {**resumir(bruto), "bruto": bruto}
