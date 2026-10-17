"""Expressões de turno e dia da semana geradas a partir da `config`.

As mesmas funções servem à camada 2 (que parte de `hora`/`dowCivil` do bucket) e à
consulta on-the-fly na raw (que parte de `observadoEm`) — por isso a comparação
raw vs materializado responde exatamente a mesma pergunta.
"""
from __future__ import annotations

from ..janela import corte_madrugada, turno_cruza_meia_noite


def expr_turno(turnos: list[dict], hora: str | dict = "$hora") -> dict:
    """`$switch` hora → código do turno. O turno que cruza a meia-noite vira `default`."""
    ramos, cruza = [], [t for t in turnos if turno_cruza_meia_noite(t)]
    for t in turnos:
        if turno_cruza_meia_noite(t):
            continue
        ramos.append({"case": {"$and": [{"$gte": [hora, t["inicioHora"]]},
                                         {"$lt": [hora, t["fimHora"]]}]},
                      "then": t["codigo"]})
    if cruza:
        return {"$switch": {"branches": ramos, "default": cruza[0]["codigo"]}}
    return {"$switch": {"branches": ramos}}


def expr_dow(cfg: dict, dow_civil: str | dict = "$dowCivil", hora: str | dict = "$hora"):
    """dow da chave. `dia_operacional`: madrugada conta no dia anterior (1(dom)→7, 7→6).

    Com `incluirDow = false` a chave é só o turno: dow 0 ("todos os dias")."""
    if not cfg.get("incluirDow", True):
        return {"$literal": 0}
    if cfg["regraNoite"] != "dia_operacional":
        return dow_civil
    corte = corte_madrugada(cfg["turnos"])
    return {"$cond": [{"$lt": [hora, corte]},
                      {"$add": [{"$mod": [{"$add": [dow_civil, 5]}, 7]}, 1]},
                      dow_civil]}


def set_hora_dow_civil(tz: str) -> dict:
    """Hora e dia da semana locais de cada observação (sem relógio do sistema)."""
    return {"$set": {"hora": {"$hour": {"date": "$observadoEm", "timezone": tz}},
                     "dowCivil": {"$dayOfWeek": {"date": "$observadoEm", "timezone": tz}}}}
