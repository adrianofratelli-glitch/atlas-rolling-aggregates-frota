"""Exporta os pipelines (com comentários por estágio) para docs/pipelines/.

Gera, para a config default e asOf 2026-10-16:
  *.json — {descricao, colecao, estagios: [{comentario, estagio}], pipeline} (EJSON relaxed)
  *.js   — o mesmo pipeline pronto para colar no mongosh
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import _path  # noqa: F401

from bson import json_util

from frota import settings
from frota.janela import inicio_dia, janela, parse_asof
from frota.mongosh import para_mongosh, pipeline_mongosh
from frota.pipelines import comentados, estagios
from frota.pipelines import camada1, camada2, raw_onthefly, simples

ASOF = "2026-10-16"
OUT = Path(__file__).resolve().parent.parent / "docs" / "pipelines"


def salvar(nome, descricao, colecao, p):
    c = comentados(p)
    doc = {"descricao": descricao, "colecao": colecao, "asOf": ASOF,
           "estagios": c, "pipeline": estagios(p)}
    (OUT / f"{nome}.json").write_text(json_util.dumps(doc, ensure_ascii=False, indent=2,
                                                      json_options=json_util.RELAXED_JSON_OPTIONS))
    (OUT / f"{nome}.js").write_text(f"// {descricao}\n" + pipeline_mongosh(colecao, c) + "\n")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    base = settings.config_inicial()
    d = parse_asof(ASOF)
    tz = base["timezone"]
    ji, jf = janela(d, base)
    k = base["kReprocessamento"]
    base = {**base, "versao": 1}
    salvar("simples-raw-para-media",
           f"Modo simples (default) com asOf {ASOF}: janela inteira [{ji:%Y-%m-%dT%H:%MZ}, "
           f"{jf:%Y-%m-%dT%H:%MZ}) → média por dow × turno, $out.", "trecho_observacoes",
           simples.pipeline(ji, jf, ASOF, base, "<runId>"))
    salvar("simples-raw-para-media-so-turno",
           "Modo simples só por turno (incluirDow = false): ≤ 3 docs por trecho/veículo.",
           "trecho_observacoes",
           simples.pipeline(ji, jf, ASOF, {**base, "incluirDow": False}, "<runId>"))
    salvar("camada1-raw-para-buckets-turno",
           f"Incremental, camada 1 por turno com asOf {ASOF}: D-{k}…D-1, $merge replace.",
           "trecho_observacoes",
           camada1.pipeline_turno([(inicio_dia(d - timedelta(days=k), tz), inicio_dia(d, tz))],
                                  "<runId>", base))
    salvar("camada1-raw-para-buckets-hora",
           f"Camada 1 com asOf {ASOF}: reprocessa D-{k}…D-1 (dias locais), $merge replace.",
           "trecho_observacoes",
           camada1.pipeline([(inicio_dia(d - timedelta(days=k), tz), inicio_dia(d, tz))],
                            "<runId>", tz))
    for modo in ("merge_runid", "out"):
        cfg = {**base, "modoLimpezaCamada2": modo, "granularidadeBucket": "turno"}
        salvar(f"camada2-buckets-para-media-{modo}",
               f"Camada 2 com asOf {ASOF}, janela [{ji:%Y-%m-%dT%H:%MZ}, {jf:%Y-%m-%dT%H:%MZ}), "
               f"limpeza {modo}.", "trecho_bucket_diario",
               camada2.pipeline(ji, jf, ASOF, cfg, "<runId>"))
    for regra in ("dia_civil", "dia_operacional"):
        cfg = {**base, "regraNoite": regra}
        salvar(f"raw-onthefly-{regra}",
               f"Mesma resposta do fallback calculada na raw (regraNoite {regra}).",
               "trecho_observacoes",
               raw_onthefly.pipeline("BASE-001", "POSTO-0042", "BITREM", ji, jf, cfg))
    filtro = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}
    (OUT / "fallback-find.js").write_text(
        "// Consulta de fallback: uma leitura, ≤ 21 docs pelo índice único chave_media_unica\n"
        f"db.trecho_media_historica.find({para_mongosh(filtro)})\n"
        f"db.trecho_media_historica.find({para_mongosh(filtro)}).explain('executionStats')\n")
    print("\n".join(sorted(p.name for p in OUT.iterdir())))
