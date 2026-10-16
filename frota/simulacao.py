"""Simulação do tempo para a demo: relógio simulado, atraso injetado e avanço de dias."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pymongo.database import Database

from . import config as config_mod
from .janela import inicio_dia, parse_asof

UTC = timezone.utc


def agora_simulado(db: Database) -> datetime:
    """Relógio de ingestão da demo: 1 s depois do último `ingeridoEm` da raw.

    O asOf da demo não acompanha o calendário real (pode estar à frente ou atrás), então
    uma ingestão nova é carimbada logo depois de tudo que já foi ingerido.
    """
    topo = db.trecho_observacoes.find_one({}, {"ingeridoEm": 1}, sort=[("ingeridoEm", -1)])
    # só o relógio simulado: usar o real quando ele está à frente faria o watermark
    # pular por cima das observações pendentes que ainda vão "chegar"
    return topo["ingeridoEm"] + timedelta(seconds=1) if topo else datetime.now(UTC)


def injetar_atrasado(db: Database, asof: str, origem: str, destino: str, tipo: str,
                     dias_atras: int = 2, hora: int = 8) -> dict:
    """Observação de D-`dias_atras` às `hora`:00 local, ingerida agora."""
    cfg = config_mod.ler(db)
    dia = parse_asof(asof) - timedelta(days=dias_atras)
    quando = inicio_dia(dia, cfg["timezone"]) + timedelta(hours=hora)
    trecho = db.trechos.find_one({"origem": origem, "destino": destino})
    tipo_doc = db.tipos_veiculo.find_one({"_id": tipo})
    if not trecho or not tipo_doc:
        raise ValueError(f"trecho {origem}→{destino} ou tipo {tipo} não existe no catálogo")
    tempo = round(trecho["tempoBaseMin"] * tipo_doc["fatorTempo"], 1)
    km = round(trecho["distanciaBaseKm"], 1)
    veiculo = db.veiculos.find_one({"tipoVeiculo": tipo}) or {"_id": "VEI-ATRASO"}
    doc = {"origem": origem, "destino": destino, "tipoVeiculo": tipo,
           "veiculoId": veiculo["_id"], "viagemId": f"VIA-ATRASO-{dia:%Y%m%d}-{hora:02d}-{uuid.uuid4().hex[:6]}",
           "seq": 1, "observadoEm": quando, "ingeridoEm": agora_simulado(db),
           "distanciaKm": km, "tempoMin": tempo}
    db.trecho_observacoes.insert_one(doc)
    doc.pop("_id")
    return doc


def asof_atual(db: Database) -> str | None:
    """asOf do último run bem-sucedido: o "hoje" simulado da demo."""
    # maior asOf já materializado (string ISO ordena como data): um rerun retroativo da
    # camada 2 não pode fazer o relógio da demo andar para trás
    r = db.job_runs.find_one({"status": "ok", "camada": {"$in": ["1", "todas"]}},
                             sort=[("asOf", -1)])
    return r["asOf"] if r else None


def avancar(db: Database, dias: int = 1, seed: int | None = None) -> list[dict]:
    """Simula a passagem do tempo: gera o novo "hoje" e roda o job com asOf + 1."""
    from . import settings
    from .gerador import Malha, gerar_dia, inserir, liberar_pendentes
    from .janela import hoje_local, janela
    from .job import materializar

    cfg = config_mod.ler(db)
    atual = parse_asof(asof_atual(db) or hoje_local(cfg["timezone"]))
    malha = Malha.do_banco(db) if db.veiculos.estimated_document_count() else None
    saida = []
    for _ in range(dias):
        novo = atual + timedelta(days=1)
        gerados = 0
        relogio = inicio_dia(novo + timedelta(days=1), cfg["timezone"])
        # dataset de fixtures não tem frota para gerar dias novos: só anda o relógio
        if malha and malha.postos_base:
            docs = gerar_dia(malha, novo, seed or settings.SEED, cfg["timezone"],
                             cfg["kReprocessamento"])
            if docs:
                inserir(db, docs, relogio)
            gerados = len(docs)
        liberados = liberar_pendentes(db, relogio)
        ji_antes, _ = janela(atual, cfg)
        ji, jf = janela(novo, cfg)
        run = materializar(db, novo)
        saida.append({"asOf": novo.isoformat(), "observacoesGeradas": gerados,
                      "atrasadosLiberados": liberados,
                      "diaQueEntra": (novo - timedelta(days=1)).isoformat(),
                      "diaQueSai": (atual - timedelta(days=cfg["janelaDias"])).isoformat(),
                      "janelaInicio": ji, "janelaFim": jf, "run": run})
        atual = novo
    return saida
