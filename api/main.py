"""API da POV v2: serve o roteiro guiado de 5 passos. A UI é só vitrine.

    uvicorn api.main:app --port 8410

`datetime.now()` só aqui (entrypoints); os módulos recebem `agora` por parâmetro.
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from frota import cenario, ingestao, previa, seed as seed_mod, settings
from frota.bootstrap import bootstrap
from frota.colecoes import COLECOES
from frota.db import get_db, mascarar
from frota.janela import ATALHOS, DOW_NOMES, hoje_local, janela_padrao
from frota.job import rodar_job
from frota.mongosh import jsonavel
from frota.operadores import bloco_query
from frota.pipelines import job as job_pipe
from frota.schemas import TIPOS_VEICULO

@asynccontextmanager
async def _ciclo(_app):
    # aquece a lista de veículos sem travar a subida da API
    threading.Thread(target=_aquecer_veiculos, daemon=True).start()
    yield


app = FastAPI(lifespan=_ciclo, title="Agregados em janela móvel — fallback de ETA", version="2.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5410",
                                                  "http://localhost:5410"],
                   allow_methods=["*"], allow_headers=["*"])

_boot: set[str] = set()
_reset = {"resetando": False, "etapa": None, "pct": 0.0, "erro": None, "fim": None}
_trava = threading.Lock()
RAW = "trecho_observacoes"
BASE = job_pipe.COLECAO
_PRIVADOS = {"owner"}
_cache_previa: dict = {}  # a prévia agrupa 180 dias de raw (segundos no Atlas): ver previa.proximo
# (banco, runId do último job ok) → veículos por tipo: seed ou job novo (API ou CLI) invalida
_cache_veiculos: dict = {}
_trava_veiculos = threading.Lock()


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def db():
    """Durante o reset não faz bootstrap: ele recriaria collections no meio do drop/seed."""
    d = get_db(settings.MONGODB_DB)
    with _trava:
        if not _reset["resetando"] and d.name not in _boot:
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
    # "base gerada em" vem do último run que deu certo; um erro mais recente vai à parte
    ultimo = d.job_runs.find_one({"status": "ok"}, sort=[("iniciadoEm", -1)])
    recente = d.job_runs.find_one({}, sort=[("iniciadoEm", -1)])
    erro = recente if recente and recente.get("status") != "ok" else None
    hh, mm = settings.JOB_HORA_LOCAL
    return J({"alvo": settings.ALVO, "agora": agora, "dataRef": data_ref.isoformat(),
              "janela": {"inicio": ini, "fim": fim, "dias": settings.JANELA_DIAS},
              "ultimoJob": ultimo, "ultimoErro": erro, "simuladoAte": ingestao.simulado_ate(d),
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
             "esparso": bool(t.get("esparso", False)),
             "tipos": t.get("tiposVeiculo") or TIPOS_VEICULO}
            for t in d.trechos.find({}).sort([("origem", 1), ("destino", 1)])]


def _veiculos(d) -> dict[str, list[str]]:
    run = d.job_runs.find_one({"status": "ok"}, {"runId": 1}, sort=[("iniciadoEm", -1)])
    chave = (d.name, run.get("runId") if run else None)
    with _trava_veiculos:
        achado = _cache_veiculos.get(chave)
    if achado is not None:
        return achado
    achado = cenario.veiculos_por_tipo(d)
    with _trava_veiculos:
        _cache_veiculos.clear()  # só a versão atual importa
        _cache_veiculos[chave] = achado
    return achado


def _aquecer_veiculos() -> None:
    """Calcula a lista uma vez ao subir; se falhar, a primeira requisição calcula."""
    try:
        _veiculos(db())
    except Exception:  # noqa: BLE001 — aquecimento é opcional
        pass



@app.get("/api/opcoes")
def opcoes():
    d = db()
    return J({"trechos": _trechos(d), "tipos": TIPOS_VEICULO, "veiculos": _veiculos(d),
              "atalhos": {k: {"inicio": a, "fim": b} for k, (a, b) in ATALHOS.items()},
              "dias": DOW_NOMES})


# ---- collections e script do trigger -----------------------------------------

def _info_colecoes(d) -> dict[str, dict]:
    """Validator e índices de verdade (do banco), por collection."""
    achadas = {c["name"]: c for c in
               d.command("listCollections", filter={"type": "collection"})["cursor"]["firstBatch"]}
    saida = {}
    for nome in achadas:
        validator = achadas[nome].get("options", {}).get("validator")
        indices = [{"nome": i["name"], "chave": dict(i["key"]),
                    **({"unico": True} if i.get("unique") else {}),
                    **({"ttlSegundos": i["expireAfterSeconds"]}
                       if "expireAfterSeconds" in i else {})}
                   for i in d[nome].list_indexes()]
        saida[nome] = {"validator": validator, "indices": indices,
                       "docs": d[nome].estimated_document_count()}
    return saida


@app.get("/api/colecoes")
def colecoes():
    """O schema de cada collection (do banco) com a explicação escrita à mão. Sem amostra."""
    if _resetando():
        return _ocupado()
    d = db()
    info = _info_colecoes(d)
    lista = []
    for c in COLECOES:
        real = info.get(c["nome"], {})
        js = (real.get("validator") or {}).get("$jsonSchema", {})
        props, req = js.get("properties", {}), set(js.get("required", []))
        campos = [{"nome": k, "descricao": txt, "schema": props.get(k),
                   "obrigatorio": k in req} for k, txt in c["campos"].items()]
        lista.append({**{k: c[k] for k in ("nome", "papel", "grava", "le", "retencao", "exemplo")},
                      "campos": campos, "docs": real.get("docs"),
                      "indices": [{**i, "porque": c["porque_indice"].get(i["nome"], "")}
                                  for i in real.get("indices", [])]})
    return J({"colecoes": lista, "ingestao": ingestao.bloco(agora_utc())})


TRIGGER_DIR = Path(__file__).resolve().parent.parent / "atlas-trigger"


@app.get("/api/trigger-script")
def trigger_script():
    """O que o Atlas Scheduled Trigger roda: a Function e a configuração do agendamento."""
    arquivos = [("funcao", "functions/rodarJob.js"), ("trigger", "triggers/jobDiario.json")]
    return J({k: {"arquivo": f"atlas-trigger/{rel}",
                  "codigo": (TRIGGER_DIR / rel).read_text(encoding="utf-8")}
              for k, rel in arquivos}
             | {"cron": settings.CRON_JOB_UTC,
                "horarioLocal": "{:02d}:{:02d}".format(*settings.JOB_HORA_LOCAL)})


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
    d = db()
    return J(cenario.consultar(d, f, agora_utc(), _veiculos(d)))


@app.get("/api/proximo-job")
def proximo_job():
    return J(previa.proximo(db(), agora_utc(), cache=_cache_previa))


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
    with _trava_veiculos:
        _cache_veiculos.clear()


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
