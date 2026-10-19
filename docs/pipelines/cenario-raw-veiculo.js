// Cenário de um veículo específico na janela padrão: a base é por tipo, então vai à raw (o $match inclui veiculoId) e salva até o próximo job.
db.trecho_observacoes.aggregate([
  // Pega as observações da rota e do veículo escolhido no período pedido (o fim fica de
  // fora).
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-11",
      tipoVeiculo: "CARRETA",
      veiculoId: "VEI-CARRETA-7",
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
  // Fica só com os dias da semana e as horas escolhidos.
  { $match: { dow: { $in: [ 1, 2, 3, 4, 5 ] }, hora: { $in: [ 6, 7, 8, 9, 10, 11 ] } } },
  // Junta tudo num único resultado com contagem e somas.
  {
    $group: {
      _id: null,
      n: { $sum: 1 },
      somaMin: { $sum: "$tempoMin" },
      somaQuadMin: { $sum: { $multiply: [ "$tempoMin", "$tempoMin" ] } },
      somaKm: { $sum: "$distanciaKm" }
    }
  },
  // Arredonda as somas, identifica a consulta pela chave do filtro e marca até quando ela
  // vale.
  {
    $project: {
      _id: { $literal: "<chave do filtro>" },
      n: 1,
      somaMin: { $round: [ "$somaMin", 6 ] },
      somaQuadMin: { $round: [ "$somaQuadMin", 6 ] },
      somaKm: { $round: [ "$somaKm", 6 ] },
      filtro: {
        $literal: {
          origem: "BASE-001",
          destino: "POSTO-11",
          tipoVeiculo: "CARRETA",
          dias: [ 1, 2, 3, 4, 5 ],
          horas: [ 6, 7, 8, 9, 10, 11 ],
          periodo: { tipo: "padrao" },
          veiculoId: "VEI-CARRETA-7"
        }
      },
      periodo: { $literal: "relativo" },
      criadoEm: "$$NOW",
      expiraEm: { $literal: ISODate("2026-10-23T06:10:00.000Z") }
    }
  },
  // Grava o resultado em consultas_salvas: a mesma consulta substitui a anterior; o índice
  // TTL apaga o documento quando passa do expiraEm.
  {
    $merge: {
      into: "consultas_salvas",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
