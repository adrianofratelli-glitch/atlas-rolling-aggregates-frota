"""'Por baixo do capô': metadados lidos do banco e badges derivados do que rodou."""
from __future__ import annotations

import json
from datetime import timedelta

from pymongo.database import Database

from . import config as config_mod
from .janela import inicio_dia, janela, parse_asof
from .mongosh import para_mongosh, pipeline_mongosh
from .pipelines import camada1, camada2, comentados, raw_onthefly, simples

DIA_S = 86400


_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_S = 600.0  # índices e validators só mudam com bootstrap/deploy
_RENOVANDO: set[str] = set()


def invalidar() -> None:
    _CACHE.clear()


def metadados(db: Database, cache: bool = True) -> dict:
    """Validators (listCollections) e índices/TTL (listIndexes) — nada hardcoded.

    Cache por banco para os badges: com o banco remoto são ~13 idas e voltas por chamada.
    Job, avanço e config não mudam índices nem validators (o `$out` os preserva). A aba "Por baixo do capô" lê sempre ao vivo (`cache=False`).
    """
    import threading
    import time as _t
    if cache and db.name in _CACHE:
        quando, valor = _CACHE[db.name]
        if _t.monotonic() - quando >= CACHE_S and db.name not in _RENOVANDO:
            # expirado: devolve o anterior e renova em segundo plano (nunca trava a tela)
            _RENOVANDO.add(db.name)
            threading.Thread(target=lambda: (metadados(db, cache=False),
                                             _RENOVANDO.discard(db.name)), daemon=True).start()
        return valor
    saida = {}
    for c in db.command("listCollections", filter={"type": "collection"})["cursor"]["firstBatch"]:
        nome = c["name"]
        if nome.startswith("system.") or nome.startswith("bench_"):
            continue
        opts = c.get("options", {})
        idx = []
        for i in db[nome].list_indexes():
            item = {"nome": i["name"], "chave": dict(i["key"]), "unique": bool(i.get("unique"))}
            if "expireAfterSeconds" in i:
                item["ttlSegundos"] = i["expireAfterSeconds"]
                item["ttlDias"] = round(i["expireAfterSeconds"] / DIA_S, 2)
            idx.append(item)
        saida[nome] = {"validator": opts.get("validator"),
                       "validationLevel": opts.get("validationLevel"),
                       "validationAction": opts.get("validationAction"),
                       "indices": idx, "docsEstimados": db[nome].estimated_document_count()}
    _CACHE[db.name] = (_t.monotonic(), saida)
    return saida


def badges(db: Database, colecoes: list[str], pipelines: list[list[dict]] | None = None,
           indices_usados: list[str] | None = None) -> list[dict]:
    """Badges a partir dos estágios enviados e dos metadados reais das collections."""
    meta = metadados(db)
    texto = json.dumps(pipelines or [], default=str)
    estagios = [e["estagio"] for p in (pipelines or []) for e in p]
    out: list[dict] = []

    def add(nome, motivo):
        if nome not in {b["badge"] for b in out}:
            out.append({"badge": nome, "motivo": motivo})

    for e in estagios:
        if "$merge" in e:
            m = e["$merge"]
            add("$merge", f"estágio $merge em {m['into']} (whenMatched: {m['whenMatched']})")
            alvo = meta.get(m["into"], {})
            unico = [i for i in alvo.get("indices", []) if i["unique"]
                     and list(i["chave"]) == list(m["on"])]
            if unico:
                add("unique index", f"$merge.on usa {unico[0]['nome']}")
            colecoes = colecoes + [m["into"]]
        if "$out" in e:
            add("$out", f"estágio $out em {e['$out']}")
            colecoes = colecoes + [e["$out"]]
    if '"$dateTrunc"' in texto and '"timezone"' in texto:
        add("$dateTrunc com timezone", "pipeline trunca o dia no fuso da config")
    for c in colecoes:
        if c == "trecho_bucket_diario":
            add("Bucket Pattern", "lê/grava buckets dia × hora com soma e contagem")
        if c == "trecho_bucket_turno":
            add("Bucket Pattern", "lê/grava buckets dia × turno com soma e contagem")
        if c == "trecho_media_historica":
            add("Computed Pattern", "média pré-calculada lida/gravada pronta")
        m = meta.get(c, {})
        for i in m.get("indices", []):
            if "ttlSegundos" in i:
                add("TTL", f"{c}.{i['nome']} expira em {i['ttlDias']} d")
        if (m.get("validator") or {}).get("$jsonSchema"):
            add("$jsonSchema", f"{c}: validationLevel {m['validationLevel']}")
    for nome in indices_usados or []:
        for c in colecoes:
            for i in meta.get(c, {}).get("indices", []):
                if i["nome"] == nome and i["unique"]:
                    add("unique index", f"consulta usou {nome} (IXSCAN)")
    return out


def pipelines_atuais(db: Database, asof: str) -> dict:
    """Os pipelines que o job e a consulta enviariam agora, em mongosh e em JSON."""
    cfg = config_mod.ler(db)
    tz = cfg["timezone"]
    d = parse_asof(asof)
    ji, jf = janela(d, cfg)
    k = cfg["kReprocessamento"]
    intervalo = [(inicio_dia(d - timedelta(days=k), tz), inicio_dia(d, tz))]
    por_turno = cfg.get("granularidadeBucket", "turno") == "turno"
    c1 = comentados(camada1.pipeline_turno(intervalo, "<runId>", cfg) if por_turno
                    else camada1.pipeline(intervalo, "<runId>", tz))
    c2 = comentados(camada2.pipeline(ji, jf, asof, cfg, "<runId>"))
    sp = comentados(simples.pipeline(ji, jf, asof, cfg, "<runId>"))
    raw = comentados(raw_onthefly.pipeline("BASE-001", "POSTO-0042", "BITREM", ji, jf, cfg))
    filtro = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}
    return {
        "desenho": {k: cfg.get(k) for k in ("modoMaterializacao", "granularidadeBucket",
                                            "modoLimpezaCamada2", "incluirDow")},
        "simples": {"colecao": "trecho_observacoes", "pipeline": sp,
                    "mongosh": pipeline_mongosh("trecho_observacoes", sp)},
        "camada1": {"colecao": "trecho_observacoes", "pipeline": c1,
                    "mongosh": pipeline_mongosh("trecho_observacoes", c1)},
        "camada2": {"colecao": camada2.colecao_origem(cfg), "pipeline": c2,
                    "mongosh": pipeline_mongosh(camada2.colecao_origem(cfg), c2)},
        "fallback": {"colecao": "trecho_media_historica", "filtro": filtro,
                     "mongosh": f"db.trecho_media_historica.find({para_mongosh(filtro)})"
                                ".explain('executionStats')"},
        "rawOnTheFly": {"colecao": "trecho_observacoes", "pipeline": raw,
                        "mongosh": pipeline_mongosh("trecho_observacoes", raw)},
        "asOf": asof, "configVersao": cfg["versao"],
    }
