// Job diário com dataRef 2026-10-22: janela [2026-04-25T03:00Z, 2026-10-22T03:00Z) → média por rota × dia da semana × hora, $merge replace.
db.trecho_observacoes.aggregate([
  // Pega só as observações dos últimos 180 dias, sem o dia de hoje.
  {
    $match: {
      observadoEm: { $gte: ISODate("2026-04-25T03:00:00.000Z"), $lt: ISODate("2026-10-22T03:00:00.000Z") }  // o início entra ($gte), o fim fica de fora ($lt)
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
  // Agrupa por rota, tipo de veículo, dia da semana e hora, guardando contagem e somas.
  {
    $group: {
      _id: {  // chave do grupo: cada combinação vira um documento de média
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dow: "$dow",
        hora: "$hora"
      },
      n: { $sum: 1 },  // conta 1 por observação
      somaMin: { $sum: "$tempoMin" },  // soma dos tempos de viagem, em minutos
      somaQuadMin: { $sum: { $multiply: [ "$tempoMin", "$tempoMin" ] } },  // soma de tempo × tempo: é o que permite calcular o desvio padrão depois
      somaKm: { $sum: "$distanciaKm" }  // soma das distâncias, em km
    }
  },
  // Arredonda as somas, calcula as médias e carimba o resultado com a data e o número da
  // execução.
  {
    $project: {
      _id: 0,  // 0 = não devolve o _id
      origem: "$_id.origem",
      destino: "$_id.destino",
      tipoVeiculo: "$_id.tipoVeiculo",
      dow: "$_id.dow",
      hora: "$_id.hora",
      n: 1,
      somaMin: { $round: [ "$somaMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaQuadMin: { $round: [ "$somaQuadMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaKm: { $round: [ "$somaKm", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      mediaMin: { $divide: [ "$somaMin", "$n" ] },  // média = soma ÷ quantidade de observações
      mediaKm: { $divide: [ "$somaKm", "$n" ] },  // média = soma ÷ quantidade de observações
      janelaInicio: { $literal: ISODate("2026-04-25T03:00:00.000Z") },  // carimbo desta execução, gravado como está
      janelaFim: { $literal: ISODate("2026-10-22T03:00:00.000Z") },  // carimbo desta execução, gravado como está
      dataRef: { $literal: "2026-10-22" },  // carimbo desta execução, gravado como está
      runId: { $literal: "<runId>" },  // carimbo desta execução, gravado como está
      atualizadoEm: "$$NOW"  // $$NOW = o instante em que o documento é gravado
    }
  },
  // Grava o resultado numa collection persistente (a "materialized view"): se já existe um
  // documento com a mesma chave, ele é substituído; se não, é inserido.
  {
    $merge: {
      into: "trecho_media_dow_hora",  // collection de destino
      on: [ "origem", "destino", "tipoVeiculo", "dow", "hora" ],  // campos que dizem quando é "o mesmo documento"
      whenMatched: "replace",  // mesma chave: troca o documento inteiro (nunca soma por cima)
      whenNotMatched: "insert"  // chave nova: insere
    }
  }
])
