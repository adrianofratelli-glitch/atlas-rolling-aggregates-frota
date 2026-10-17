"""Modo simples — raw → média histórica num pipeline só (a "MV com COMPLETE refresh").

Relê a janela inteira a cada run e troca a collection com `$out`. Dado atrasado entra
sozinho no run seguinte; não há buckets, k de reprocessamento nem watermark. No
benchmark `escala` (Atlas M30) foi o caminho mais rápido: ~36 s para 1,86 M observações.
"""
from __future__ import annotations

from datetime import datetime

from . import Estagio
from .camada1 import PRECISAO
from .camada2 import COLECAO_DESTINO
from .expressoes import expr_dow, expr_turno, set_hora_dow_civil


def pipeline(janela_inicio: datetime, janela_fim: datetime, asof: str, cfg: dict,
             run_id: str) -> list[Estagio]:
    tz = cfg["timezone"]
    return [
        Estagio(
            "Toda a janela [início, fim) — semiaberta, sem $lte; hoje fica fora porque fim = "
            "00:00 local de asOf. Usa o índice { observadoEm: 1 }.",
            {"$match": {"observadoEm": {"$gte": janela_inicio, "$lt": janela_fim}}},
        ),
        Estagio("Hora e dia da semana locais (timezone da config), por observação.",
                set_hora_dow_civil(tz)),
        Estagio(
            f"Turno gerado de config.turnos v{cfg['versao']}; dow pela regraNoite = "
            f"{cfg['regraNoite']}" + ("" if cfg.get("incluirDow", True) else
                                     " (incluirDow = false: dow 0, chave só por turno)") + ".",
            {"$set": {"turno": expr_turno(cfg["turnos"]), "dow": expr_dow(cfg)}},
        ),
        Estagio(
            "Chave sem data: { origem, destino, tipoVeiculo, dow, turno }. Soma e contagem "
            "guardadas para que turno/geral sejam somas corretas na consulta.",
            {"$group": {
                "_id": {"origem": "$origem", "destino": "$destino",
                        "tipoVeiculo": "$tipoVeiculo", "dow": "$dow", "turno": "$turno"},
                "somaMin": {"$sum": "$tempoMin"}, "somaKm": {"$sum": "$distanciaKm"},
                "n": {"$sum": 1},
            }},
        ),
        Estagio(
            "Média calculada uma vez aqui (somas a 6 casas: $sum de doubles depende da ordem).",
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
        Estagio(
            "Troca atômica da collection (preserva índices e validator): leitores veem a "
            "versão anterior ou a nova; chaves fora da janela deixam de existir.",
            {"$out": COLECAO_DESTINO},
        ),
    ]
