// GERADO por scripts/export_pipelines.py a partir de frota/pipelines/job.py.
// Não edite à mão: mude o builder Python e rode `make pipelines`.
//
// Job diário (trigger jobDiario, 03:10 em São Paulo): lê a raw da janela padrão
// [00:00 local de (hoje − 180), 00:00 local de hoje) e materializa trecho_media_dow_hora.
// Mesma sequência de frota/job.py::rodar_job: count → aggregate ($merge replace) →
// remove o que não foi regravado neste run → registra em job_runs (origem "trigger").

const JANELA_DIAS = 180;
// São Paulo não tem horário de verão desde 2019: o fuso é UTC−3 fixo o ano todo.
// O Python usa America/Sao_Paulo (zoneinfo); se o horário de verão voltar, revisar aqui.
const OFFSET_SP_HORAS = -3;

// O que cada estágio do pipeline faz (o JSON abaixo é exatamente o que vai ao MongoDB;
// os textos "__INICIO__" etc. são trocados pelos valores da execução):
//  1. $match   Pega só as observações dos últimos 180 dias, sem o dia de hoje.
//  2. $set     Descobre o dia da semana (1 = segunda … 7 = domingo) e a hora, no horário de
//              São Paulo.
//  3. $group   Agrupa por rota, tipo de veículo, dia da semana e hora, guardando contagem e
//              somas.
//  4. $project Arredonda as somas, calcula as médias e carimba o resultado com a data e o
//              número da execução.
//  5. $merge   Grava o resultado numa collection persistente (a "materialized view"): se já
//              existe um documento com a mesma chave, ele é substituído; se não, é inserido.

const TEMPLATE = [
  {
    "$match": {
      "observadoEm": {
        "$gte": "__INICIO__",
        "$lt": "__FIM__"
      }
    }
  },
  {
    "$set": {
      "dow": {
        "$isoDayOfWeek": {
          "date": "$observadoEm",
          "timezone": "America/Sao_Paulo"
        }
      },
      "hora": {
        "$hour": {
          "date": "$observadoEm",
          "timezone": "America/Sao_Paulo"
        }
      }
    }
  },
  {
    "$group": {
      "_id": {
        "origem": "$origem",
        "destino": "$destino",
        "tipoVeiculo": "$tipoVeiculo",
        "dow": "$dow",
        "hora": "$hora"
      },
      "n": {
        "$sum": 1
      },
      "somaMin": {
        "$sum": "$tempoMin"
      },
      "somaQuadMin": {
        "$sum": {
          "$multiply": [
            "$tempoMin",
            "$tempoMin"
          ]
        }
      },
      "somaKm": {
        "$sum": "$distanciaKm"
      }
    }
  },
  {
    "$project": {
      "_id": 0,
      "origem": "$_id.origem",
      "destino": "$_id.destino",
      "tipoVeiculo": "$_id.tipoVeiculo",
      "dow": "$_id.dow",
      "hora": "$_id.hora",
      "n": 1,
      "somaMin": {
        "$round": [
          "$somaMin",
          6
        ]
      },
      "somaQuadMin": {
        "$round": [
          "$somaQuadMin",
          6
        ]
      },
      "somaKm": {
        "$round": [
          "$somaKm",
          6
        ]
      },
      "mediaMin": {
        "$divide": [
          "$somaMin",
          "$n"
        ]
      },
      "mediaKm": {
        "$divide": [
          "$somaKm",
          "$n"
        ]
      },
      "janelaInicio": {
        "$literal": "__INICIO__"
      },
      "janelaFim": {
        "$literal": "__FIM__"
      },
      "dataRef": {
        "$literal": "__DATA_REF__"
      },
      "runId": {
        "$literal": "__RUN_ID__"
      },
      "atualizadoEm": "$$NOW"
    }
  },
  {
    "$merge": {
      "into": "trecho_media_dow_hora",
      "on": [
        "origem",
        "destino",
        "tipoVeiculo",
        "dow",
        "hora"
      ],
      "whenMatched": "replace",
      "whenNotMatched": "insert"
    }
  }
];

const BANCO = "frota_eta";
// Mesmo padrão de frota/db.py: host:porta não sai em mensagem de erro.
const HOST = new RegExp("[A-Za-z0-9][A-Za-z0-9.-]*\\.(?:mongodb\\.net|mongo\\.cosmos\\.azure\\.com|internal)(?::\\d+)?|\\b(?:\\d{1,3}\\.){3}\\d{1,3}(?::\\d+)?", "g");

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
  const r = await db.collection("trecho_observacoes")
    .aggregate([{ $limit: 1 }, { $project: { _id: 0, t: "$$NOW" } }]).toArray();
  return r.length ? r[0].t : new Date();
}

exports = async function () {
  const db = context.services.get("mongodb-atlas").db(BANCO);
  const raw = db.collection("trecho_observacoes");
  const media = db.collection("trecho_media_dow_hora");
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
