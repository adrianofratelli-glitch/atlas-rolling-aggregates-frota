"""Documento único versionado `config` (`_id: "ativa"`)."""
from __future__ import annotations

from pymongo.database import Database

from . import settings
from .janela import validar_turnos

CAMPOS_EDITAVEIS = {"turnos", "regraNoite", "minAmostras", "modoLimpezaCamada2",
                    "kReprocessamento", "janelaDias"}


def validar(cfg: dict) -> None:
    validar_turnos(cfg["turnos"])
    if cfg["regraNoite"] not in ("dia_civil", "dia_operacional"):
        raise ValueError("regraNoite deve ser dia_civil ou dia_operacional")
    if cfg["modoLimpezaCamada2"] not in ("merge_runid", "out"):
        raise ValueError("modoLimpezaCamada2 deve ser merge_runid ou out")
    for campo in ("janelaDias", "kReprocessamento", "minAmostras"):
        if int(cfg[campo]) < 1:
            raise ValueError(f"{campo} deve ser ≥ 1")


def garantir(db: Database) -> dict:
    """Cria o documento a partir do `.env` se ainda não existir; devolve o vigente."""
    inicial = settings.config_inicial()
    validar(inicial)
    r = db.config.update_one({"_id": "ativa"}, {"$setOnInsert": inicial}, upsert=True)
    cfg = db.config.find_one({"_id": "ativa"})
    # config recém-criada (ou recriada depois de um reset) reescreve a versão arquivada
    if r.upserted_id is not None or not db.config_versoes.find_one({"_id": cfg["versao"]}, {"_id": 1}):
        _arquivar(db, cfg)
    return cfg


def _arquivar(db: Database, cfg: dict) -> None:
    _VERSOES.pop((db.name, cfg["versao"]), None)
    db.config_versoes.replace_one({"_id": cfg["versao"]}, {**cfg, "_id": cfg["versao"]},
                                  upsert=True)


_VERSOES: dict[tuple[str, int], dict] = {}
_VIGENTE: dict[str, tuple[float, dict]] = {}
VIGENTE_TTL_S = 10.0


def versao(db: Database, numero: int) -> dict | None:
    """Config exatamente como estava na versão `numero` (imutável: cache sem expiração)."""
    chave = (db.name, numero)
    if chave not in _VERSOES:
        doc = db.config_versoes.find_one({"_id": numero})
        if not doc:
            return None
        _VERSOES[chave] = {**doc, "_id": "ativa"}
    return _VERSOES[chave]


def vigente_em_cache(db: Database) -> dict:
    """Config vigente com cache de 10 s, para a consulta de fallback (caminho quente).

    Seguro porque o fallback deriva dow/turno pela versão gravada no próprio agregado;
    da vigente ele só usa `minAmostras` e o fuso para responder sem histórico.
    """
    import time as _t
    agora = _t.monotonic()
    if db.name not in _VIGENTE or agora - _VIGENTE[db.name][0] > VIGENTE_TTL_S:
        _VIGENTE[db.name] = (agora, ler(db))
    return _VIGENTE[db.name][1]


def ler(db: Database) -> dict:
    cfg = db.config.find_one({"_id": "ativa"})
    if cfg is None:
        return garantir(db)
    return cfg


def atualizar(db: Database, mudancas: dict) -> dict:
    """Aplica mudanças editáveis, valida e incrementa `versao`."""
    desconhecidos = set(mudancas) - CAMPOS_EDITAVEIS
    if desconhecidos:
        raise ValueError(f"campos não editáveis: {sorted(desconhecidos)}")
    atual = ler(db)
    novo = {**atual, **mudancas}
    validar(novo)
    novo["versao"] = atual["versao"] + 1
    r = db.config.replace_one({"_id": "ativa", "versao": atual["versao"]}, novo)
    if r.matched_count == 0:
        raise ValueError("config alterada por outra pessoa ao mesmo tempo; recarregue e tente de novo")
    _arquivar(db, novo)
    _VIGENTE.pop(db.name, None)
    return ler(db)
