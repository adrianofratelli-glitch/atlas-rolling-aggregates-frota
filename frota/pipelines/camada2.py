"""Camada 2 — buckets → média histórica por dow × turno (o "materialized view")."""
from __future__ import annotations

from datetime import datetime

from . import Estagio
from .camada1 import PRECISAO
from .expressoes import expr_dow, expr_turno

COLECAO_DESTINO = "trecho_media_historica"
CHAVE_MEDIA = ["origem", "destino", "tipoVeiculo", "dow", "turno"]


def pipeline(janela_inicio: datetime, janela_fim: datetime, asof: str, cfg: dict,
             run_id: str) -> list[Estagio]:
    modo = cfg["modoLimpezaCamada2"]
    final = (
        Estagio(
            "merge_runid: upsert pela chave única do agregado (replace = idempotente). "
            "Chaves que saíram da janela são apagadas depois por runId ≠ atual.",
            {"$merge": {"into": COLECAO_DESTINO, "on": CHAVE_MEDIA,
                        "whenMatched": "replace", "whenNotMatched": "insert"}},
        ) if modo == "merge_runid" else
        Estagio(
            "out: troca atômica da collection inteira pelo resultado (preserva índices "
            "e opções). Chaves fora da janela simplesmente deixam de existir.",
            {"$out": COLECAO_DESTINO},
        )
    )
    return [
        Estagio(
            "Recorte da janela móvel sobre o dia local do bucket: [início, fim) "
            "semiaberto, sem $lte. Usa o índice { dataLocal: 1 }. O dia de hoje nunca "
            "entra porque fim = 00:00 local de asOf.",
            {"$match": {"dataLocal": {"$gte": janela_inicio, "$lt": janela_fim}}},
        ),
        Estagio(
            f"Deriva turno da hora local (gerado de config.turnos v{cfg['versao']}) e "
            f"dow conforme regraNoite = {cfg['regraNoite']}. Nenhum dado da raw é relido.",
            {"$set": {"turno": expr_turno(cfg["turnos"]), "dow": expr_dow(cfg)}},
        ),
        Estagio(
            "Chave sem data: 'toda sexta à noite' = { dow: 6, turno: 'N' } soma todas as "
            "sextas da janela. Soma de somas e de contagens (Computed Pattern).",
            {"$group": {
                "_id": {"origem": "$origem", "destino": "$destino",
                        "tipoVeiculo": "$tipoVeiculo", "dow": "$dow", "turno": "$turno"},
                "somaMin": {"$sum": "$somaMin"}, "somaKm": {"$sum": "$somaKm"},
                "n": {"$sum": "$n"},
            }},
        ),
        Estagio(
            "Média = soma / contagem, calculada uma vez aqui e não na consulta (somas "
            "arredondadas a 6 casas, como na camada 1). Grava janela, asOf e versão da config.",
            {"$project": {
                "_id": 0,
                "origem": "$_id.origem", "destino": "$_id.destino",
                "tipoVeiculo": "$_id.tipoVeiculo", "dow": "$_id.dow", "turno": "$_id.turno",
                "somaMin": {"$round": ["$somaMin", PRECISAO]},
                "somaKm": {"$round": ["$somaKm", PRECISAO]}, "n": 1,
                "mediaMin": {"$divide": [{"$round": ["$somaMin", PRECISAO]}, "$n"]},
                "mediaKm": {"$divide": [{"$round": ["$somaKm", PRECISAO]}, "$n"]},
                "janelaInicio": {"$literal": janela_inicio},
                "janelaFim": {"$literal": janela_fim},
                "asOf": {"$literal": asof}, "configVersao": {"$literal": cfg["versao"]},
                "runId": {"$literal": run_id}, "atualizadoEm": "$$NOW",
            }},
        ),
        final,
    ]
