"""Caos real no MongoDB do docker: congela o mongod no meio do job e da consulta.

    FROTA_MONGO=local .venv/bin/python scripts/caos_local.py

1. job da carga inicial começa; o container é pausado por N s (`docker pause`);
2. durante a pausa, a consulta de fallback falha rápido (serverSelectionTimeout) em vez
   de pendurar; a API traduziria em 503;
3. o container volta; o job termina sozinho (retry/reconexão do driver) e o resultado é
   idêntico ao de um run sem falha.
Usa o banco frota_eta_caos_test e só o container desta POV.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

os.environ["FROTA_MONGO"] = "local"
import _path  # noqa: E402,F401

from pymongo import MongoClient  # noqa: E402

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.consulta import fallback  # noqa: E402
from frota.db import CODEC, get_db  # noqa: E402
from frota.job import materializar  # noqa: E402
from frota.seed import seed  # noqa: E402

CONTAINER = "frota-eta-mongo"
PAUSA_S = int(os.getenv("PAUSA_S", "8"))
ASOF = "2026-10-16"
NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0}
assert settings.ALVO == "local"


def docker(*args):
    subprocess.run(["docker", *args], check=True, capture_output=True)


def negocio(db):
    return list(db.trecho_media_historica.find({}, NEG).sort(
        [("origem", 1), ("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]))


db = get_db("frota_eta_caos_test")
db.config.delete_many({})
bootstrap(db)
seed(db, "small", 42, ASOF, log=None)
materializar(db, ASOF)
referencia = negocio(db)
db.trecho_bucket_diario.delete_many({})
db.trecho_media_historica.delete_many({})
db.job_runs.delete_many({})
print(f"referência: {len(referencia)} médias; refazendo a carga com o mongod congelado {PAUSA_S}s")

resultado = {}


def roda():
    t0 = time.perf_counter()
    try:
        resultado["run"] = materializar(db, ASOF)
    except Exception as e:  # noqa: BLE001
        resultado["erro"] = repr(e)
    resultado["s"] = time.perf_counter() - t0


t = threading.Thread(target=roda)
t.start()
time.sleep(1.0)
docker("pause", CONTAINER)
print(f"[{time.strftime('%X')}] mongod pausado")
rapido = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500, socketTimeoutMS=1500)
t0 = time.perf_counter()
try:
    fallback(rapido.get_database(db.name, codec_options=CODEC), "BASE-001", "POSTO-0001",
             "CARRETA", "2026-10-16T20:00:00-03:00")
    consulta = "respondeu (inesperado)"
except Exception as e:  # noqa: BLE001
    consulta = f"falhou em {time.perf_counter() - t0:.1f}s com {type(e).__name__} (sem pendurar)"
print(f"consulta durante a pausa: {consulta}")
time.sleep(max(0, PAUSA_S - (time.perf_counter() - t0)))
docker("unpause", CONTAINER)
print(f"[{time.strftime('%X')}] mongod de volta")
t.join(timeout=600)

ok = "run" in resultado and resultado["run"]["status"] == "ok" and negocio(db) == referencia
if "run" in resultado:
    c1 = resultado["run"]["stats"]["camada1"]
    print(f"job: {resultado['run']['status']} em {resultado['s']:.1f}s · tentativas camada 1: "
          f"{c1['tentativas']} {c1['errosTransitorios'][:1]}")
else:
    print(f"job falhou: {resultado.get('erro')}")
print("resultado idêntico ao run sem falha" if ok else "DIVERGÊNCIA")
sys.exit(0 if ok else 1)
