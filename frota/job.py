"""Job de materialização: camada 1 (raw → buckets) e camada 2 (buckets → médias).

O `$merge` não atualiza nada sozinho: quem recalcula é este job, agendado de fora
(CronJob, Cloud Scheduler, Atlas Scheduled Trigger chamando a aplicação…). Ele é:

- incremental: camada 1 só relê D-1…D-k e os dias com atraso detectado;
- idempotente: `$merge` com `whenMatched: "replace"` recalcula a chave inteira;
- exclusivo: lease em `job_locks` (um segundo job falha limpo e fica registrado);
- retomável: erro transitório reexecuta a camada inteira com o mesmo `runId`, e
  rodar de novo depois de uma falha produz o mesmo resultado.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo.database import Database
from pymongo.errors import (AutoReconnect, ConnectionFailure, DuplicateKeyError,
                            NetworkTimeout, NotPrimaryError, OperationFailure)

from . import config as config_mod
from .janela import dias, hoje_local, inicio_dia, janela, parse_asof
from .pipelines import camada1, camada2, comentados, estagios, simples

UTC = timezone.utc
LOCK_ID = "materializacao"


import re as _re

# host:porta de servidores em mensagens de erro de driver: não saem do processo
_HOST = _re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*\.(?:mongodb\.net|mongo\.cosmos\.azure\.com|internal)(?::\d+)?"
                    r"|\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?")


def mascarar(texto: str) -> str:
    return _HOST.sub("<host>", texto)


class LockOcupado(RuntimeError):
    pass


def _agora() -> datetime:
    return datetime.now(UTC)


def novo_run_id() -> str:
    return f"{_agora().strftime('%Y-%m-%dT%H:%M:%SZ')}-{uuid.uuid4().hex[:4]}"


# ---- lock (lease) -----------------------------------------------------------

def adquirir_lock(db: Database, owner: str, lease_s: int = 1800) -> None:
    """Pega o lease se não existir ou estiver expirado; senão `LockOcupado`.

    O filtro só casa com lease vencido. Se o documento existe e está válido, o upsert
    tenta inserir o mesmo `_id` e o índice de `_id` devolve DuplicateKeyError — a
    exclusão mútua é garantida pelo servidor, não por um read-then-write.
    """
    agora = _agora()
    try:
        db.job_locks.find_one_and_update(
            {"_id": LOCK_ID, "expiraEm": {"$lt": agora}},
            {"$set": {"owner": owner, "expiraEm": agora + timedelta(seconds=lease_s),
                      "adquiridoEm": agora}},
            upsert=True)
    except DuplicateKeyError:
        atual = db.job_locks.find_one({"_id": LOCK_ID}) or {}
        raise LockOcupado(f"lock '{LOCK_ID}' ocupado por {atual.get('owner')} "
                          f"até {atual.get('expiraEm')}") from None


class LockPerdido(RuntimeError):
    pass


def renovar_lock(db: Database, owner: str, lease_s: int = 1800) -> None:
    """Estende o lease e confirma o dono. Chamado antes de cada etapa destrutiva: se o
    lease venceu e outro job assumiu, este para antes de apagar o que o outro gravou."""
    r = db.job_locks.update_one({"_id": LOCK_ID, "owner": owner},
                                {"$set": {"expiraEm": _agora() + timedelta(seconds=lease_s)}})
    if r.matched_count == 0:
        raise LockPerdido(f"lease de '{LOCK_ID}' não pertence mais a {owner}")


def liberar_lock(db: Database, owner: str) -> None:
    db.job_locks.delete_one({"_id": LOCK_ID, "owner": owner})


# ---- retry ------------------------------------------------------------------

TRANSITORIOS = (AutoReconnect, ConnectionFailure, NetworkTimeout, NotPrimaryError)


def com_retry(fn, *args, tentativas: int = 4, base_s: float = 0.5, **kwargs):
    """Reexecuta a camada inteira em erro transitório; devolve (resultado, erros vistos)."""
    erros: list[str] = []
    for i in range(tentativas):
        try:
            return fn(*args, **kwargs), erros
        except OperationFailure as e:
            rotulos = ("TransientTransactionError", "RetryableWriteError")
            if not any(e.has_error_label(r) for r in rotulos) or i == tentativas - 1:
                raise
            erros.append(mascarar(f"{type(e).__name__}: {str(e)[:200]}"))
        except TRANSITORIOS as e:
            if i == tentativas - 1:
                raise
            erros.append(mascarar(f"{type(e).__name__}: {str(e)[:200]}"))
        time.sleep(base_s * 2 ** i)


# ---- camada 1 ---------------------------------------------------------------

def _intervalos(dias_proc: list[date], tz: str) -> list[tuple[datetime, datetime]]:
    """Agrupa dias consecutivos em intervalos [00:00 do 1º, 00:00 do dia após o último)."""
    saida: list[list[date]] = []
    for d in sorted(dias_proc):
        if saida and (d - saida[-1][1]).days == 1:
            saida[-1][1] = d
        else:
            saida.append([d, d])
    return [(inicio_dia(a, tz), inicio_dia(b + timedelta(days=1), tz)) for a, b in saida]


def ultimo_run_ok(db: Database, camadas: tuple[str, ...],
                  assinatura: str | None = None) -> dict | None:
    """Último run ok que executou a camada 1 (runs do modo simples não contam).

    Com `assinatura`, só runs que gravaram buckets com o mesmo grão/config: depois de
    alternar entre grãos, cada coleção de buckets só confia no próprio histórico."""
    filtro = {"status": "ok", "camada": {"$in": list(camadas)},
              "stats.camada1": {"$exists": True}}
    if assinatura is not None:
        filtro["stats.camada1.assinaturaGrao"] = assinatura
    return db.job_runs.find_one(filtro, sort=[("iniciadoEm", -1)])


def assinatura_grao(cfg: dict) -> str:
    """O que fica gravado nos buckets. Se mudar, a camada 1 refaz a janela inteira."""
    import json as _json
    g = cfg.get("granularidadeBucket", "turno")
    partes = {"granularidade": g, "timezone": cfg["timezone"]}
    if g == "turno":
        partes.update(turnos=cfg["turnos"], regraNoite=cfg["regraNoite"],
                      incluirDow=cfg.get("incluirDow", True))
    return _json.dumps(partes, sort_keys=True)


def planejar_camada1(db: Database, asof: date, cfg: dict) -> dict:
    """Decide quais dias locais reprocessar e mede os atrasados."""
    tz, k = cfg["timezone"], cfg["kReprocessamento"]
    ji, jf = janela(asof, cfg)
    dia_ini = asof - timedelta(days=cfg["janelaDias"])
    topo = db.trecho_observacoes.find_one({}, {"ingeridoEm": 1}, sort=[("ingeridoEm", -1)])
    wm_novo = topo["ingeridoEm"] if topo else None
    ultimo = ultimo_run_ok(db, ("1", "todas"), assinatura_grao(cfg))
    plano = {"watermarkNovo": wm_novo, "atrasadosDetectados": 0,
             "atrasadosForaDaJanelaK": 0, "diasAtrasados": []}
    cobertura = ((ultimo or {}).get("stats") or {}).get("camada1", {}).get("coberturaDesde")
    if ultimo is not None and (cobertura is None or parse_asof(cobertura) > dia_ini):
        # o run anterior não garante buckets completos desde o início da janela
        # (histórico antigo, buckets apagados, janela aumentada): não confiar nele
        ultimo = None
    if ultimo is None:
        # nenhum run gravou buckets com este grão/config: janela inteira
        houve_outro = ultimo_run_ok(db, ("1", "todas")) is not None
        plano["modo"] = "recarga_por_config" if houve_outro else "carga_inicial"
        base = dias(dia_ini, asof)
    else:
        plano["modo"] = "incremental"
        # D-1…D-k, estendido para trás até o asOf do último run se o job ficou parado
        inicio = max(min(asof - timedelta(days=k), parse_asof(ultimo["asOf"])), dia_ini)
        base = dias(inicio, asof)
        wm_prev = (ultimo.get("stats") or {}).get("camada1", {}).get("watermarkIngeridoEm")
        # run anterior com raw vazia não deixou watermark: tudo que existe agora é "novo"
        wm_prev = wm_prev or datetime(1970, 1, 1, tzinfo=UTC)
        if wm_novo and wm_novo > wm_prev:
            atrasos = db.trecho_observacoes.aggregate([
                {"$match": {"ingeridoEm": {"$gt": wm_prev, "$lte": wm_novo}}},
                {"$match": {"observadoEm": {"$gte": ji, "$lt": jf}}},
                {"$group": {"_id": {"$dateTrunc": {"date": "$observadoEm", "unit": "day",
                                                   "timezone": tz}}, "n": {"$sum": 1}}},
            ])
            base_set = set(base)
            for a in atrasos:
                d = a["_id"].astimezone(ZoneInfo(tz)).date()
                plano["atrasadosDetectados"] += a["n"]
                if d not in base_set:
                    plano["atrasadosForaDaJanelaK"] += a["n"]
                    plano["diasAtrasados"].append(d)
    plano["dias"] = sorted(set(base) | set(plano["diasAtrasados"]))
    plano["diasAtrasados"] = sorted(plano["diasAtrasados"])
    # carga/recarga cobre a janela inteira; incremental herda a cobertura do run anterior
    plano["coberturaDesde"] = (dia_ini if plano["modo"] != "incremental"
                               else max(parse_asof(cobertura), dia_ini)).isoformat()
    return plano


def executar_camada1(db: Database, asof: date, cfg: dict, run_id: str,
                     memo: dict | None = None) -> dict:
    """`memo` guarda plano e contagem "antes" da primeira tentativa: uma reexecução por
    erro transitório encontra buckets já gravados com o mesmo runId e não pode recontar."""
    memo = {} if memo is None else memo
    tz = cfg["timezone"]
    t0 = time.perf_counter()
    if "plano" not in memo:
        memo["plano"] = planejar_camada1(db, asof, cfg)
    plano = memo["plano"]
    dias_proc = plano["dias"]
    instantes = [inicio_dia(d, tz) for d in dias_proc]
    stats = {"modo": plano["modo"], "lidos": 0, "inseridos": 0, "atualizados": 0,
             "removidos": 0, "diasReprocessados": [d.isoformat() for d in dias_proc],
             "diasAtrasados": [d.isoformat() for d in plano["diasAtrasados"]],
             "atrasadosDetectados": plano["atrasadosDetectados"],
             "atrasadosForaDaJanelaK": plano["atrasadosForaDaJanelaK"],
             "watermarkIngeridoEm": plano["watermarkNovo"],
             "assinaturaGrao": assinatura_grao(cfg),
             "coberturaDesde": plano["coberturaDesde"],
             "granularidade": cfg.get("granularidadeBucket", "turno")}
    por_turno = stats["granularidade"] == "turno"
    if dias_proc:
        buckets = db[camada1.COLECAO_TURNO if por_turno else camada1.COLECAO_DESTINO]
        no_recorte = {"dataLocal": {"$in": instantes}}
        if "antes" not in memo:
            memo["antes"] = buckets.count_documents(no_recorte)
        antes = memo["antes"]
        intervalos = _intervalos(dias_proc, tz)
        p = (camada1.pipeline_turno(intervalos, run_id, cfg) if por_turno
             else camada1.pipeline(intervalos, run_id, tz))
        stats["pipeline"] = comentados(p)
        db.trecho_observacoes.aggregate(estagios(p), allowDiskUse=True)
        novos = list(buckets.aggregate([
            {"$match": {**no_recorte, "runId": run_id}},
            {"$group": {"_id": None, "buckets": {"$sum": 1}, "lidos": {"$sum": "$n"}}}]))
        total = novos[0]["buckets"] if novos else 0
        # dia reprocessado cujo bucket deixou de existir na raw (ex.: correção que
        # apagou observações): sobra com runId antigo e é removido aqui
        memo.get("guarda", lambda: None)()
        removidos = buckets.delete_many({**no_recorte, "runId": {"$ne": run_id}}).deleted_count
        atualizados = antes - removidos
        stats.update(lidos=novos[0]["lidos"] if novos else 0, inseridos=total - atualizados,
                     atualizados=atualizados, removidos=removidos)
    stats["duracaoMs"] = round((time.perf_counter() - t0) * 1000, 1)
    return stats


# ---- camada 2 ---------------------------------------------------------------

CHAVE = camada2.CHAVE_MEDIA


def _chaves(db: Database) -> set[tuple]:
    proj = {c: 1 for c in CHAVE} | {"_id": 0}
    return {tuple(d[c] for c in CHAVE) for d in db.trecho_media_historica.find({}, proj)}


def executar_camada2(db: Database, asof: date, cfg: dict, run_id: str,
                     memo: dict | None = None) -> dict:
    memo = {} if memo is None else memo
    t0 = time.perf_counter()
    ji, jf = janela(asof, cfg)
    media = db.trecho_media_historica
    modo = cfg["modoLimpezaCamada2"]
    p = camada2.pipeline(ji, jf, asof.isoformat(), cfg, run_id)
    fonte = db[camada2.colecao_origem(cfg)]
    lidos = fonte.count_documents({"dataLocal": {"$gte": ji, "$lt": jf}})
    if modo == "merge_runid":
        if "antes" not in memo:
            memo["antes"] = media.count_documents({})
        antes = memo["antes"]
        fonte.aggregate(estagios(p), allowDiskUse=True)
        total = media.count_documents({"runId": run_id})
        orfaos = {"runId": {"$ne": run_id}}
        amostra = list(media.find(orfaos, {c: 1 for c in CHAVE} | {"_id": 0}).limit(50))
        memo.get("guarda", lambda: None)()
        removidos = media.delete_many(orfaos).deleted_count
        atualizados = antes - removidos
        inseridos = total - atualizados
    else:
        if "antes_k" not in memo:
            memo["antes_k"] = _chaves(db)
        antes_k = memo["antes_k"]
        memo.get("guarda", lambda: None)()  # $out substitui a collection: confirma o lease antes
        fonte.aggregate(estagios(p), allowDiskUse=True)
        depois_k = _chaves(db)
        sairam = antes_k - depois_k
        amostra = [dict(zip(CHAVE, k)) for k in sorted(sairam)[:50]]
        removidos, atualizados = len(sairam), len(antes_k & depois_k)
        inseridos = len(depois_k - antes_k)
    return {"modo": modo, "fonte": fonte.name, "lidos": lidos, "inseridos": inseridos,
            "atualizados": atualizados,
            "removidos": removidos, "removidosAmostra": amostra,
            "janelaInicio": ji, "janelaFim": jf, "configVersao": cfg["versao"],
            "pipeline": comentados(p),
            "duracaoMs": round((time.perf_counter() - t0) * 1000, 1)}


# ---- modo simples -----------------------------------------------------------

def executar_simples(db: Database, asof: date, cfg: dict, run_id: str,
                     memo: dict | None = None) -> dict:
    """raw → média num pipeline só, janela inteira, `$out`."""
    memo = {} if memo is None else memo
    t0 = time.perf_counter()
    ji, jf = janela(asof, cfg)
    p = simples.pipeline(ji, jf, asof.isoformat(), cfg, run_id)
    if "antes_k" not in memo:
        memo["antes_k"] = _chaves(db)
    antes_k = memo["antes_k"]
    lidos = db.trecho_observacoes.count_documents({"observadoEm": {"$gte": ji, "$lt": jf}})
    memo.get("guarda", lambda: None)()  # $out substitui a collection: confirma o lease antes
    db.trecho_observacoes.aggregate(estagios(p), allowDiskUse=True)
    depois_k = _chaves(db)
    sairam = antes_k - depois_k
    return {"modo": "simples", "lidos": lidos, "inseridos": len(depois_k - antes_k),
            "atualizados": len(antes_k & depois_k), "removidos": len(sairam),
            "removidosAmostra": [dict(zip(CHAVE, k)) for k in sorted(sairam)[:50]],
            "janelaInicio": ji, "janelaFim": jf, "configVersao": cfg["versao"],
            "pipeline": comentados(p),
            "duracaoMs": round((time.perf_counter() - t0) * 1000, 1)}


# ---- orquestração -----------------------------------------------------------

EXECUCAO = {"modoMaterializacao", "granularidadeBucket", "modoLimpezaCamada2"}


def materializar(db: Database, asof: str | date | None = None, camada: str = "todas",
                 owner: str | None = None, lease_s: int = 1800,
                 execucao: dict | None = None) -> dict:
    """`execucao` troca só COMO se calcula (modo, grão, limpeza) sem gravar a config: o
    agregado resultante é o mesmo (teste `test_tres_modos_mesmo_agregado`)."""
    cfg = config_mod.ler(db)
    if execucao:
        if set(execucao) - EXECUCAO:
            raise ValueError(f"execucao aceita só {sorted(EXECUCAO)}")
        cfg = {**cfg, **execucao}
        config_mod.validar(cfg)
    asof_d = parse_asof(asof) if asof else hoje_local(cfg["timezone"])
    camada = str(camada)
    if camada not in ("1", "2", "todas"):
        raise ValueError("camada deve ser 1, 2 ou todas")
    modo_mat = cfg.get("modoMaterializacao", "simples")
    if modo_mat == "simples" and camada == "1":
        raise ValueError("modo simples não tem camada 1: rode camada 2 ou todas")
    if modo_mat == "incremental" and camada == "2":
        ultimo = ultimo_run_ok(db, ("1", "todas"))
        gravada = ((ultimo or {}).get("stats") or {}).get("camada1", {}).get("assinaturaGrao")
        if gravada != assinatura_grao(cfg):
            raise ValueError("os buckets foram gravados com outra config/grão (ou não existem): "
                             "rode camada 1 ou todas")
    owner = owner or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    run_id = novo_run_id()
    run = {"runId": run_id, "asOf": asof_d.isoformat(), "camada": camada,
           "modoMaterializacao": modo_mat, "status": "running",
           "owner": owner, "iniciadoEm": _agora(), "finalizadoEm": None, "stats": {},
           "erro": None, "configVersao": cfg["versao"]}
    db.job_runs.insert_one(run)
    try:
        adquirir_lock(db, owner, lease_s)
    except Exception as e:
        msg = str(e) if isinstance(e, LockOcupado) else mascarar(f"{type(e).__name__}: {e}")
        db.job_runs.update_one({"runId": run_id}, {"$set": {
            "status": "erro", "erro": msg, "finalizadoEm": _agora()}})
        raise
    try:
        stats: dict = {}
        etapas = ((("simples", executar_simples),) if modo_mat == "simples" else
                  (("camada1", executar_camada1), ("camada2", executar_camada2)))
        for nome, fn in etapas:
            if nome != "simples" and camada not in (nome[-1], "todas"):
                continue
            t0 = time.perf_counter()
            renovar_lock(db, owner, lease_s)
            guarda = lambda: renovar_lock(db, owner, lease_s)  # noqa: E731
            st, erros = com_retry(fn, db, asof_d, cfg, run_id, memo={"guarda": guarda})
            st["tentativas"] = len(erros) + 1
            st["errosTransitorios"] = erros
            st["duracaoTotalMs"] = round((time.perf_counter() - t0) * 1000, 1)
            stats[nome] = st
        partes = [stats[c] for c in ("simples", "camada1", "camada2") if c in stats]
        resumo = {campo: sum(s[campo] for s in partes)
                  for campo in ("inseridos", "atualizados", "removidos")}
        resumo["lidos"] = partes[0]["lidos"]
        resumo["diasReprocessados"] = stats.get("camada1", {}).get("diasReprocessados", [])
        fim = {"status": "ok", "finalizadoEm": _agora(), "stats": {**resumo, **stats},
               "atrasadosForaDaJanelaK": stats.get("camada1", {}).get("atrasadosForaDaJanelaK", 0)}
        db.job_runs.update_one({"runId": run_id}, {"$set": fim})
        return {**run, **fim}
    except Exception as e:
        db.job_runs.update_one({"runId": run_id}, {"$set": {
            "status": "erro", "erro": mascarar(f"{type(e).__name__}: {e}"), "finalizadoEm": _agora()}})
        raise
    finally:
        liberar_lock(db, owner)
