// Job diário com dataRef 2026-10-22: janela [2026-04-25T03:00Z, 2026-10-22T03:00Z) → média por rota × dia da semana × hora, $merge replace.
db.trecho_observacoes.aggregate([
  // Pega só as observações dos últimos 180 dias, sem o dia de hoje.
  {
    $match: {
      observadoEm: { $gte: ISODate("2026-04-25T03:00:00.000Z"), $lt: ISODate("2026-10-22T03:00:00.000Z") }
    }
  },
  // Descobre o dia da semana (1 = segunda … 7 = domingo) e a hora, no horário de São
  // Paulo.
  {
    $set: {
      dow: { $isoDayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },
      hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }
    }
  },
  // Agrupa por rota, tipo de veículo, dia da semana e hora, guardando contagem e somas.
  {
    $group: {
      _id: {
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dow: "$dow",
        hora: "$hora"
      },
      n: { $sum: 1 },
      somaMin: { $sum: "$tempoMin" },
      somaQuadMin: { $sum: { $multiply: [ "$tempoMin", "$tempoMin" ] } },
      somaKm: { $sum: "$distanciaKm" }
    }
  },
  // Arredonda as somas, calcula as médias e carimba o resultado com a data e o número da
  // execução.
  {
    $project: {
      _id: 0,
      origem: "$_id.origem",
      destino: "$_id.destino",
      tipoVeiculo: "$_id.tipoVeiculo",
      dow: "$_id.dow",
      hora: "$_id.hora",
      n: 1,
      somaMin: { $round: [ "$somaMin", 6 ] },
      somaQuadMin: { $round: [ "$somaQuadMin", 6 ] },
      somaKm: { $round: [ "$somaKm", 6 ] },
      mediaMin: { $divide: [ "$somaMin", "$n" ] },
      mediaKm: { $divide: [ "$somaKm", "$n" ] },
      janelaInicio: { $literal: ISODate("2026-04-25T03:00:00.000Z") },
      janelaFim: { $literal: ISODate("2026-10-22T03:00:00.000Z") },
      dataRef: { $literal: "2026-10-22" },
      runId: { $literal: "<runId>" },
      atualizadoEm: "$$NOW"
    }
  },
  // Grava o resultado numa collection persistente (a "materialized view"): se já existe um
  // documento com a mesma chave, ele é substituído; se não, é inserido.
  {
    $merge: {
      into: "trecho_media_dow_hora",
      on: [ "origem", "destino", "tipoVeiculo", "dow", "hora" ],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
