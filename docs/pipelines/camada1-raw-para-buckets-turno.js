// Incremental, camada 1 por turno com asOf 2026-10-16: D-3…D-1, $merge replace.
db.trecho_observacoes.aggregate([
  // Só os dias a reprocessar (dia local civil). Limites semiabertos já no fuso local; usa
  // o índice { observadoEm: 1 }.
  {
    $match: {
      observadoEm: { $gte: ISODate("2026-10-13T03:00:00.000Z"), $lt: ISODate("2026-10-16T03:00:00.000Z") }
    }
  },
  // Hora e dia da semana locais por observação.
  {
    $set: {
      hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },
      dowCivil: { $dayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }
    }
  },
  // Turno (config v1) e dow pela regraNoite = dia_civil: gravados no bucket.
  {
    $set: {
      turno: {
        $switch: {
          branches: [
            { case: { $and: [ { $gte: [ "$hora", 6 ] }, { $lt: [ "$hora", 12 ] } ] }, then: "M" },
            { case: { $and: [ { $gte: [ "$hora", 12 ] }, { $lt: [ "$hora", 18 ] } ] }, then: "T" }
          ],
          default: "N"
        }
      },
      dow: "$dowCivil"
    }
  },
  // Grão: trecho × tipo × dia local civil × turno × dow. O dow fica na chave porque com
  // dia_operacional a madrugada do dia civil pertence ao dow anterior; assim cada dia
  // civil continua sendo reprocessado sozinho.
  {
    $group: {
      _id: {
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dataLocal: { $dateTrunc: { date: "$observadoEm", unit: "day", timezone: "America/Sao_Paulo" } },
        turno: "$turno",
        dow: "$dow"
      },
      somaMin: { $sum: "$tempoMin" },
      somaKm: { $sum: "$distanciaKm" },
      n: { $sum: 1 },
      minMin: { $min: "$tempoMin" },
      maxMin: { $max: "$tempoMin" }
    }
  },
  // Achata a chave; somas a 6 casas (determinístico); versão da config gravada.
  {
    $project: {
      _id: 0,
      origem: "$_id.origem",
      destino: "$_id.destino",
      tipoVeiculo: "$_id.tipoVeiculo",
      dataLocal: "$_id.dataLocal",
      turno: "$_id.turno",
      dow: "$_id.dow",
      somaMin: { $round: [ "$somaMin", 6 ] },
      somaKm: { $round: [ "$somaKm", 6 ] },
      n: 1,
      minMin: 1,
      maxMin: 1,
      configVersao: { $literal: 1 },
      atualizadoEm: "$$NOW",
      runId: { $literal: "<runId>" }
    }
  },
  // Upsert pela chave única do bucket de turno; replace = idempotente.
  {
    $merge: {
      into: "trecho_bucket_turno",
      on: [ "origem", "destino", "tipoVeiculo", "dataLocal", "turno", "dow" ],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
