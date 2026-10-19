// Cenário fora da janela padrão (últimos 30 dias): o mesmo cálculo direto na raw, sem salvar.
db.trecho_observacoes.aggregate([
  // Pega as observações da rota e do tipo de veículo no período pedido (o fim fica de
  // fora).
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-11",
      tipoVeiculo: "CARRETA",
      observadoEm: { $gte: ISODate("2026-09-22T03:00:00.000Z"), $lt: ISODate("2026-10-22T03:00:00.000Z") }  // o início entra ($gte), o fim fica de fora ($lt)
    }
  },
  // Descobre o dia da semana (1 = segunda … 7 = domingo) e a hora, no horário de São
  // Paulo.
  {
    $set: {
      dow: { $isoDayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },  // 1 = segunda … 7 = domingo, no horário de São Paulo
      hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }  // 0 a 23, no horário de São Paulo
    }
  },
  // Fica só com os dias da semana e as horas escolhidos.
  { $match: { dow: { $in: [ 1, 2, 3, 4, 5 ] }, hora: { $in: [ 6, 7, 8, 9, 10, 11 ] } } },
  // Junta tudo num único resultado com contagem e somas.
  {
    $group: {
      _id: null,  // null = um grupo só: soma tudo que passou pelo filtro
      n: { $sum: 1 },  // conta 1 por observação
      somaMin: { $sum: "$tempoMin" },  // soma dos tempos de viagem, em minutos
      somaQuadMin: { $sum: { $multiply: [ "$tempoMin", "$tempoMin" ] } },  // soma de tempo × tempo: é o que permite calcular o desvio padrão depois
      somaKm: { $sum: "$distanciaKm" }  // soma das distâncias, em km
    }
  },
  // Arredonda as somas.
  {
    $project: {
      _id: 0,  // 0 = não devolve o _id
      n: 1,
      somaMin: { $round: [ "$somaMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaQuadMin: { $round: [ "$somaQuadMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaKm: { $round: [ "$somaKm", 6 ] }  // arredonda para 6 casas (tira ruído de ponto flutuante)
    }
  }
])
