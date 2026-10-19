"""Exporta os pipelines para docs/pipelines/ e gera as Functions dos triggers do Atlas.

Uma fonte só: os builders de `frota/pipelines/`. Para as Functions, o builder é chamado
com marcadores (`"__INICIO__"`, `"__FIM__"`, `"__DATA_REF__"`, `"__RUN_ID__"`, `"__IDS__"`,
`"__AGORA__"`) no lugar dos valores; o JS só troca cada marcador pelo valor da execução.
Assim o trigger roda exatamente o pipeline que o Python roda (tests/test_trigger_export.py).

Gera:
  docs/pipelines/*.json — {descricao, colecao, dataRef, estagios: [{comentario, estagio}], pipeline}
  docs/pipelines/*.js   — o mesmo pipeline pronto para colar no mongosh
  atlas-trigger/functions/rodarJob.js e ingerirSimulado.js
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import _path  # noqa: F401

from bson import json_util

from frota.cenario import Filtro
from frota.db import _HOST
from frota.janela import inicio_dia, janela_padrao, proximo_job
from frota.mongosh import _quebrar, pipeline_mongosh
from frota.pipelines import cenario as pl_cenario
from frota.pipelines import comentados, estagios
from frota.pipelines import ingestao as pl_ingestao
from frota.pipelines import job as pl_job
from frota.settings import JANELA_DIAS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pipelines"
TRIGGER = ROOT / "atlas-trigger"
# banco da demo: é nele que o trigger escreve (constante gerada, não vem do .env local)
BANCO = "frota_eta"
DATA_REF = date(2026, 10, 22)


class _Marcador(str):
    """String que também responde `isoformat()`, para entrar onde o builder espera uma data."""

    def isoformat(self) -> str:
        return str(self)


def template_job() -> list[dict]:
    return substituir(estagios(pl_job.pipeline(_Marcador("__INICIO__"), _Marcador("__FIM__"),
                                               _Marcador("__DATA_REF__"), "__RUN_ID__")), {})


def template_ingestao() -> list[dict]:
    return substituir(estagios(pl_ingestao.pipeline(_Marcador("__AGORA__"), "__IDS__")), {})


def template_filtro_pendentes() -> dict:
    return substituir(pl_ingestao.filtro_pendentes(_Marcador("__AGORA__")), {})


def substituir(template, valores: dict):
    """Troca toda string igual a um marcador pelo valor; devolve cópia (template intacto)."""
    if isinstance(template, str):
        return valores.get(str(template), str(template))
    if isinstance(template, list):
        return [substituir(v, valores) for v in template]
    if isinstance(template, dict):
        return {k: substituir(v, valores) for k, v in template.items()}
    return template


# ---- Functions do App Services ---------------------------------------------------------

_CABECALHO = """\
// GERADO por scripts/export_pipelines.py a partir de @@ORIGEM@@.
// Não edite à mão: mude o builder Python e rode `make pipelines`.
"""

_COMUM = """\
const BANCO = "@@BANCO@@";
// Mesmo padrão de frota/db.py: host:porta não sai em mensagem de erro.
const HOST = new RegExp(@@HOST@@, "g");

// Troca toda string igual a um marcador pelo valor da execução (como substituir() no Python).
function substituir(v, valores) {
  if (typeof v === "string") {
    return Object.prototype.hasOwnProperty.call(valores, v) ? valores[v] : v;
  }
  if (Array.isArray(v)) return v.map((x) => substituir(x, valores));
  if (v !== null && typeof v === "object") {
    const r = {};
    for (const k of Object.keys(v)) r[k] = substituir(v[k], valores);
    return r;
  }
  return v;
}

function mascarar(e) {
  const texto = e && e.message ? `${e.name || "Error"}: ${e.message}` : String(e);
  return texto.replace(HOST, "<host>");
}
"""

_JOB = """\
//
// Job diário (trigger jobDiario, 03:10 em São Paulo): lê a raw da janela padrão
// [00:00 local de (hoje − @@JANELA@@), 00:00 local de hoje) e materializa @@MEDIA@@.
// Mesma sequência de frota/job.py::rodar_job: count → aggregate ($merge replace) →
// remove o que não foi regravado neste run → registra em job_runs (origem "trigger").

const JANELA_DIAS = @@JANELA@@;
// São Paulo não tem horário de verão desde 2019: o fuso é UTC−3 fixo o ano todo.
// O Python usa America/Sao_Paulo (zoneinfo); se o horário de verão voltar, revisar aqui.
const OFFSET_SP_HORAS = -3;

// O que cada estágio do pipeline faz (o JSON abaixo é exatamente o que vai ao MongoDB;
// os textos "__INICIO__" etc. são trocados pelos valores da execução):
@@PASSOS@@
const TEMPLATE = @@TEMPLATE@@;

@@COMUM@@
// Data local (ano, mês 0–11, dia) de São Paulo no instante `agora`.
function diaLocal(agora) {
  const l = new Date(agora.getTime() + OFFSET_SP_HORAS * 3600 * 1000);
  return [l.getUTCFullYear(), l.getUTCMonth(), l.getUTCDate()];
}

// 00:00 local do dia, como instante UTC (Date.UTC normaliza dia negativo ou > 31).
function inicioDia(ano, mes, dia) {
  return new Date(Date.UTC(ano, mes, dia, -OFFSET_SP_HORAS));
}

function isoDia(ano, mes, dia) {
  return new Date(Date.UTC(ano, mes, dia)).toISOString().slice(0, 10);
}

// Mesmo formato de frota/job.py::novo_run_id: "YYYY-MM-DDTHH:MM:SSZ-xxxx".
function novoRunId(t) {
  const sufixo = Math.floor(Math.random() * 0x10000).toString(16).padStart(4, "0");
  return `${t.toISOString().slice(0, 19)}Z-${sufixo}`;
}

// Relógio do cluster (o mesmo do $$NOW gravado em atualizadoEm), como o Python faz com
// hello.localTime: o corte "não foi regravado neste run" não depende do relógio da Function.
async function relogioServidor(db) {
  const r = await db.collection("@@RAW@@")
    .aggregate([{ $limit: 1 }, { $project: { _id: 0, t: "$$NOW" } }]).toArray();
  return r.length ? r[0].t : new Date();
}

exports = async function () {
  const db = context.services.get("mongodb-atlas").db(BANCO);
  const raw = db.collection("@@RAW@@");
  const media = db.collection("@@MEDIA@@");
  const [ano, mes, dia] = diaLocal(new Date());
  const inicio = inicioDia(ano, mes, dia - JANELA_DIAS);
  const fim = inicioDia(ano, mes, dia);
  const dataRef = isoDia(ano, mes, dia);
  const inicioRun = await relogioServidor(db);
  const runId = novoRunId(inicioRun);
  const pipeline = substituir(TEMPLATE, {
    __INICIO__: inicio, __FIM__: fim, __DATA_REF__: dataRef, __RUN_ID__: runId,
  });
  const base = { _id: runId, runId, origem: "trigger", dataRef, iniciadoEm: inicioRun };
  const t0 = Date.now();
  try {
    const lidos = await raw.count(pipeline[0].$match);
    await raw.aggregate(pipeline).toArray();
    const gravados = await media.count({ runId });
    const removidos = (await media.deleteMany({ atualizadoEm: { $lt: inicioRun } })).deletedCount;
    const ms = Date.now() - t0;
    await db.collection("job_runs").insertOne({
      ...base, status: "ok", janelaInicio: inicio, janelaFim: fim,
      lidos, gravados, removidos, ms,
    });
    return { runId, dataRef, lidos, gravados, removidos, ms };
  } catch (e) {
    const erro = mascarar(e);
    try {
      await db.collection("job_runs").insertOne({ ...base, status: "erro", erro, ms: Date.now() - t0 });
    } catch (_) {
      // o registro do erro não pode esconder o erro original
    }
    throw new Error(erro);
  }
};
"""

_INGESTAO = """\
//
// Ingestão simulada (trigger ingestaoSimulada, de hora em hora): move da fila
// @@ORIGEM_COL@@ para @@DESTINO_COL@@ o que já "aconteceu". Mesmo algoritmo de
// frota/ingestao.py::ingerir: escolhe os _ids, faz o $merge só deles e apaga só eles da
// fila (o que chegar no meio do caminho não se perde).

const FILTRO_PENDENTES = @@FILTRO@@;

// O que cada estágio do pipeline faz:
@@PASSOS@@
const TEMPLATE = @@TEMPLATE@@;

@@COMUM@@
exports = async function () {
  const db = context.services.get("mongodb-atlas").db(BANCO);
  const fila = db.collection("@@ORIGEM_COL@@");
  const agora = new Date();
  try {
    const escolhidos = await fila
      .find(substituir(FILTRO_PENDENTES, { __AGORA__: agora }), { _id: 1 }).toArray();
    const ids = escolhidos.map((d) => d._id);
    if (ids.length) {
      await fila.aggregate(substituir(TEMPLATE, { __IDS__: ids })).toArray();
      await fila.deleteMany({ _id: { $in: ids } });
    }
    return { movidos: ids.length, restantes: await fila.count({}) };
  } catch (e) {
    throw new Error(mascarar(e));
  }
};
"""


def _passos(p) -> str:
    """Um comentário JS por estágio: `//  1. $match  frase`, com quebra alinhada."""
    linhas = []
    for i, e in enumerate(p, start=1):
        op = next(iter(e.estagio))
        cab = f"//  {i}. {op:<8} "
        quebradas = _quebrar(e.comentario, 78)
        linhas.append(cab + quebradas[0])
        linhas += [f"//{' ' * (len(cab) - 2)}{q}" for q in quebradas[1:]]
    return "\n".join(linhas) + "\n"


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _preencher(texto: str, valores: dict) -> str:
    for k, v in valores.items():
        texto = texto.replace(f"@@{k}@@", v)
    return texto


def gerar_functions() -> dict[str, str]:
    """{caminho relativo a atlas-trigger/: conteúdo} das duas Functions."""
    comum = _preencher(_COMUM, {"BANCO": BANCO, "HOST": json.dumps(_HOST.pattern)})
    job = _preencher(_CABECALHO + _JOB, {
        "ORIGEM": "frota/pipelines/job.py", "COMUM": comum, "JANELA": str(JANELA_DIAS),
        "RAW": pl_cenario.RAW, "MEDIA": pl_job.COLECAO, "TEMPLATE": _js(template_job()),
        "PASSOS": _passos(pl_job.pipeline(_Marcador("__INICIO__"), _Marcador("__FIM__"),
                                          _Marcador("__DATA_REF__"), "__RUN_ID__"))})
    ingestao = _preencher(_CABECALHO + _INGESTAO, {
        "ORIGEM": "frota/pipelines/ingestao.py", "COMUM": comum,
        "ORIGEM_COL": pl_ingestao.ORIGEM, "DESTINO_COL": pl_ingestao.DESTINO,
        "FILTRO": _js(template_filtro_pendentes()), "TEMPLATE": _js(template_ingestao()),
        "PASSOS": _passos(pl_ingestao.pipeline(_Marcador("__AGORA__"), ["__IDS__"]))})
    return {"functions/rodarJob.js": job, "functions/ingerirSimulado.js": ingestao}


# ---- docs/pipelines ---------------------------------------------------------------------

def _salvar(nome: str, descricao: str, colecao: str, p) -> None:
    c = comentados(p)
    doc = {"descricao": descricao, "colecao": colecao, "dataRef": DATA_REF.isoformat(),
           "estagios": c, "pipeline": estagios(p)}
    (OUT / f"{nome}.json").write_text(json_util.dumps(
        doc, ensure_ascii=False, indent=2, json_options=json_util.RELAXED_JSON_OPTIONS) + "\n")
    (OUT / f"{nome}.js").write_text(f"// {descricao}\n" + pipeline_mongosh(colecao, c) + "\n")


def exportar_docs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for antigo in OUT.iterdir():
        if antigo.suffix in (".js", ".json"):
            antigo.unlink()
    ini, fim = janela_padrao(DATA_REF)
    agora = datetime(2026, 10, 22, 14, 5, tzinfo=timezone.utc)
    _salvar("job-raw-para-media",
            f"Job diário com dataRef {DATA_REF}: janela [{ini:%Y-%m-%dT%H:%MZ}, {fim:%Y-%m-%dT%H:%MZ}) "
            "→ média por rota × dia da semana × hora, $merge replace.",
            pl_cenario.RAW, pl_job.pipeline(ini, fim, DATA_REF, "<runId>"))
    _salvar("ingestao-fila-para-raw",
            f"Ingestão simulada às {agora:%Y-%m-%dT%H:%MZ}: o que já passou sai da fila e entra "
            "na raw ($merge por viagemId + seq).",
            pl_ingestao.ORIGEM, pl_ingestao.pipeline(agora))
    f = Filtro("BASE-001", "POSTO-11", "CARRETA", [1, 2, 3, 4, 5], 6, 12)
    _salvar("cenario-base-pronta",
            "Cenário na janela padrão: soma os documentos prontos do job (seg–sex, 6h–12h).",
            pl_cenario.BASE, pl_cenario.base(f, f.dias_ordenados(), f.horas()))
    _salvar("cenario-raw-sob-demanda",
            "Cenário fora da janela padrão (últimos 30 dias): o mesmo cálculo direto na raw, "
            "sem salvar.",
            pl_cenario.RAW, pl_cenario.raw(f, inicio_dia(DATA_REF - timedelta(days=30)), fim,
                                           f.horas(), None))
    _salvar("cenario-raw-salvo",
            "Cenário sob demanda salvo: o $merge em consultas_salvas é o último estágio "
            "(TTL apaga quando passa do expiraEm).",
            pl_cenario.RAW, pl_cenario.raw(f, ini, fim, f.horas(), {
                "_id": "<chave do filtro>", "periodo": "relativo", "expiraEm": proximo_job(agora)}))
    fv = Filtro("BASE-001", "POSTO-11", "CARRETA", [1, 2, 3, 4, 5], 6, 12, veiculoId="VEI-CARRETA-7")
    _salvar("cenario-raw-veiculo",
            "Cenário de um veículo específico na janela padrão: a base é por tipo, então vai à "
            "raw (o $match inclui veiculoId) e salva até o próximo job.",
            pl_cenario.RAW, pl_cenario.raw(fv, ini, fim, fv.horas(), {
                "_id": "<chave do filtro>", "periodo": "relativo", "expiraEm": proximo_job(agora)}))


def exportar_functions() -> None:
    for caminho, conteudo in gerar_functions().items():
        (TRIGGER / caminho).write_text(conteudo)


if __name__ == "__main__":
    exportar_docs()
    exportar_functions()
    print("\n".join(sorted(f"docs/pipelines/{p.name}" for p in OUT.iterdir())))
    print("\n".join(f"atlas-trigger/{c}" for c in gerar_functions()))
