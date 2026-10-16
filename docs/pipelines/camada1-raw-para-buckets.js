// Camada 1 com asOf 2026-10-16: reprocessa D-3…D-1 (dias locais), $merge replace.
db.trecho_observacoes.aggregate([
  // Só os dias a reprocessar (D-1…D-k ∪ dias com atraso detectado). Limites semiabertos,
  // já calculados no fuso local: usa o índice { observadoEm: 1 }.
  {
    $match: {
      observadoEm: { $gte: ISODate("2026-10-13T03:00:00.000Z"), $lt: ISODate("2026-10-16T03:00:00.000Z") }
    }
  },
  // Grão do bucket: trecho × tipo de veículo × dia local × hora local. $dateTrunc/$hour
  // com timezone — nunca o dia/hora UTC. Guarda soma e contagem (componíveis), não média.
  {
    $group: {
      _id: {
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dataLocal: { $dateTrunc: { date: "$observadoEm", unit: "day", timezone: "America/Sao_Paulo" } },
        hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }
      },
      somaMin: { $sum: "$tempoMin" },
      somaKm: { $sum: "$distanciaKm" },
      n: { $sum: 1 },
      minMin: { $min: "$tempoMin" },
      maxMin: { $max: "$tempoMin" }
    }
  },
  // Achata a chave e deriva dowCivil (1=domingo … 7=sábado) do dia local. $$NOW só para
  // auditoria; janela e dias vêm por parâmetro.
  {
    $project: {
      _id: 0,
      origem: "$_id.origem",
      destino: "$_id.destino",
      tipoVeiculo: "$_id.tipoVeiculo",
      dataLocal: "$_id.dataLocal",
      hora: "$_id.hora",
      dowCivil: { $dayOfWeek: { date: "$_id.dataLocal", timezone: "America/Sao_Paulo" } },
      somaMin: 1,
      somaKm: 1,
      n: 1,
      minMin: 1,
      maxMin: 1,
      atualizadoEm: "$$NOW",
      runId: { $literal: "<runId>" }
    }
  },
  // Upsert pela chave única do bucket. whenMatched: replace recalcula o dia inteiro a
  // partir da raw — reexecutar dá o mesmo resultado (idempotente). $inc duplicaria a cada
  // reexecução.
  {
    $merge: {
      into: "trecho_bucket_diario",
      on: [ "origem", "destino", "tipoVeiculo", "dataLocal", "hora" ],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
