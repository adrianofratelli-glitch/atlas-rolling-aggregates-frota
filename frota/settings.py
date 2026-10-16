"""Configuração de processo, lida do `.env`.

O que é regra de negócio (turnos, janela, k, amostragem mínima) mora na collection
`config`; o `.env` só fornece o valor inicial quando o documento ainda não existe.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

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
MONGODB_FIXTURES_DB = os.getenv("MONGODB_FIXTURES_DB", "frota_eta_fixtures")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8410"))
SEED = int(os.getenv("SEED", "42"))


def config_inicial() -> dict:
    """Documento `config` usado quando o banco ainda não tem um."""
    return {
        "_id": "ativa",
        "versao": 1,
        "timezone": os.getenv("FROTA_TIMEZONE", "America/Sao_Paulo"),
        "janelaDias": int(os.getenv("FROTA_JANELA_DIAS", "180")),
        "turnos": [
            {"codigo": "M", "inicioHora": 6, "fimHora": 12},
            {"codigo": "T", "inicioHora": 12, "fimHora": 18},
            {"codigo": "N", "inicioHora": 18, "fimHora": 6},
        ],
        "regraNoite": os.getenv("FROTA_REGRA_NOITE", "dia_civil"),
        "kReprocessamento": int(os.getenv("FROTA_K_REPROCESSAMENTO", "3")),
        "minAmostras": int(os.getenv("FROTA_MIN_AMOSTRAS", "5")),
        "modoLimpezaCamada2": os.getenv("FROTA_MODO_LIMPEZA_CAMADA2", "merge_runid"),
        "ttlRawDias": int(os.getenv("FROTA_TTL_RAW_DIAS", "200")),
        "ttlBucketDias": int(os.getenv("FROTA_TTL_BUCKET_DIAS", "190")),
    }
