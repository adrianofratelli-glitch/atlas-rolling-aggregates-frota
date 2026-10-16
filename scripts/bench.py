"""Benchmark no perfil `escala`: job incremental, recálculo completo, latência e storage.

Só reporta o que mediu. Resultado em docs/bench-results.json e tabela no stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import time
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401

from frota import config as config_mod
from frota import settings
from frota.bootstrap import bootstrap
from frota.consulta import fallback, onthefly
from frota.db import get_db, guardar_escrita
from frota.janela import janela
from frota.job import materializar
from frota.pipelines.expressoes import expr_dow, expr_turno
from frota.seed import seed
from frota.simulacao import asof_atual, avancar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cronometro(fn, *a, **k):
    t0 = time.perf_counter()
    r = fn(*a, **k)
    return r, time.perf_counter() - t0


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def recalculo_completo(db, asof, cfg):
    """O que uma MV com COMPLETE refresh faria: $group direto sobre 180 dias de raw."""
    ji, jf = janela(asof, cfg)
    tz = cfg["timezone"]
    pipe = [
        {"$match": {"observadoEm": {"$gte": ji, "$lt": jf}}},
        {"$set": {"hora": {"$hour": {"date": "$observadoEm", "timezone": tz}},
                  "dowCivil": {"$dayOfWeek": {"date": "$observadoEm", "timezone": tz}}}},
        {"$set": {"turno": expr_turno(cfg["turnos"]), "dow": expr_dow(cfg)}},
        {"$group": {"_id": {"o": "$origem", "d": "$destino", "t": "$tipoVeiculo",
                            "dow": "$dow", "turno": "$turno"},
                    "somaMin": {"$sum": "$tempoMin"}, "n": {"$sum": 1}}},
        {"$out": "bench_recalculo_completo"},
    ]
    db.trecho_observacoes.aggregate(pipe, allowDiskUse=True)
    return db.bench_recalculo_completo.estimated_document_count()


def storage(db, nome):
    s = db.command("collStats", nome)
    return {"docs": s["count"], "dataMB": round(s["size"] / 2**20, 1),
            "storageMB": round(s["storageSize"] / 2**20, 1),
            "indicesMB": round(s["totalIndexSize"] / 2**20, 1),
            "bytesPorDoc": round(s["avgObjSize"]) if s["count"] else 0}


def hardware(db):
    info = {"so": f"{platform.system()} {platform.release()}", "maquina": platform.machine(),
            "cpusHost": os.cpu_count(), "mongodb": db.client.server_info()["version"],
            "python": platform.python_version()}
    try:
        info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                     capture_output=True, text=True).stdout.strip()
        d = subprocess.run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"],
                           capture_output=True, text=True).stdout.split()
        info["docker"] = f"{d[0]} vCPU, {int(d[1]) / 2**30:.1f} GiB"
    except Exception:
        pass
    return info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="frota_eta_bench")
    ap.add_argument("--profile", default="escala")
    ap.add_argument("--reuse", action="store_true", help="não regerar se já houver dados")
    ap.add_argument("--consultas", type=int, default=500)
    a = ap.parse_args()
    guardar_escrita(a.db)
    db = get_db(a.db)
    db.config.delete_many({}) if not a.reuse else None
    bootstrap(db)
    res = {"perfil": a.profile, "alvo": settings.ALVO,
           "medidoEm": datetime.now(timezone.utc).isoformat(), "hardware": hardware(db)}

    if not (a.reuse and db.trecho_observacoes.estimated_document_count()):
        print("1/6 seed ...", flush=True)
        r, _ = cronometro(seed, db, a.profile, settings.SEED, log=lambda m: print(m, flush=True))
        res["seed"] = r
    else:
        # reaproveita a raw, mas remede a carga inicial do zero
        print("1/6 seed reaproveitado; limpando buckets, médias e job_runs ...", flush=True)
        for c in ("trecho_bucket_diario", "trecho_media_historica", "job_runs"):
            db[c].delete_many({})
        res["seed"] = {"reaproveitado": True,
                       "observacoes": db.trecho_observacoes.estimated_document_count()}
    if True:
        print("2/6 carga inicial (camada 1 com 180 dias + camada 2) ...", flush=True)
        run, s = cronometro(materializar, db)
        res["cargaInicial"] = {"segundos": round(s, 1),
                               "tentativasCamada1": run["stats"]["camada1"]["tentativas"],
                               "errosTransitorios": run["stats"]["camada1"]["errosTransitorios"],
                               "camada1Ms": run["stats"]["camada1"]["duracaoMs"],
                               "camada2Ms": run["stats"]["camada2"]["duracaoMs"],
                               "buckets": run["stats"]["camada1"]["inseridos"],
                               "medias": run["stats"]["camada2"]["inseridos"]}
    cfg = config_mod.ler(db)

    print("3/6 job incremental (avançar 1 dia: gera o dia, camada 1 com k dias + camada 2) ...",
          flush=True)
    p = avancar(db, 1)[0]
    c1, c2 = p["run"]["stats"]["camada1"], p["run"]["stats"]["camada2"]
    res["jobIncremental"] = {"asOf": p["asOf"], "k": cfg["kReprocessamento"],
                             "diasReprocessados": len(c1["diasReprocessados"]),
                             "rawLidos": c1["lidos"], "camada1Ms": c1["duracaoMs"],
                             "bucketsLidosCamada2": c2["lidos"], "camada2Ms": c2["duracaoMs"],
                             "totalMs": round(c1["duracaoMs"] + c2["duracaoMs"], 1)}
    asof = asof_atual(db)
    print("3b/6 job em regime (mesmo asOf, só k dias) e camada 2 em modo out ...", flush=True)
    run, s = cronometro(materializar, db, asof)
    res["jobRegime"] = {"segundos": round(s, 1),
                        "diasReprocessados": len(run["stats"]["camada1"]["diasReprocessados"]),
                        "rawLidos": run["stats"]["camada1"]["lidos"],
                        "camada1Ms": run["stats"]["camada1"]["duracaoMs"],
                        "camada2Ms": run["stats"]["camada2"]["duracaoMs"]}
    config_mod.atualizar(db, {"modoLimpezaCamada2": "out"})
    run, s = cronometro(materializar, db, asof, "2")
    res["camada2Out"] = {"segundos": round(s, 1), "camada2Ms": run["stats"]["camada2"]["duracaoMs"]}
    config_mod.atualizar(db, {"modoLimpezaCamada2": "merge_runid"})
    cfg = config_mod.ler(db)

    print("4/6 recálculo completo direto da raw (180 dias) ...", flush=True)
    grupos, s = cronometro(recalculo_completo, db, asof, cfg)
    res["recalculoCompletoRaw"] = {"segundos": round(s, 2), "grupos": grupos}
    db.bench_recalculo_completo.drop()

    print(f"5/6 latência: {a.consultas} consultas de fallback e on-the-fly ...", flush=True)
    chaves = list(db.trecho_media_historica.aggregate([
        {"$sample": {"size": a.consultas}},
        {"$project": {"_id": 0, "origem": 1, "destino": 1, "tipoVeiculo": 1}}]))
    rnd = random.Random(1)
    base = datetime.fromisoformat(f"{asof}T00:00:00-03:00")
    lat_mat, lat_raw = [], []
    for c in chaves:
        inst = base - timedelta(days=rnd.randint(1, 7), hours=rnd.randint(0, 23))
        t0 = time.perf_counter()
        fallback(db, c["origem"], c["destino"], c["tipoVeiculo"], inst, cfg=cfg)
        lat_mat.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        onthefly(db, c["origem"], c["destino"], c["tipoVeiculo"], inst, asof, cfg=cfg)
        lat_raw.append((time.perf_counter() - t0) * 1000)
    # tempo no servidor (explain executionStats) numa subamostra: separa banco de rede
    srv_mat, srv_raw, docs_raw = [], [], []
    for c in chaves[:100]:
        k = (c["origem"], c["destino"], c["tipoVeiculo"])
        em = fallback(db, *k, instante=base, cfg=cfg, com_explain=True)["explain"]
        er = onthefly(db, *k, instante=base, asof=asof, cfg=cfg, com_explain=True)["explain"]
        srv_mat.append(em["executionTimeMillis"] or 0)
        srv_raw.append(er["executionTimeMillis"] or 0)
        docs_raw.append(er["totalDocsExamined"] or 0)
    rtt = []
    for _ in range(20):
        t0 = time.perf_counter()
        db.command("ping")
        rtt.append((time.perf_counter() - t0) * 1000)
    c0 = (chaves[0]["origem"], chaves[0]["destino"], chaves[0]["tipoVeiculo"])
    ex_m = fallback(db, *c0, instante=base, cfg=cfg, com_explain=True)["explain"]
    ex_r = onthefly(db, *c0, instante=base, asof=asof, cfg=cfg, com_explain=True)["explain"]
    res["latencia"] = {
        "consultas": len(chaves),
        "fallbackMs": {"p50": round(pct(lat_mat, 50), 2), "p95": round(pct(lat_mat, 95), 2),
                       "media": round(statistics.mean(lat_mat), 2)},
        "onTheFlyRawMs": {"p50": round(pct(lat_raw, 50), 2), "p95": round(pct(lat_raw, 95), 2),
                          "media": round(statistics.mean(lat_raw), 2)},
        "servidorMs (explain, 100 chaves)": {
            "fallback": {"p50": pct(srv_mat, 50), "p95": pct(srv_mat, 95), "max": max(srv_mat)},
            "onTheFlyRaw": {"p50": pct(srv_raw, 50), "p95": pct(srv_raw, 95), "max": max(srv_raw)},
            "docsExaminadosRaw": {"p50": pct(docs_raw, 50), "p95": pct(docs_raw, 95),
                                  "max": max(docs_raw)}},
        "pingMs": {"p50": round(pct(rtt, 50), 1), "p95": round(pct(rtt, 95), 1)},
        "explainFallbackExemplo": ex_m, "explainRawExemplo": ex_r,
    }

    print("6/6 storage (collStats) ...", flush=True)
    res["storage"] = {n: storage(db, n) for n in
                      ("trecho_observacoes", "trecho_bucket_diario", "trecho_media_historica")}

    destino = os.path.join(RAIZ, "docs", f"bench-results-{settings.ALVO}.json")
    with open(destino, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "latencia"}, ensure_ascii=False,
                     indent=2, default=str))
    print(json.dumps({k: v for k, v in res["latencia"].items() if "explain" not in k}, indent=2))
    print(f"gravado em {destino}")
