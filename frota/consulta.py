"""Consulta de fallback (o que o serviço de ETA chamaria) e o equivalente na raw.

Hierarquia de fallback — **proposta para validação com o cliente**:
`dow+turno` (n ≥ minAmostras) → `turno` (todos os dow) → `geral` (trecho/veículo) →
`sem_historico`. Se nenhum nível atingir o mínimo, devolve o mais amplo com dados e
`abaixoDoMinimo: true`.
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from pymongo.database import Database

from . import config as config_mod
from .explain import explain_aggregate, explain_find
from .janela import derivar_chave, janela, parse_asof
from .pipelines import comentados, estagios
from .pipelines import raw_onthefly

COLECAO = "trecho_media_historica"


def _local_iso(dt: datetime | None, tz: str) -> str | None:
    return dt.astimezone(ZoneInfo(tz)).isoformat() if dt else None


def escolher_nivel(docs: list[dict], chave: dict, min_amostras: int) -> dict:
    """Aplica a hierarquia sobre os ≤ 21 documentos (dow × turno) do trecho/veículo."""
    if not docs:
        return {"nivel": "sem_historico", "mediaMin": None, "mediaKm": None, "n": 0,
                "abaixoDoMinimo": True}
    niveis = [] if chave["dow"] == 0 else [  # dow 0: agregado só por turno
        ("dow+turno", [d for d in docs if d["dow"] == chave["dow"]
                       and d["turno"] == chave["turno"]]),
    ]
    niveis += [
        ("turno", [d for d in docs if d["turno"] == chave["turno"]]),
        ("geral", docs),
    ]
    escolhido = None
    for nome, sel in niveis:
        n = sum(d["n"] for d in sel)
        if n >= min_amostras:
            escolhido = (nome, sel, False)
            break
    if escolhido is None:
        escolhido = ("geral", docs, True)
    nome, sel, abaixo = escolhido
    n = sum(d["n"] for d in sel)
    soma_min = sum(d["somaMin"] for d in sel)
    soma_km = sum(d["somaKm"] for d in sel)
    return {"nivel": nome, "mediaMin": soma_min / n, "mediaKm": soma_km / n, "n": n,
            "abaixoDoMinimo": abaixo}


def _instante(valor: str | datetime, tz: str) -> datetime:
    if isinstance(valor, datetime):
        dt = valor
    else:
        dt = datetime.fromisoformat(valor)
    if dt.tzinfo is None:  # instante sem offset é interpretado no fuso da operação
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def fallback(db: Database, origem: str, destino: str, tipo_veiculo: str,
             instante: str | datetime, asof: str | None = None,
             min_amostras: int | None = None, cfg: dict | None = None,
             com_explain: bool = False, incluir_docs: bool = False) -> dict:
    cfg = cfg or config_mod.vigente_em_cache(db)
    minimo = int(min_amostras or cfg["minAmostras"])
    filtro = {"origem": origem, "destino": destino, "tipoVeiculo": tipo_veiculo}

    t0 = time.perf_counter()
    # uma leitura, ≤ 21 docs; o mais recente primeiro (fornece janela/asOf da resposta)
    docs = list(db[COLECAO].find(filtro, {"_id": 0}).sort("atualizadoEm", -1))
    latencia_ms = (time.perf_counter() - t0) * 1000
    aviso_config = None
    if docs:
        # a chave tem que ser derivada com os turnos/regra que geraram o agregado
        da_versao = config_mod.versao(db, docs[0]["configVersao"])
        if da_versao and docs[0]["configVersao"] != cfg["versao"]:
            aviso_config = (f"agregado calculado com config v{docs[0]['configVersao']}; a vigente é "
                            f"v{cfg['versao']} (rode a camada 2 para aplicá-la)")
        cfg = da_versao or cfg
    tz = cfg["timezone"]
    inst = _instante(instante, tz)
    chave = derivar_chave(inst, cfg)

    escolha = escolher_nivel(docs, chave, minimo)
    if docs:
        ji, jf, asof_mat, versao = (docs[0]["janelaInicio"], docs[0]["janelaFim"],
                                    docs[0]["asOf"], docs[0]["configVersao"])
    else:
        ji, jf = janela(asof or parse_asof(datetime.now(ZoneInfo(tz)).date()), cfg)
        asof_mat, versao = asof, cfg["versao"]
    resposta = {
        "origem": origem, "destino": destino, "tipoVeiculo": tipo_veiculo,
        "instanteLocal": inst.astimezone(ZoneInfo(tz)).isoformat(),
        "chaveSolicitada": {"dow": chave["dow"], "turno": chave["turno"]},
        "horaLocal": chave["hora"],
        **escolha,
        "minAmostras": minimo,
        "janela": {"inicio": _local_iso(ji, tz), "fimExclusivo": _local_iso(jf, tz)},
        "asOf": asof_mat, "configVersao": versao,
        "docsLidos": len(docs),
        "latenciaClienteMs": round(latencia_ms, 3),
        "consulta": {"colecao": COLECAO, "operacao": "find", "filtro": filtro},
    }
    if aviso_config:
        resposta["avisoConfig"] = aviso_config
    if incluir_docs:
        resposta["documentos"] = sorted(docs, key=lambda d: (d["dow"], d["turno"]))
    if asof and asof_mat and asof != asof_mat:
        resposta["avisoAsOf"] = (f"agregado materializado com asOf {asof_mat}; "
                                 f"rode o job com asOf {asof} para atualizar")
    if com_explain:
        ex = explain_find(db, COLECAO, filtro)
        ex.pop("bruto")
        resposta["explain"] = ex
    return resposta


def onthefly(db: Database, origem: str, destino: str, tipo_veiculo: str,
             instante: str | datetime, asof: str, min_amostras: int | None = None,
             cfg: dict | None = None, com_explain: bool = False) -> dict:
    """Mesma resposta, calculada na raw sobre a mesma janela, sem usar o agregado."""
    cfg = cfg or config_mod.ler(db)
    tz = cfg["timezone"]
    inst = _instante(instante, tz)
    chave = derivar_chave(inst, cfg)
    minimo = int(min_amostras or cfg["minAmostras"])
    ji, jf = janela(asof, cfg)
    p = raw_onthefly.pipeline(origem, destino, tipo_veiculo, ji, jf, cfg)
    t0 = time.perf_counter()
    grupos = list(db.trecho_observacoes.aggregate(estagios(p)))
    latencia_ms = (time.perf_counter() - t0) * 1000
    resposta = {
        "origem": origem, "destino": destino, "tipoVeiculo": tipo_veiculo,
        "chaveSolicitada": {"dow": chave["dow"], "turno": chave["turno"]},
        **escolher_nivel(grupos, chave, minimo),
        "minAmostras": minimo,
        "janela": {"inicio": _local_iso(ji, tz), "fimExclusivo": _local_iso(jf, tz)},
        "asOf": asof, "gruposCalculados": len(grupos),
        "latenciaClienteMs": round(latencia_ms, 3),
        "consulta": {"colecao": "trecho_observacoes", "operacao": "aggregate",
                     "pipeline": comentados(p)},
    }
    if com_explain:
        ex = explain_aggregate(db, "trecho_observacoes", estagios(p))
        ex.pop("bruto")
        resposta["explain"] = ex
    return resposta
