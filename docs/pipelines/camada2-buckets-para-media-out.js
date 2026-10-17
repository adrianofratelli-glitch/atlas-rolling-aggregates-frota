// Camada 2 com asOf 2026-10-16, janela [2026-04-19T03:00Z, 2026-10-16T03:00Z), limpeza out.
db.trecho_bucket_diario.aggregate([
  // Recorte da janela móvel sobre o dia local do bucket: [início, fim) semiaberto, sem
  // $lte. Usa o índice { dataLocal: 1 }. O dia de hoje nunca entra porque fim = 00:00
  // local de asOf.
  {
    $match: {
      dataLocal: { $gte: ISODate("2026-04-19T03:00:00.000Z"), $lt: ISODate("2026-10-16T03:00:00.000Z") }
    }
  },
  // Chave sem data: 'toda sexta à noite' = { dow: 6, turno: 'N' } soma todas as sextas da
  // janela. Soma de somas e de contagens (Computed Pattern).
  {
    $group: {
      _id: {
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dow: "$dow",
        turno: "$turno"
      },
      somaMin: { $sum: "$somaMin" },
      somaKm: { $sum: "$somaKm" },
      n: { $sum: "$n" }
    }
  },
  // Média = soma / contagem, calculada uma vez aqui e não na consulta (somas arredondadas
  // a 6 casas, como na camada 1). Grava janela, asOf e versão da config.
  {
    $project: {
      _id: 0,
      origem: "$_id.origem",
      destino: "$_id.destino",
      tipoVeiculo: "$_id.tipoVeiculo",
      dow: "$_id.dow",
      turno: "$_id.turno",
      somaMin: { $round: [ "$somaMin", 6 ] },
      somaKm: { $round: [ "$somaKm", 6 ] },
      n: 1,
      mediaMin: { $divide: [ { $round: [ "$somaMin", 6 ] }, "$n" ] },
      mediaKm: { $divide: [ { $round: [ "$somaKm", 6 ] }, "$n" ] },
      janelaInicio: { $literal: ISODate("2026-04-19T03:00:00.000Z") },
      janelaFim: { $literal: ISODate("2026-10-16T03:00:00.000Z") },
      asOf: { $literal: "2026-10-16" },
      configVersao: { $literal: 1 },
      runId: { $literal: "<runId>" },
      atualizadoEm: "$$NOW"
    }
  },
  // out: troca atômica da collection inteira pelo resultado (preserva índices e opções).
  // Chaves fora da janela simplesmente deixam de existir.
  { $out: "trecho_media_historica" }
])
