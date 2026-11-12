"""Mede o custo do job e das consultas quando a raw cresce (1×, 2×, 4× …), e compara com time series.

Pergunta: a consulta na base pronta continua barata com mais volume? O job escala como?
E uma time series collection mudaria o jogo para a raw?

Uso (só em banco `*_test`; escreve e apaga só o banco de bench):
    make seed DB=frota_eta_f2_test            # uma vez: a fonte, com a demo inteira
    .venv/bin/python scripts/bench_escala.py --fonte frota_eta_f2_test [--fatores 1 2 4] [--ts]

Cada fator k copia a raw da fonte k vezes no servidor (`$merge` entre bancos, `viagemId` com
sufixo da cópia: mesmas datas, mesma distribuição, k vezes mais documentos), roda o job e
mede as consultas com `explain` (`executionStats`): o tempo do servidor separa custo de
rede. Imprime JSON; o banco de bench é apagado no fim (use `--manter` para inspecionar).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone

import _path  # noqa: F401

from backend.frota.bootstrap import bootstrap
from backend.frota.cenario import Filtro
from backend.frota.db import get_db, guardar_escrita
from backend.frota.janela import hoje_local, janela_padrao
from backend.frota.job import rodar_job
from backend.frota.pipelines import cenario as pl_cenario
from backend.frota.pipelines import estagios
from backend.frota.pipelines import job as pl_job
from backend.frota.schemas import VALIDATORS

BENCH = "frota_eta_escala_test"
RAW = pl_cenario.RAW
FILTRO = Filtro("BASE-001", "POSTO-11", "CARRETA", [5], 12, 18)


def _achar(no, chave: str) -> list:
    """Todos os valores de `chave` em qualquer profundidade do explain."""
    achados = []
    if isinstance(no, dict):
        for k, v in no.items():
            if k == chave:
                achados.append(v)
            achados += _achar(v, chave)
    elif isinstance(no, list):
        for v in no:
            achados += _achar(v, chave)
    return achados


def explicar(db, colecao: str, pipeline: list[dict]) -> dict:
    """Tempo do servidor e o que foi lido, do explain executionStats (sem o `$merge`)."""
    e = db.command("explain", {"aggregate": colecao, "pipeline": pipeline, "cursor": {}},
                   verbosity="executionStats")
    tempos = _achar(e, "executionTimeMillis") + _achar(e, "executionTimeMillisEstimate")
    return {"msServidor": max(tempos) if tempos else None,
            "chavesLidas": max(_achar(e, "totalKeysExamined") or [0]),
            "docsLidos": max(_achar(e, "totalDocsExamined") or [0]),
            "estagio": sorted({s for s in _achar(e, "stage") if isinstance(s, str)} & {
                "COLLSCAN", "IXSCAN", "FETCH"})}


def rtt_ms(db, n: int = 7) -> float:
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        db.command("ping")
        ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(ts), 1)


def tamanho(db, colecao: str) -> dict:
    s = db.command("collStats", colecao)
    return {"docs": s["count"], "dadosMB": round(s["size"] / 1e6, 1),
            "discoMB": round(s["storageSize"] / 1e6, 1),
            "indicesMB": round(s["totalIndexSize"] / 1e6, 1)}


def copiar_raw(fonte, destino, vezes: int) -> None:
    for i in range(vezes):
        fonte[RAW].aggregate([
            {"$unset": "_id"},
            {"$set": {"viagemId": {"$concat": ["$viagemId", f"-C{i}"]}}},
            {"$merge": {"into": {"db": destino.name, "coll": RAW},
                        "on": ["viagemId", "seq"], "whenMatched": "fail",
                        "whenNotMatched": "insert"}},
        ], allowDiskUse=True)


def medir_fator(fonte, k: int, agora: datetime) -> dict:
    db = get_db(guardar_escrita(BENCH))
    for nome in VALIDATORS:
        db.drop_collection(nome)
    bootstrap(db)
    t0 = time.perf_counter()
    copiar_raw(fonte, db, k)
    copia_s = round(time.perf_counter() - t0, 1)
    hoje = hoje_local(agora)
    job = rodar_job(db, hoje, "cli")
    base_p = estagios(pl_cenario.base(FILTRO, FILTRO.dias_ordenados(), FILTRO.horas()))
    ini, fim = janela_padrao(hoje)
    raw_p = estagios(pl_cenario.raw(FILTRO, ini, fim, FILTRO.horas(), None))
    return {"fator": k, "raw": tamanho(db, RAW), "copiaS": copia_s,
            "job": {"lidos": job["lidos"], "gravados": job["gravados"], "ms": job["ms"]},
            "base": tamanho(db, pl_job.COLECAO),
            "consultaBase": explicar(db, pl_job.COLECAO, base_p),
            "consultaRawJanela": explicar(db, RAW, raw_p)}


def medir_time_series(fonte, agora: datetime, repeticoes: int = 2) -> dict:
    """A mesma raw (1×) numa time series collection, medida do mesmo jeito que a raw comum.

    Só o aggregate do job (`$match` → `$set` → `$group` → `$project` → `$merge`), sem os
    counts, a limpeza e o `job_runs` que o `rodar_job` acrescenta. Os dois gravam numa
    collection de rascunho do banco de bench e rodam alternados (raw, ts, raw, ts…), para
    que a carga do cluster compartilhado pese igual nos dois; vale a mediana.
    """
    db = get_db(guardar_escrita(BENCH))
    for nome in ("obs_ts", "base_ts", "base_raw"):
        db.drop_collection(nome)
    fonte[RAW].aggregate([
        {"$set": {"rota": {"origem": "$origem", "destino": "$destino",
                           "tipoVeiculo": "$tipoVeiculo"}}},
        {"$unset": ["_id", "origem", "destino", "tipoVeiculo"]},
        {"$out": {"db": db.name, "coll": "obs_ts",
                  "timeseries": {"timeField": "observadoEm", "metaField": "rota",
                                 "granularity": "minutes"}}},
    ], allowDiskUse=True)
    for nome in ("base_ts", "base_raw"):
        db[nome].create_index([(c, 1) for c in pl_job.CHAVE], unique=True)
    hoje = hoje_local(agora)
    ini, fim = janela_padrao(hoje)
    p = estagios(pl_job.pipeline(ini, fim, hoje, "bench"))
    p_raw = [*p[:-1], {"$merge": {**p[-1]["$merge"], "into": {"db": db.name, "coll": "base_raw"}}}]
    # na time series a rota está no metaField: volta para o formato da raw antes do $set
    p_ts = [p[0], {"$replaceWith": {"$mergeObjects": ["$$ROOT", "$rota"]}}, *p[1:-1],
            {"$merge": {**p[-1]["$merge"], "into": "base_ts"}}]
    tempos: dict[str, list[float]] = {"raw": [], "ts": []}
    for _ in range(repeticoes):
        for nome, coll, pipe in (("raw", fonte[RAW], p_raw), ("ts", db.obs_ts, p_ts)):
            t0 = time.perf_counter()
            coll.aggregate(pipe, allowDiskUse=True)
            tempos[nome].append(round((time.perf_counter() - t0) * 1000, 1))
    s = db.command("collStats", "obs_ts")
    return {"repeticoes": repeticoes,
            "raw": {**tamanho(fonte, RAW), "aggregateMs": tempos["raw"],
                    "medianaMs": statistics.median(tempos["raw"]),
                    "gravados": db.base_raw.count_documents({})},
            "ts": {"discoMB": round(s["storageSize"] / 1e6, 1),
                   "indicesMB": round(s["totalIndexSize"] / 1e6, 1),
                   "buckets": s.get("timeseries", {}).get("bucketCount"),
                   "aggregateMs": tempos["ts"], "medianaMs": statistics.median(tempos["ts"]),
                   "gravados": db.base_ts.count_documents({})}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", required=True, help="banco *_test já semeado (make seed DB=...)")
    ap.add_argument("--fatores", type=int, nargs="*", default=[1, 2, 4],
                    help="vazio (`--fatores`) mede só a time series, com --ts")
    ap.add_argument("--ts", action="store_true", help="também mede a raw em time series (1×), do mesmo jeito que a raw comum")
    ap.add_argument("--manter", action="store_true", help="não apaga o banco de bench no fim")
    a = ap.parse_args()
    fonte = get_db(guardar_escrita(a.fonte))  # só lê; a guarda impede apontar para a demo
    agora = datetime.now(timezone.utc)
    bench = get_db(guardar_escrita(BENCH))
    saida = {"quando": agora.isoformat(timespec="seconds"),
             "servidor": bench.client.server_info()["version"], "rttMs": rtt_ms(bench),
             "fonte": tamanho(fonte, RAW), "fatores": []}
    try:
        for k in a.fatores:
            r = medir_fator(fonte, k, agora)
            saida["fatores"].append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
        if a.ts:
            saida["timeSeries"] = medir_time_series(fonte, agora)
            print(json.dumps(saida["timeSeries"], ensure_ascii=False), flush=True)
    finally:
        if not a.manter:
            bench.client.drop_database(BENCH)
    print(json.dumps(saida, ensure_ascii=False, indent=2))
