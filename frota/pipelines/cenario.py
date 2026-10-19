"""Pipelines dos cenários: somar a base pronta ou agregar a raw sob demanda.

Na janela padrão a resposta sai da soma de documentos já materializados pelo job (poucos
docs, sem recalcular nada). Fora dela, ou com um veículo específico, o mesmo cálculo roda
na raw; se o usuário pedir para
salvar, o `$merge` é o último estágio do próprio aggregate que calcula o resultado.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from frota.settings import TZ

from . import Estagio
from .job import COLECAO as BASE

if TYPE_CHECKING:
    from frota.cenario import Filtro

RAW = "trecho_observacoes"
SALVOS = "consultas_salvas"

_SOMAS = {"somaMin": {"$sum": "$tempoMin"},
          "somaQuadMin": {"$sum": {"$multiply": ["$tempoMin", "$tempoMin"]}},
          "somaKm": {"$sum": "$distanciaKm"}}


def _rota(f: "Filtro") -> dict:
    return {"origem": f.origem, "destino": f.destino, "tipoVeiculo": f.tipoVeiculo}


def base(f: "Filtro", dias: list[int], horas: list[int]) -> list[Estagio]:
    return [
        Estagio("Pega na base pronta só a rota e o tipo de veículo pedidos, nos dias da semana "
                "e nas horas escolhidos.",
                {"$match": {**_rota(f), "dow": {"$in": dias}, "hora": {"$in": horas}}}),
        Estagio("Soma as contagens e as somas guardadas pelo job e conta quantos documentos "
                "prontos foram somados.",
                {"$group": {"_id": None, "n": {"$sum": "$n"}, "somaMin": {"$sum": "$somaMin"},
                            "somaQuadMin": {"$sum": "$somaQuadMin"},
                            "somaKm": {"$sum": "$somaKm"}, "docs": {"$sum": 1}}}),
    ]


def raw(f: "Filtro", inicio: datetime, fim: datetime, horas: list[int],
        salvar_em: dict | None) -> list[Estagio]:
    """`salvar_em` = {"_id": chave, "periodo": "absoluto"|"relativo", "expiraEm": datetime}."""
    filtro = {**_rota(f), **({"veiculoId": f.veiculoId} if f.veiculoId else {}),
              "observadoEm": {"$gte": inicio, "$lt": fim}}
    quem = "do veículo escolhido" if f.veiculoId else "do tipo de veículo"
    p = [
        Estagio(f"Pega as observações da rota e {quem} no período pedido (o fim fica de fora).",
                {"$match": filtro}),
        Estagio("Descobre o dia da semana (1 = segunda … 7 = domingo) e a hora, no horário de São Paulo.",
                {"$set": {"dow": {"$isoDayOfWeek": {"date": "$observadoEm", "timezone": TZ}},
                          "hora": {"$hour": {"date": "$observadoEm", "timezone": TZ}}}}),
        Estagio("Fica só com os dias da semana e as horas escolhidos.",
                {"$match": {"dow": {"$in": f.dias_ordenados()}, "hora": {"$in": horas}}}),
        Estagio("Junta tudo num único resultado com contagem e somas.",
                {"$group": {"_id": None, "n": {"$sum": 1}, **_SOMAS}}),
    ]
    proj = {"_id": {"$literal": salvar_em["_id"]} if salvar_em else 0,
            "n": 1,
            "somaMin": {"$round": ["$somaMin", 6]},
            "somaQuadMin": {"$round": ["$somaQuadMin", 6]},
            "somaKm": {"$round": ["$somaKm", 6]}}
    if salvar_em:
        proj.update({
            "filtro": {"$literal": f.descricao()},
            "periodo": {"$literal": salvar_em["periodo"]},
            "criadoEm": "$$NOW",
            "expiraEm": {"$literal": salvar_em["expiraEm"]},
        })
    p.append(Estagio("Arredonda as somas" + (", identifica a consulta pela chave do filtro e "
                                             "marca até quando ela vale." if salvar_em else "."),
                     {"$project": proj}))
    if salvar_em:
        p.append(Estagio("Grava o resultado em consultas_salvas: a mesma consulta substitui a "
                         "anterior; o índice TTL apaga o documento quando passa do expiraEm.",
                         {"$merge": {"into": SALVOS, "on": "_id",
                                     "whenMatched": "replace", "whenNotMatched": "insert"}}))
    return p
