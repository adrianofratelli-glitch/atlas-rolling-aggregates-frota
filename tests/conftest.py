from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frota import settings  # noqa: E402
from frota.bootstrap import bootstrap  # noqa: E402
from frota.db import get_db  # noqa: E402
from tests.fixtures import dataset  # noqa: E402

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
    """Banco de teste com validators/índices, config default e fixtures carregadas.

    O bootstrap (collMod + índices) roda uma vez por sessão; por teste só a config volta
    ao default e os dados são recarregados — no Atlas cada ida e volta custa ~250 ms daqui.
    """
    from frota import config as config_mod
    db_sessao.config.delete_many({})
    db_sessao.config_versoes.delete_many({})
    config_mod.garantir(db_sessao)
    dataset.carregar(db_sessao)
    return db_sessao


def set_config(db, **mudancas):
    from frota import config
    return config.atualizar(db, mudancas)
