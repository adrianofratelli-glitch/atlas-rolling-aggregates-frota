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


def _inserir(coll, docs: list[dict]) -> None:
    for i in range(0, len(docs), LOTE):
        coll.insert_many(docs[i:i + LOTE], ordered=False)


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
    p("inserindo", 0.3)
    _inserir(db.pontos, g["pontos"])
    _inserir(db.trechos, g["trechos"])
    _inserir(db.trecho_observacoes, g["observacoes"])
    p("inserindo", 0.8)
    _inserir(db.ingestao_simulada, g["futuras"])
    p("job", 0.9)
    from . import job  # import tardio: o job é da etapa seguinte
    job.rodar_job(db, hoje_local(agora), origem="reset")
    p("pronto", 1.0)
    return {"pontos": len(g["pontos"]), "trechos": len(g["trechos"]),
            "observacoes": len(g["observacoes"]), "futuras": len(g["futuras"]),
            "simuladoAte": (agora + timedelta(days=DIAS_SIMULADOS)).isoformat()}
