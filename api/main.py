"""API da POV. Mesmos módulos que os testes usam; a UI é só vitrine.

    uvicorn api.main:app --port 8410
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from frota import config as config_mod
from frota import settings
from frota.bootstrap import bootstrap
from frota.capo import badges, metadados, pipelines_atuais
from frota.consulta import fallback, onthefly
from frota.db import get_db
from frota.janela import DOW_NOMES, derivar_chave, hoje_local, inicio_dia, janela, parse_asof
from frota.job import LockOcupado, mascarar, materializar
from frota.mongosh import jsonavel, para_mongosh, pipeline_mongosh
from frota.simulacao import asof_atual, avancar, injetar_atrasado

app = FastAPI(title="Agregados em janela móvel — fallback de ETA", version="1.0.1")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5410",
                                                  "http://localhost:5410"],
                   allow_methods=["*"], allow_headers=["*"])

_boot = {"ok": False}
_escrita = threading.Lock()  # serializa job/advance/config vindos da UI


def db():
    d = get_db(settings.MONGODB_DB)
    if not _boot["ok"]:
        bootstrap(d)
        _boot["ok"] = True
    return d


_PRIVADOS = {"owner"}  # host:pid do processo do job: diagnóstico interno, não sai na API


def _sem_privados(obj):
    if isinstance(obj, str):
        return mascarar(obj)
    if isinstance(obj, dict):
        return {k: _sem_privados(v) for k, v in obj.items() if k not in _PRIVADOS}
    if isinstance(obj, list):
        return [_sem_privados(v) for v in obj]
    return obj


def J(obj, status: int = 200):
    return JSONResponse(_sem_privados(jsonavel(obj)), status_code=status)


@app.exception_handler(PyMongoError)
def _mongo_fora(_, exc):
    _boot["ok"] = False
    return J({"erro": "MongoDB indisponível ou erro de servidor",
              "detalhe": mascarar(f"{type(exc).__name__}: {str(exc)[:300]}"),
              "acao": "suba o banco com `make up` e recarregue"}, 503)


@app.exception_handler(ValueError)
def _valor(_, exc):
    return J({"erro": str(exc)}, 400)


@app.get("/health/live")
def live():
    return {"ok": True}


@app.get("/health/ready")
def ready():
    d = db()
    d.command("ping")
    return {"ok": True, "db": d.name}


def _asof(valor: str | None) -> str:
    d = db()
    return valor or asof_atual(d) or hoje_local(config_mod.ler(d)["timezone"]).isoformat()


# ---- estado e catálogo ------------------------------------------------------

@app.get("/api/estado")
def estado():
    d = db()
    cfg = config_mod.ler(d)
    ultimo = d.job_runs.find_one({}, {"stats.camada1.pipeline": 0, "stats.camada2.pipeline": 0},
                                 sort=[("iniciadoEm", -1)])
    metadados(d)  # aquece o cache dos badges (o start.sh chama esta rota antes do "pronto")
    contagens = {c: d[c].estimated_document_count() for c in
                 ("trecho_observacoes", "trecho_bucket_diario", "trecho_bucket_turno",
                  "trecho_media_historica", "ingestao_pendente", "trechos", "veiculos")}
    return J({"db": d.name, "mongodb": d.client.server_info()["version"],
              "asOfAtual": asof_atual(d), "hojeReal": hoje_local(cfg["timezone"]).isoformat(),
              "config": cfg, "contagens": contagens, "ultimoRun": ultimo})


@app.get("/api/catalogo")
def catalogo():
    d = db()
    nomes = {p["_id"]: p for p in d.pontos.find({}, {"nome": 1, "tipo": 1, "cidade": 1})}
    origens = sorted(d.trechos.distinct("origem"))
    tipos = list(d.tipos_veiculo.find({}, {"descricao": 1, "fatorTempo": 1}).sort("fatorTempo", 1))
    return J({"origens": [{"id": o, **{k: v for k, v in nomes.get(o, {}).items() if k != "_id"}}
                          for o in origens],
              "tipos": tipos})


@app.get("/api/destinos")
def destinos(origem: str):
    d = db()
    dest = sorted(d.trechos.distinct("destino", {"origem": origem}))
    com_hist = set(d.trecho_media_historica.distinct("destino", {"origem": origem}))
    return J([{"id": x, "comHistorico": x in com_hist} for x in dest])


def _contexto(d, asof: str, hora: int):
    cfg = config_mod.ler(d)
    tz = cfg["timezone"]
    inst = inicio_dia(parse_asof(asof), tz) + timedelta(hours=hora)
    ch = derivar_chave(inst, cfg)
    ji, jf = janela(asof, cfg)
    turno = next(t for t in cfg["turnos"] if t["codigo"] == ch["turno"])
    return cfg, inst, {
        "asOf": asof, "instanteLocal": inst.astimezone(ZoneInfo(tz)).isoformat(),
        "janela": {"inicioLocal": ji.astimezone(ZoneInfo(tz)).date().isoformat(),
                   "fimExclusivoLocal": jf.astimezone(ZoneInfo(tz)).date().isoformat(),
                   "ultimoDiaIncluido": (jf.astimezone(ZoneInfo(tz)).date()
                                         - timedelta(days=1)).isoformat(),
                   "inicioUTC": ji, "fimExclusivoUTC": jf, "dias": cfg["janelaDias"]},
        "dow": ch["dow"], "dowNome": DOW_NOMES[ch["dow"]], "dowCivil": ch["dowCivil"],
        "turno": ch["turno"], "turnoLimites": turno, "regraNoite": cfg["regraNoite"],
        "hora": hora, "configVersao": cfg["versao"],
    }


# ---- consulta ETA -----------------------------------------------------------

@app.get("/eta/fallback")
@app.get("/api/eta/fallback")
def eta_fallback(origem: str, destino: str, tipoVeiculo: str, instante: str,
                 asOf: str | None = None, minAmostras: int | None = Query(None, ge=1)):
    """Contrato do serviço de ETA (seção 14.4)."""
    r = fallback(db(), origem, destino, tipoVeiculo, instante, asof=asOf,
                 min_amostras=minAmostras)
    r.pop("latenciaClienteMs", None)
    r.pop("consulta", None)
    r.pop("horaLocal", None)
    return J(r)


@app.get("/api/eta")
def eta(origem: str, destino: str, tipoVeiculo: str, hora: int = Query(..., ge=0, le=23),
        asOf: str | None = None, minAmostras: int | None = Query(None, ge=1)):
    d = db()
    asof = _asof(asOf)
    cfg, inst, ctx = _contexto(d, asof, hora)
    r = fallback(d, origem, destino, tipoVeiculo, inst, asof=asof, min_amostras=minAmostras,
                 cfg=cfg, incluir_docs=True)
    filtro = r["consulta"]["filtro"]
    docs = r.pop("documentos")
    ctx["chaveConsultada"] = {**filtro, **r["chaveSolicitada"]}
    return J({"contexto": ctx, "resultado": r, "documentos": docs,
              "mongosh": f"db.trecho_media_historica.find({para_mongosh(filtro)})",
              "badges": badges(d, ["trecho_media_historica"])})


@app.get("/api/comparar")
def comparar(origem: str, destino: str, tipoVeiculo: str, hora: int = Query(..., ge=0, le=23),
             asOf: str | None = None, minAmostras: int | None = Query(None, ge=1)):
    """Mesma pergunta na raw e no agregado, com explain('executionStats') real."""
    d = db()
    asof = _asof(asOf)
    cfg, inst, ctx = _contexto(d, asof, hora)
    m = fallback(d, origem, destino, tipoVeiculo, inst, asof=asof, min_amostras=minAmostras,
                 cfg=cfg, com_explain=True)
    r = onthefly(d, origem, destino, tipoVeiculo, inst, asof, min_amostras=minAmostras,
                 cfg=cfg, com_explain=True)
    filtro = m["consulta"]["filtro"]
    return J({
        "contexto": ctx,
        "materializado": {**m, "mongosh": f"db.trecho_media_historica.find("
                                          f"{para_mongosh(filtro)}).explain('executionStats')",
                          "badges": badges(d, ["trecho_media_historica"],
                                           indices_usados=m["explain"]["indices"])},
        "raw": {**r, "mongosh": pipeline_mongosh("trecho_observacoes",
                                                 r["consulta"]["pipeline"]),
                "badges": badges(d, ["trecho_observacoes"], [r["consulta"]["pipeline"]],
                                 indices_usados=r["explain"]["indices"])},
        "mesmaResposta": (m["nivel"], m["n"]) == (r["nivel"], r["n"]) and
                         (m["mediaMin"] is None and r["mediaMin"] is None or
                          m["mediaMin"] is not None and r["mediaMin"] is not None and
                          abs(m["mediaMin"] - r["mediaMin"]) < 1e-9),
    })


# ---- job --------------------------------------------------------------------

def _run_api(d, run: dict) -> dict:
    s = run.get("stats", {})
    pipes, colecoes = [], ["trecho_observacoes"]
    mongosh = {}
    if "simples" in s:
        pipes.append(s["simples"]["pipeline"])
        colecoes.append("trecho_media_historica")
        mongosh["simples"] = pipeline_mongosh("trecho_observacoes", s["simples"]["pipeline"])
    if "camada1" in s:
        destino = ("trecho_bucket_turno" if s["camada1"].get("granularidade") == "turno"
                   else "trecho_bucket_diario")
        pipes.append(s["camada1"]["pipeline"])
        colecoes.append(destino)
        mongosh["camada1"] = pipeline_mongosh("trecho_observacoes", s["camada1"]["pipeline"])
    if "camada2" in s:
        fonte = s["camada2"].get("fonte", "trecho_bucket_diario")
        pipes.append(s["camada2"]["pipeline"])
        colecoes += [fonte, "trecho_media_historica"]
        mongosh["camada2"] = pipeline_mongosh(fonte, s["camada2"]["pipeline"])
    return {"run": run, "mongosh": mongosh, "badges": badges(d, colecoes, pipes)}


@app.post("/api/job")
def job(body: dict = Body(default={})):
    d = db()
    asof = _asof(body.get("asOf"))
    camada = str(body.get("camada", "todas"))
    with _escrita:
        try:
            run = materializar(d, asof, camada)
        except LockOcupado as e:
            return J({"erro": str(e)}, 409)
    return J(_run_api(d, run))


@app.get("/api/job_runs")
def job_runs(limit: int = Query(15, ge=1, le=100)):
    proj = {"stats.camada1.pipeline": 0, "stats.camada2.pipeline": 0,
            "stats.camada2.removidosAmostra": 0}
    return J(list(db().job_runs.find({}, proj).sort("iniciadoEm", -1).limit(limit)))


@app.post("/api/atrasado")
def atrasado(body: dict = Body(...)):
    d = db()
    asof = _asof(body.get("asOf"))
    faltando = [k for k in ("origem", "destino", "tipoVeiculo") if not body.get(k)]
    if faltando:
        raise ValueError(f"campos obrigatórios: {faltando}")
    doc = injetar_atrasado(d, asof, body["origem"], body["destino"], body["tipoVeiculo"],
                           int(body.get("diasAtras", 2)), int(body.get("hora", 8)))
    return J({"inserido": doc, "comando": f"db.trecho_observacoes.insertOne({para_mongosh(doc)})"})


@app.get("/api/buckets")
def buckets(origem: str, destino: str, tipoVeiculo: str, asOf: str | None = None,
            dias: int = Query(7, ge=1, le=60)):
    """Buckets recentes do trecho/veículo (o que a camada 1 materializou)."""
    d = db()
    cfg = config_mod.ler(d)
    asof = parse_asof(_asof(asOf))
    de = inicio_dia(asof - timedelta(days=dias), cfg["timezone"])
    filtro = {"origem": origem, "destino": destino, "tipoVeiculo": tipoVeiculo,
              "dataLocal": {"$gte": de}}
    por_turno = cfg.get("granularidadeBucket") == "turno"
    colecao = "trecho_bucket_turno" if por_turno else "trecho_bucket_diario"
    docs = list(d[colecao].find(filtro, {"_id": 0}).sort(
        [("dataLocal", 1), ("turno" if por_turno else "hora", 1)]))
    raw = d.trecho_observacoes.count_documents({**{k: filtro[k] for k in
                                                   ("origem", "destino", "tipoVeiculo")},
                                                "observadoEm": {"$gte": de}})
    return J({"buckets": docs, "observacoesRawMesmoPeriodo": raw, "colecao": colecao,
              "granularidade": "turno" if por_turno else "hora",
              "modoMaterializacao": cfg.get("modoMaterializacao"),
              "mongosh": f"db.{colecao}.find({para_mongosh(filtro)})"})


# ---- simples × incremental ----------------------------------------------------

DESENHOS = {
    "simples": {"modoMaterializacao": "simples", "modoLimpezaCamada2": "out"},
    "incremental_turno": {"modoMaterializacao": "incremental", "granularidadeBucket": "turno",
                          "modoLimpezaCamada2": "out"},
}
BENCH = Path(__file__).resolve().parent.parent / "docs" / "bench-results-atlas.json"


def _snapshot(d) -> list[dict]:
    proj = {"_id": 0, "atualizadoEm": 0, "runId": 0, "configVersao": 0, "asOf": 0}
    return list(d.trecho_media_historica.find({}, proj).sort(
        [("origem", 1), ("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]))


@app.post("/api/comparar-modos")
def comparar_modos(body: dict = Body(default={})):
    """Roda os dois desenhos sobre a mesma raw e o mesmo asOf, mede e compara o agregado.

    Não grava a config: o desenho é trocado só para a execução. O incremental roda duas
    vezes — a primeira pode ser carga inicial; a segunda é o run diário em regime.
    """
    d = db()
    asof = _asof(body.get("asOf"))
    cfg = config_mod.ler(d)
    resultado = {}
    with _escrita:
        try:
            for nome, execucao in DESENHOS.items():
                runs = [materializar(d, asof, execucao=execucao)]
                if nome != "simples":
                    runs.append(materializar(d, asof, execucao=execucao))
                resultado[nome] = {
                    "runs": [{"runId": r["runId"], "segundos": round(
                        (r["finalizadoEm"] - r["iniciadoEm"]).total_seconds(), 2),
                        "etapas": {k: {c: v for c, v in st.items() if c in (
                            "modo", "lidos", "inseridos", "atualizados", "removidos",
                            "duracaoMs", "diasReprocessados")}
                            for k, st in r["stats"].items() if isinstance(st, dict)}}
                        for r in runs],
                    "agregado": _snapshot(d),
                    "badges": badges(d, ["trecho_observacoes"], [
                        st["pipeline"] for st in runs[-1]["stats"].values()
                        if isinstance(st, dict) and "pipeline" in st]),
                }
            # devolve o agregado ao desenho configurado
            materializar(d, asof)
        except LockOcupado as e:
            return J({"erro": str(e)}, 409)
    iguais = resultado["simples"]["agregado"] == resultado["incremental_turno"]["agregado"]
    for r in resultado.values():
        r["documentos"] = len(r.pop("agregado"))
    contagens = {c: d[c].estimated_document_count() for c in
                 ("trecho_observacoes", "trecho_bucket_turno", "trecho_bucket_diario",
                  "trecho_media_historica")}
    bench = None
    if BENCH.exists():
        import json as _json
        b = _json.loads(BENCH.read_text())
        bench = {"medidoEm": b.get("medidoEm"), "perfil": b.get("perfil"),
                 "observacoes": (b.get("seed") or {}).get("observacoes"),
                 "simplesSegundos": (b.get("simples") or b.get("recalculoCompletoRaw") or {}).get("segundos"),
                 "incremental": b.get("jobRegimeTurno") or b.get("jobRegime"),
                 "fonte": BENCH.name}
    return J({"asOf": asof, "configVersao": cfg["versao"], "desenhoConfigurado": {
        k: cfg.get(k) for k in ("modoMaterializacao", "granularidadeBucket")},
        "mesmoAgregado": iguais, "desenhos": resultado, "contagens": contagens,
        "benchmarkEscala": bench})


# ---- janela móvel -----------------------------------------------------------

@app.post("/api/avancar")
def avancar_api(body: dict = Body(default={})):
    d = db()
    with _escrita:
        try:
            dias = int(body.get("dias", 1))
            if not 1 <= dias <= 31:
                raise ValueError("dias deve estar entre 1 e 31")
            passos = avancar(d, dias)
        except LockOcupado as e:
            return J({"erro": str(e)}, 409)
    return J([{**{k: v for k, v in p.items() if k != "run"}, **_run_api(d, p["run"])}
              for p in passos])


@app.get("/api/janela")
def janela_api(asOf: str | None = None):
    d = db()
    cfg = config_mod.ler(d)
    tz = cfg["timezone"]
    asof = parse_asof(_asof(asOf))
    ji, jf = janela(asof, cfg)
    ini, fim = ji.astimezone(ZoneInfo(tz)).date(), jf.astimezone(ZoneInfo(tz)).date()
    # bucket count por dia nas bordas: o que acabou de sair, as primeiras e as últimas datas
    def por_dia(a, b):
        res = d.trecho_bucket_diario.aggregate([
            {"$match": {"dataLocal": {"$gte": inicio_dia(a, tz), "$lt": inicio_dia(b, tz)}}},
            {"$group": {"_id": "$dataLocal", "buckets": {"$sum": 1}, "obs": {"$sum": "$n"}}}])
        m = {r["_id"].astimezone(ZoneInfo(tz)).date(): r for r in res}
        return [{"dia": (a + timedelta(days=i)).isoformat(),
                 "buckets": m.get(a + timedelta(days=i), {}).get("buckets", 0),
                 "obs": m.get(a + timedelta(days=i), {}).get("obs", 0)}
                for i in range((b - a).days)]
    hoje_raw = d.trecho_observacoes.count_documents(
        {"observadoEm": {"$gte": jf, "$lt": inicio_dia(fim + timedelta(days=1), tz)}})
    return J({"asOf": asof.isoformat(), "inicio": ini.isoformat(), "fimExclusivo": fim.isoformat(),
              "diaQueSaiu": (ini - timedelta(days=1)).isoformat(),
              "diaQueEntrou": (fim - timedelta(days=1)).isoformat(),
              "inicioDias": por_dia(ini - timedelta(days=3), ini + timedelta(days=4)),
              "fimDias": por_dia(fim - timedelta(days=6), fim),
              "hojeObservacoesNaRaw": hoje_raw, "modoLimpezaCamada2": cfg["modoLimpezaCamada2"]})


# ---- config -----------------------------------------------------------------

@app.get("/api/config")
def get_config():
    return J(config_mod.ler(db()))


@app.post("/api/config")
def post_config(body: dict = Body(...)):
    """Muda a config e, com `rerodarCamada2`, recalcula o mínimo necessário.

    simples: relê a raw (é o desenho). incremental/hora: só a camada 2, raw intacta.
    incremental/turno: turnos e regra estão gravados nos buckets, então refaz as duas.
    """
    d = db()
    mudancas = body.get("mudancas", {})
    with _escrita:
        antes_raw = d.trecho_observacoes.estimated_document_count()
        b_antes = d.trecho_bucket_diario.find_one(sort=[("atualizadoEm", -1)],
                                                  projection={"runId": 1, "atualizadoEm": 1})
        cfg = config_mod.atualizar(d, mudancas) if mudancas else config_mod.ler(d)
        saida = {"config": cfg}
        if body.get("rerodarCamada2"):
            hora = (cfg.get("modoMaterializacao") == "incremental"
                    and cfg.get("granularidadeBucket") == "hora")
            camada = "2" if hora else "todas"
            try:
                run = materializar(d, _asof(body.get("asOf")), camada)
            except LockOcupado as e:
                return J({"erro": f"config v{cfg['versao']} salva, mas a camada 2 não foi "
                                  f"recalculada: {e}", "config": cfg}, 409)
            b_depois = d.trecho_bucket_diario.find_one(sort=[("atualizadoEm", -1)],
                                                       projection={"runId": 1, "atualizadoEm": 1})
            saida.update(_run_api(d, run))
            st = run["stats"]
            saida["provaRawIntacta"] = {
                "desenho": "incremental/hora" if hora else (
                    "simples" if "simples" in st else "incremental/turno"),
                "camada1Executada": "camada1" in st,
                "observacoesRawLidas": (st["simples"]["lidos"] if "simples" in st else
                                        st.get("camada1", {}).get("lidos", 0)),
                "bucketsLidos": st.get("camada2", {}).get("lidos", 0),
                "rawDocsAntes": antes_raw,
                "rawDocsDepois": d.trecho_observacoes.estimated_document_count(),
                "ultimoBucketRunIdAntes": (b_antes or {}).get("runId"),
                "ultimoBucketRunIdDepois": (b_depois or {}).get("runId"),
            }
    return J(saida)


# ---- por baixo do capô -------------------------------------------------------

@app.get("/api/capo")
def capo(asOf: str | None = None):
    d = db()
    return J({"pipelines": pipelines_atuais(d, _asof(asOf)), "colecoes": metadados(d, cache=False)})


# ---- UI compilada (make ui-build) --------------------------------------------

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(DIST / "index.html")
