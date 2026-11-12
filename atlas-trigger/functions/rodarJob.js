// GERADO por scripts/export_pipelines.py a partir de backend/frota/pipelines/job.py.
// Não edite à mão: mude o builder Python e rode `make pipelines`.
//
// Job diário (trigger jobDiario, 03:10 em São Paulo): lê a raw da janela padrão
// [00:00 local de (hoje − 180), 00:00 local de hoje) e materializa trecho_media_dow_hora.
// Mesma sequência de backend/frota/job.py::rodar_job: count → aggregate ($merge replace) →
// remove o que não foi regravado neste run → registra em job_runs (origem "trigger").

// A data local não é calculada aqui com offset fixo: o MongoDB devolve o 00:00 de hoje e o de
// 180 dias antes em America/Sao_Paulo ($dateTrunc/$dateSubtract com timezone), seguindo a
// base de fusos do servidor, horário de verão incluído. Mesmo resultado de
// backend/frota/janela.py::janela_padrao (conferido em tests/test_live_trigger.py).
const JANELA_NO_SERVIDOR = [
  {
    "$match": {
      "$expr": false
    }
  },
  {
    "$unionWith": {
      "pipeline": [
        {
          "$documents": [
            {}
          ]
        }
      ]
    }
  },
  {
    "$project": {
      "_id": 0,
      "t": "$$NOW",
      "inicio": {
        "$dateTrunc": {
          "date": {
            "$dateSubtract": {
              "startDate": {
                "$dateTrunc": {
                  "date": "__AGORA__",
                  "unit": "day",
                  "timezone": "America/Sao_Paulo"
                }
              },
              "unit": "day",
              "amount": 180,
              "timezone": "America/Sao_Paulo"
            }
          },
          "unit": "day",
          "timezone": "America/Sao_Paulo"
        }
      },
      "fim": {
        "$dateTrunc": {
          "date": "__AGORA__",
          "unit": "day",
          "timezone": "America/Sao_Paulo"
        }
      },
      "dataRef": {
        "$dateToString": {
          "date": "__AGORA__",
          "format": "%Y-%m-%d",
          "timezone": "America/Sao_Paulo"
        }
      }
    }
  }
];

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
// Mesmo padrão de backend/frota/db.py: host:porta não sai em mensagem de erro.
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

// Mesmo formato de backend/frota/job.py::novo_run_id: "YYYY-MM-DDTHH:MM:SSZ-xxxx".
function novoRunId(t) {
  const sufixo = Math.floor(Math.random() * 0x10000).toString(16).padStart(4, "0");
  return `${t.toISOString().slice(0, 19)}Z-${sufixo}`;
}

// Janela, dataRef e relógio do cluster numa ida só ao servidor. `t` é o $$NOW do cluster (o
// mesmo gravado em atualizadoEm), como o Python faz com hello.localTime: o corte "não foi
// regravado neste run" não depende do relógio da Function.
async function janelaNoServidor(raw, agora) {
  const r = await raw.aggregate(substituir(JANELA_NO_SERVIDOR, { __AGORA__: agora })).toArray();
  if (r.length !== 1) throw new Error("o servidor não devolveu a janela do job");
  return r[0];
}

exports = async function () {
  const db = context.services.get("mongodb-atlas").db(BANCO);
  const raw = db.collection("trecho_observacoes");
  const media = db.collection("trecho_media_dow_hora");
  const { inicio, fim, dataRef, t: inicioRun } = await janelaNoServidor(raw, new Date());
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
