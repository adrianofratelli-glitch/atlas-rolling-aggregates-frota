"""Fixtures de teste: banco `*_test` com validators e índices; dados zerados por teste."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.db import get_db  # noqa: E402
from frota.schemas import VALIDATORS  # noqa: E402

TEST_DB = settings.MONGODB_TEST_DB
assert TEST_DB.endswith("_test"), "testes só rodam em banco *_test"


@pytest.fixture(scope="session")
def db_sessao():
    db = get_db(TEST_DB)
    db.client.admin.command("ping")
    bootstrap(db)
    return db


@pytest.fixture
def db(db_sessao):
    """Esvazia todas as collections; validators e índices ficam."""
    for nome in VALIDATORS:
        db_sessao[nome].delete_many({})
    return db_sessao
