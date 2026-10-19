"""Cenários de ETA: base pronta na janela padrão, raw sob demanda fora dela.

Na janela padrão a resposta é a soma de documentos que o job diário já materializou; se
houver menos de MIN_AMOSTRAS, amplia (todos os dias da semana nas mesmas horas, depois o dia
inteiro nos dias pedidos). Fora da janela, agrega a raw na hora e, se pedido, salva o
resultado em `consultas_salvas` com validade (TTL). O sob demanda não amplia: mostra o `n`
como veio, porque o período foi escolhido de propósito.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo.database import Database

from .janela import (hoje_local, horas_da_faixa, inicio_dia, janela_padrao,
                     periodo_para_intervalo, proximo_job)
from .mongosh import para_mongosh
from .operadores import bloco_query
from .pipelines import cenario as pl
from .pipelines import comentados, estagios
from .pipelines import job as job_pl
from .schemas import TIPOS_VEICULO
from .settings import MIN_AMOSTRAS, TTL_RAW_DIAS, TTL_SALVO_MAX_DIAS, TTL_SALVO_PADRAO_DIAS, TZ

UTC = timezone.utc
_TZ = ZoneInfo(TZ)
TODOS_OS_DIAS = list(range(1, 8))
DIA_INTEIRO = list(range(24))
SEM_RAW = "sem dados brutos para esse período"
# instante qualquer: `validar` só confere a forma do período (datas e "ultimos" não dependem dele)
_QUALQUER = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass
class Filtro:
    origem: str
    destino: str
    tipoVeiculo: str
    dias: list[int]
    horaInicio: int
    horaFim: int
    periodo: dict = field(default_factory=lambda: {"tipo": "padrao"})
    persistir: bool = False
    ttlDias: int = TTL_SALVO_PADRAO_DIAS

    def validar(self) -> None:
        for nome in ("origem", "destino"):
            v = getattr(self, nome)
            if not isinstance(v, str) or not v:
                raise ValueError(f"Informe '{nome}'.")
        if self.tipoVeiculo not in TIPOS_VEICULO:
            raise ValueError(f"Tipo de veículo inválido: use um de {', '.join(TIPOS_VEICULO)}.")
        if not isinstance(self.dias, list) or not self.dias:
            raise ValueError("Escolha pelo menos um dia da semana.")
        if any(not _inteiro(d) or not 1 <= d <= 7 for d in self.dias):
            raise ValueError("Dias da semana vão de 1 (segunda) a 7 (domingo).")
        if not _inteiro(self.horaInicio) or not _inteiro(self.horaFim):
            raise ValueError("As horas devem ser números inteiros.")
        horas_da_faixa(self.horaInicio, self.horaFim)
        if not isinstance(self.periodo, dict):
            raise ValueError("Período inválido.")
        periodo_para_intervalo(self.periodo, _QUALQUER)
        if not _inteiro(self.ttlDias) or not 1 <= self.ttlDias <= TTL_SALVO_MAX_DIAS:
            raise ValueError(f"A validade do salvo deve ficar entre 1 e {TTL_SALVO_MAX_DIAS} dias.")

    def dias_ordenados(self) -> list[int]:
        return sorted(set(self.dias))

    def horas(self) -> list[int]:
        return horas_da_faixa(self.horaInicio, self.horaFim)

    def descricao(self) -> dict:
        return {"origem": self.origem, "destino": self.destino, "tipoVeiculo": self.tipoVeiculo,
                "dias": self.dias_ordenados(), "horas": self.horas(), "periodo": self.periodo}

    def _periodo_resolvido(self, agora: datetime | None) -> dict:
        tipo = self.periodo.get("tipo")
        if tipo == "datas":
            ini, fim, _ = periodo_para_intervalo(self.periodo, _QUALQUER)
            return {"de": hoje_local(ini).isoformat(),
                    "ate": hoje_local(fim - timedelta(seconds=1)).isoformat()}
        if agora is None:
            raise ValueError("Período relativo precisa do instante de referência.")
        n = 180 if tipo == "padrao" else self.periodo.get("dias")
        return {"ultimos": n, "dataRef": hoje_local(agora).isoformat()}

    def chave(self, agora: datetime | None = None) -> str:
        """sha1 do JSON canônico do filtro; o relativo muda de chave quando o dia vira."""
        canon = {"origem": self.origem, "destino": self.destino,
                 "tipoVeiculo": self.tipoVeiculo, "dias": self.dias_ordenados(),
                 "horas": self.horas(), "periodo": self._periodo_resolvido(agora)}
        txt = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha1(txt.encode()).hexdigest()


def _inteiro(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ddmm(dt: datetime) -> str:
    return dt.astimezone(_TZ).strftime("%d/%m")


def _metricas(doc: dict | None, docs_lidos: int, dias: list[int], horas: list[int],
              ms: float) -> dict:
    n = int(doc["n"]) if doc else 0
    media = media_km = desvio = None
    if n:
        media = doc["somaMin"] / n
        media_km = doc["somaKm"] / n
        desvio = math.sqrt(max(0.0, doc["somaQuadMin"] / n - media * media))
    return {"n": n, "mediaMin": media, "desvioMin": desvio, "mediaKm": media_km,
            "docsLidos": docs_lidos, "diasSomados": dias, "horas": horas, "ms": ms}


def _resposta(selo: str, detalhe: str, query: dict, *, nivel=None, resultado=None,
              aviso=None, expira=None, gerado=None) -> dict:
    return {"selo": selo, "detalhe": detalhe, "nivel": nivel, "resultado": resultado,
            "aviso": aviso, "expiraEm": expira, "query": query, "geradoPor": gerado}


def _gerado_por(db: Database, agora: datetime) -> dict:
    """O pipeline do job que produziu a base desta janela padrão."""
    hoje = hoje_local(agora)
    ini, fim = janela_padrao(hoje)
    run = db.job_runs.find_one({"dataRef": hoje.isoformat(), "status": "ok"},
                               sort=[("iniciadoEm", -1)])
    p = job_pl.pipeline(ini, fim, hoje, run["runId"] if run else "pendente")
    return bloco_query(pl.RAW, comentados(p), [pl.RAW], [job_pl.COLECAO])


_DETALHE_BASE = {
    "pedido": "somado da base pronta do job diário",
    "todos_os_dias": "poucas amostras: ampliado para todos os dias da semana nas mesmas horas",
    "dia_inteiro": "poucas amostras: ampliado para o dia inteiro nos dias pedidos",
    "sem_historico": "sem histórico suficiente, mesmo ampliando",
}


def _da_base(db: Database, f: Filtro, agora: datetime) -> dict:
    dias, horas = f.dias_ordenados(), f.horas()
    tentativas = [("pedido", dias, horas), ("todos_os_dias", TODOS_OS_DIAS, horas),
                  ("dia_inteiro", dias, DIA_INTEIRO)]
    t0 = time.perf_counter()
    for nivel, d, h in tentativas:
        p = pl.base(f, d, h)
        doc = next(db[pl.BASE].aggregate(estagios(p)), None)
        if doc and doc["n"] >= MIN_AMOSTRAS:
            break
    else:
        nivel = "sem_historico"
    ms = round((time.perf_counter() - t0) * 1000, 1)
    query = bloco_query(pl.BASE, comentados(p), [pl.BASE], [])
    gerado = _gerado_por(db, agora)
    if nivel == "sem_historico":
        return _resposta("job_diario", _DETALHE_BASE[nivel], query, nivel=nivel,
                         aviso=f"menos de {MIN_AMOSTRAS} amostras mesmo ampliando",
                         gerado=gerado)
    res = _metricas(doc, int(doc["docs"]), d, h, ms)
    return _resposta("job_diario", _DETALHE_BASE[nivel], query, nivel=nivel,
                     resultado=res, gerado=gerado)


def _bloco_salvo(chave: str, agora: datetime) -> dict:
    filtro = {"_id": chave, "expiraEm": {"$gt": agora}}
    comentado = [{"comentario": "Busca a consulta salva pela chave do filtro, se ainda vale.",
                  "estagio": filtro}]
    q = bloco_query(pl.SALVOS, comentado, [pl.SALVOS], [], operacao="findOne")
    q["mongosh"] = ("// Busca a consulta salva pela chave do filtro, se ainda vale.\n"
                    f"db.{pl.SALVOS}.findOne({para_mongosh(filtro)})")
    return q


def _sob_demanda(db: Database, f: Filtro, agora: datetime) -> dict:
    ini, fim, tipo = periodo_para_intervalo(f.periodo, agora)
    dias, horas = f.dias_ordenados(), f.horas()
    inicio_raw = inicio_dia(hoje_local(agora) - timedelta(days=TTL_RAW_DIAS))
    chave = f.chave(agora)
    salvar = None
    if f.persistir:
        expira = agora + timedelta(days=f.ttlDias) if tipo == "absoluto" else proximo_job(agora)
        salvar = {"_id": chave, "periodo": tipo, "expiraEm": expira}
    p = pl.raw(f, ini, fim, horas, salvar)
    grava = [pl.SALVOS] if salvar else []
    query = bloco_query(pl.RAW, comentados(p), [pl.RAW], grava)
    if fim <= inicio_raw or ini >= agora:
        return _resposta("sob_demanda", SEM_RAW, query, aviso=SEM_RAW)

    t0 = time.perf_counter()
    salvo = db[pl.SALVOS].find_one({"_id": chave, "expiraEm": {"$gt": agora}})
    if salvo:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        q = _bloco_salvo(chave, agora)
        return _resposta("sob_demanda", f"lido do salvo · expira {_ddmm(salvo['expiraEm'])}", q,
                         resultado=_metricas(salvo, 1, dias, horas, ms),
                         expira=salvo["expiraEm"])

    cursor = db[pl.RAW].aggregate(estagios(p), allowDiskUse=True)
    if salvar:
        # o $merge não devolve documentos: lê de volta o que o próprio aggregate gravou
        list(cursor)
        doc = db[pl.SALVOS].find_one({"_id": chave})
    else:
        doc = next(cursor, None)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    res = _metricas(doc, int(doc["n"]) if doc else 0, dias, horas, ms)
    if salvar and doc:
        return _resposta("sob_demanda", f"calculado agora · salvo até {_ddmm(salvar['expiraEm'])}",
                         query, resultado=res, expira=salvar["expiraEm"])
    detalhe = ("calculado agora na raw (sem amostras, nada salvo)" if salvar
               else "calculado agora na raw (não salvo)")
    return _resposta("sob_demanda", detalhe, query, resultado=res)


def consultar(db: Database, f: Filtro, agora: datetime) -> dict:
    f.validar()
    if f.periodo.get("tipo") == "padrao":
        return _da_base(db, f, agora)
    return _sob_demanda(db, f, agora)
