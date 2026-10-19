// GERADO por scripts/export_pipelines.py a partir de frota/pipelines/ingestao.py.
// Não edite à mão: mude o builder Python e rode `make pipelines`.
//
// Ingestão simulada (trigger ingestaoSimulada, de hora em hora): move da fila
// ingestao_simulada para trecho_observacoes o que já "aconteceu". Mesmo algoritmo de
// frota/ingestao.py::ingerir: escolhe os _ids, faz o $merge só deles e apaga só eles da
// fila (o que chegar no meio do caminho não se perde).

const FILTRO_PENDENTES = {
  "observadoEm": {
    "$lt": "__AGORA__"
  }
};

const TEMPLATE = [
  {
    "$match": {
      "_id": {
        "$in": "__IDS__"
      }
    }
  },
  {
    "$project": {
      "_id": 0
    }
  },
  {
    "$merge": {
      "into": "trecho_observacoes",
      "on": [
        "viagemId",
        "seq"
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

exports = async function () {
  const db = context.services.get("mongodb-atlas").db(BANCO);
  const fila = db.collection("ingestao_simulada");
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
