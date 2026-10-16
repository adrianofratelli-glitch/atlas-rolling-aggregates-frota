"""Pipelines comentados estágio a estágio.

Cada builder devolve uma lista de `Estagio(comentario, estagio)`. O driver recebe só
`estagios(...)`; a UI e `docs/pipelines/*.json` recebem os comentários junto, então o
que aparece na tela é exatamente o que foi enviado, estágio por estágio.
"""
from __future__ import annotations

from typing import NamedTuple


class Estagio(NamedTuple):
    comentario: str
    estagio: dict


def estagios(pipeline: list[Estagio]) -> list[dict]:
    return [e.estagio for e in pipeline]


def comentados(pipeline: list[Estagio]) -> list[dict]:
    return [{"comentario": e.comentario, "estagio": e.estagio} for e in pipeline]
