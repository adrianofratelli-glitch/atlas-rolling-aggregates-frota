"""Configuração de processo e constantes de negócio da v2.

Sem collection `config`: janela, amostragem mínima e retenções são constantes de código.
O `.env` só escolhe alvo (Atlas ou local), bancos, porta e semente.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- regras de negócio ------------------------------------------------------
TZ = "America/Sao_Paulo"
JANELA_DIAS = 180
MIN_AMOSTRAS = 5
TTL_RAW_DIAS = 200
DIAS_SIMULADOS = 14
TTL_SALVO_PADRAO_DIAS = 7
TTL_SALVO_MAX_DIAS = 30
JOB_HORA_LOCAL = (3, 10)
# 03:10 em America/Sao_Paulo (UTC-3) e ingestão simulada de hora em hora
CRON_JOB_UTC = "10 6 * * *"
CRON_INGESTAO_UTC = "5 * * * *"

# ---- alvo e bancos ----------------------------------------------------------
MONGODB_URI_LOCAL = os.getenv("MONGODB_URI_LOCAL", "mongodb://localhost:27027/?replicaSet=rs0")
# auto: Atlas se MONGODB_URI estiver preenchida (vem do .env.shared do portfólio), senão o
# MongoDB do docker compose. Máquina limpa sem credencial funciona sem configurar nada.
FROTA_MONGO = os.getenv("FROTA_MONGO", "auto").lower()
_ATLAS = os.getenv("MONGODB_URI", "").strip()
if FROTA_MONGO == "local" or (FROTA_MONGO == "auto" and not _ATLAS):
    MONGODB_URI, ALVO = MONGODB_URI_LOCAL, "local"
else:
    if not _ATLAS:
        raise SystemExit("FROTA_MONGO=atlas, mas MONGODB_URI está vazia")
    MONGODB_URI, ALVO = _ATLAS, "atlas"
MONGODB_DB = os.getenv("MONGODB_DB", "frota_eta")
MONGODB_TEST_DB = os.getenv("MONGODB_TEST_DB", "frota_eta_test")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8410"))
SEED = int(os.getenv("SEED", "42"))
