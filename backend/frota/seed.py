"""Reset do banco da demo ao redor do instante do clique.

Apaga os dados (não o banco), recria validators e índices, insere a raw até `agora` e as
observações futuras em `ingestao_simulada`, e roda o job uma vez para a base nascer pronta.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from pymongo.database import Database

from .bootstrap import bootstrap
from .db import guardar_escrita
from .gerador import gerar
from .janela import hoje_local
from .schemas import VALIDATORS
from .settings import DIAS_SIMULADOS

LOTE = 5_000
# a inserção é a etapa longa do reset: o progresso anda de 30% a 85% lote a lote
PCT_INSERCAO = (0.3, 0.85)


def resetar(db: Database, agora: datetime, seed: int, permitir: bool = False,
            progresso: Callable[[str, float], None] | None = None,
            perfil: str = "demo") -> dict:
    guardar_escrita(db.name, permitir)
    p = progresso or (lambda etapa, pct: None)
    p("apagando", 0.0)
    for nome in VALIDATORS:
        db.drop_collection(nome)
    bootstrap(db)
    p("gerando", 0.1)
    g = gerar(agora, seed, perfil)
    p("inserindo", PCT_INSERCAO[0])
    lotes = [(db[nome], g[chave][i:i + LOTE])
             for nome, chave in (("pontos", "pontos"), ("trechos", "trechos"),
                                 ("trecho_observacoes", "observacoes"),
                                 ("ingestao_simulada", "futuras"))
             for i in range(0, len(g[chave]), LOTE)]
    total, feitos = sum(len(docs) for _, docs in lotes), 0
    ini_pct, fim_pct = PCT_INSERCAO
    for coll, docs in lotes:
        coll.insert_many(docs, ordered=False)
        feitos += len(docs)
        p("inserindo", ini_pct + (fim_pct - ini_pct) * feitos / total)
    p("job", 0.9)
    from . import job  # import tardio: o job é da etapa seguinte
    job.rodar_job(db, hoje_local(agora), origem="reset")
    p("pronto", 1.0)
    return {"pontos": len(g["pontos"]), "trechos": len(g["trechos"]),
            "observacoes": len(g["observacoes"]), "futuras": len(g["futuras"]),
            "simuladoAte": (agora + timedelta(days=DIAS_SIMULADOS)).isoformat()}
