"""API da POV v2: serve o roteiro guiado de 7 passos. A UI é só vitrine.

    uvicorn api.main:app --port 8410

`datetime.now()` só aqui (entrypoints); os módulos recebem `agora` por parâmetro.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from frota import cenario, ingestao, previa, seed as seed_mod, settings
from frota.bootstrap import bootstrap
from frota.db import get_db, mascarar
from frota.janela import ATALHOS, DOW_NOMES, hoje_local, janela_padrao
from frota.job import rodar_job
from frota.mongosh import jsonavel, para_mongosh
from frota.operadores import bloco_query
from frota.pipelines import job as job_pipe
from frota.schemas import TIPOS_VEICULO

app = FastAPI(title="Agregados em janela móvel — fallback de ETA", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5410",
                                                  "http://localhost:5410"],
                   allow_methods=["*"], allow_headers=["*"])

_boot: set[str] = set()
_reset = {"resetando": False, "etapa": None, "pct": 0.0, "erro": None, "fim": None}
_trava = threading.Lock()
RAW = "trecho_observacoes"
BASE = job_pipe.COLECAO
_PRIVADOS = {"owner"}


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def db():
    d = get_db(settings.MONGODB_DB)
    if d.name not in _boot:
        bootstrap(d)
        _boot.add(d.name)
    return d


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


def _resetando() -> bool:
    with _trava:
        return _reset["resetando"]


def _ocupado():
    return J({"erro": "a demo está sendo recriada", "acao": "aguarde o reset terminar"}, 409)


@app.exception_handler(PyMongoError)
def _mongo_fora(_, exc):
    _boot.clear()
    return J({"erro": mascarar(f"MongoDB indisponível ou com erro: {type(exc).__name__}"),
              "detalhe": mascarar(str(exc)[:300]),
              "acao": "verifique a conexão com o MongoDB"}, 503)


@app.exception_handler(ValueError)
def _valor(_, exc):
    return J({"erro": str(exc), "acao": "corrija o valor informado e tente de novo"}, 422)


@app.get("/health/live")
def live():
    return {"ok": True}


@app.get("/health/ready")
def ready():
    d = db()
    d.command("ping")
    return {"ok": True, "db": d.name}


# ---- estado e opções --------------------------------------------------------

@app.get("/api/estado")
def estado():
    d = db()
    agora = agora_utc()
    data_ref = hoje_local(agora)
    ini, fim = janela_padrao(data_ref)
    ultimo = d.job_runs.find_one({}, sort=[("iniciadoEm", -1)])
    hh, mm = settings.JOB_HORA_LOCAL
    return J({"alvo": settings.ALVO, "agora": agora, "dataRef": data_ref.isoformat(),
              "janela": {"inicio": ini, "fim": fim, "dias": settings.JANELA_DIAS},
              "ultimoJob": ultimo, "simuladoAte": ingestao.simulado_ate(d),
              "resetando": _resetando(),
              "trigger": {"implantado": settings.ALVO == "atlas"
                          and bool(os.getenv("APPSERVICES_APP_ID", "").strip()),
                          "horarioLocal": f"{hh:02d}:{mm:02d}",
                          "cron": settings.CRON_JOB_UTC,
                          "ingestaoCron": settings.CRON_INGESTAO_UTC}})


def _trechos(d) -> list[dict]:
    nomes = {p["_id"]: p["nome"] for p in d.pontos.find({}, {"nome": 1})}
    return [{"origem": t["origem"], "destino": t["destino"],
             "nomeOrigem": nomes.get(t["origem"], t["origem"]),
             "nomeDestino": nomes.get(t["destino"], t["destino"]),
             "esparso": bool(t.get("esparso", False))}
            for t in d.trechos.find({}).sort([("origem", 1), ("destino", 1)])]


@app.get("/api/opcoes")
def opcoes():
    return J({"trechos": _trechos(db()), "tipos": TIPOS_VEICULO,
              "atalhos": {k: {"inicio": a, "fim": b} for k, (a, b) in ATALHOS.items()},
              "dias": DOW_NOMES})


# ---- raw --------------------------------------------------------------------

def _amostra(docs: list[dict], n: int = 12) -> list[dict]:
    """Um doc por dia local (o mais recente do dia), espalhado ao longo do período."""
    from frota.janela import hoje_local as dia
    por_dia: dict = {}
    for x in docs:
        por_dia.setdefault(dia(x["observadoEm"]), x)
    dias = sorted(por_dia)
    if len(dias) > n:
        passo = (len(dias) - 1) / (n - 1)
        dias = [dias[round(i * passo)] for i in range(n)]
    return sorted((por_dia[k] for k in dias), key=lambda x: x["observadoEm"])


@app.get("/api/raw")
def raw(origem: str | None = None, destino: str | None = None,
        tipoVeiculo: str | None = None):
    if _resetando():
        return _ocupado()
    d = db()
    if not origem or not destino:
        t = next((t for t in _trechos(d) if not t["esparso"]), None)
        if t is None:
            raise ValueError("Não há trechos na base; recrie a demo.")
        origem, destino = origem or t["origem"], destino or t["destino"]
    tipo = tipoVeiculo or "CARRETA"
    filtro = {"origem": origem, "destino": destino, "tipoVeiculo": tipo}
    docs = list(d[RAW].find(filtro).sort("observadoEm", -1).limit(600))
    info = d.command("listCollections", filter={"name": RAW})["cursor"]["firstBatch"]
    validator = (info[0].get("options", {}).get("validator") if info else None)
    indices = [{"nome": i["name"], "chave": dict(i["key"]),
                **({"unico": True} if i.get("unique") else {}),
                **({"ttlSegundos": i["expireAfterSeconds"]}
                   if "expireAfterSeconds" in i else {})}
               for i in d[RAW].list_indexes()]
    query = {"le": [RAW], "grava": [], "operacao": "find", "operadores": [],
             "mongosh": f"db.{RAW}.find({para_mongosh(filtro)}).sort({{ observadoEm: -1 }})"
                        f".limit(600)"}
    return J({"filtro": filtro, "amostra": _amostra(docs),
              "schema": {"validator": validator, "indices": indices}, "query": query})


# ---- job, cenário, prévia ---------------------------------------------------

@app.post("/api/job")
def job():
    if _resetando():
        return _ocupado()
    d = db()
    r = rodar_job(d, hoje_local(agora_utc()), origem="botao")
    return J({**r, "query": bloco_query(RAW, r["pipeline"], [RAW], [BASE])})


@app.post("/api/cenario")
def cenario_api(body: dict = Body(...)):
    if _resetando():
        return _ocupado()
    try:
        f = cenario.Filtro(**body)
    except TypeError as e:
        raise ValueError(f"Campos do cenário inválidos: {e}")
    f.validar()
    return J(cenario.consultar(db(), f, agora_utc()))


@app.get("/api/proximo-job")
def proximo_job():
    return J(previa.proximo(db(), agora_utc()))


@app.get("/api/job_runs")
def job_runs(limite: int = Query(10, ge=1, le=100)):
    return J(list(db().job_runs.find({}).sort("iniciadoEm", -1).limit(limite)))


# ---- reset ------------------------------------------------------------------

def _progresso(etapa: str, pct: float) -> None:
    with _trava:
        _reset.update(etapa=etapa, pct=pct)


def _executar_reset(nome: str, agora: datetime) -> None:
    erro = None
    try:
        seed_mod.resetar(get_db(nome), agora, settings.SEED, permitir=True,
                         progresso=_progresso)
    except BaseException as e:  # a thread nunca pode morrer sem liberar a trava
        erro = mascarar(f"{type(e).__name__}: {str(e)[:300]}")
    with _trava:
        _reset.update(resetando=False, erro=erro, fim=agora_utc(),
                      **({} if erro else {"etapa": "pronto", "pct": 1.0}))
    _boot.clear()


@app.post("/api/reset")
def reset():
    with _trava:
        if _reset["resetando"]:
            return J({"erro": "a demo já está sendo recriada",
                      "acao": "aguarde o reset terminar"}, 409)
        _reset.update(resetando=True, etapa="iniciando", pct=0.0, erro=None, fim=None)
    threading.Thread(target=_executar_reset, args=(settings.MONGODB_DB, agora_utc()),
                     daemon=True).start()
    return J({"iniciado": True}, 202)


@app.get("/api/reset/status")
def reset_status():
    with _trava:
        return J({k: _reset[k] for k in ("etapa", "pct", "erro", "fim")}
                 | {"resetando": _reset["resetando"]})


# ---- UI compilada (make ui-build) --------------------------------------------

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(DIST / "index.html")
