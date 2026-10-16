"""Conexão e guarda de escrita destrutiva."""
from __future__ import annotations

import os
from datetime import timezone

from bson.codec_options import CodecOptions
from pymongo import MongoClient
from pymongo.database import Database

from . import settings

_CLIENTES: dict[str, MongoClient] = {}

# Datas sempre como datetime aware em UTC: comparar um naive com um aware em Python
# é erro, e a POV inteira gira em torno de limites de janela.
CODEC = CodecOptions(tz_aware=True, tzinfo=timezone.utc)


def client(uri: str | None = None) -> MongoClient:
    uri = uri or settings.MONGODB_URI
    if uri not in _CLIENTES:
        _CLIENTES[uri] = MongoClient(uri, w="majority", retryWrites=True,
                                     serverSelectionTimeoutMS=10000, appname="frota-eta-pov")
    return _CLIENTES[uri]


def get_db(nome: str | None = None) -> Database:
    return client().get_database(nome or settings.MONGODB_DB, codec_options=CODEC)


class EscritaRecusada(SystemExit):
    """Escrita destrutiva no banco da demo sem autorização explícita."""


def guardar_escrita(nome: str) -> str:
    """Recusa operações destrutivas (drop, seed) fora de `*_test`/`*_fixtures`.

    O banco da demo só é recriado com `ALLOW_DEMO_DB_WRITE=1` — o Makefile passa a
    variável nos alvos que existem justamente para isso (`make seed`, `make reset`).
    """
    if nome.endswith("_test") or nome.endswith("_fixtures"):
        return nome
    if os.getenv("ALLOW_DEMO_DB_WRITE") == "1":
        return nome
    raise EscritaRecusada(
        f"recusado: '{nome}' não é banco *_test/*_fixtures. "
        "Use ALLOW_DEMO_DB_WRITE=1 (ou o alvo do Makefile) para recriar o banco da demo."
    )
