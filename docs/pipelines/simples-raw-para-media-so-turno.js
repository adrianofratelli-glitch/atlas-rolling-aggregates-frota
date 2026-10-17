// Modo simples só por turno (incluirDow = false): ≤ 3 docs por trecho/veículo.
db.trecho_observacoes.aggregate([
  // Toda a janela [início, fim) — semiaberta, sem $lte; hoje fica fora porque fim = 00:00
  // local de asOf. Usa o índice { observadoEm: 1 }.
  {
    $match: {
      observadoEm: { $gte: ISODate("2026-04-19T03:00:00.000Z"), $lt: ISODate("2026-10-16T03:00:00.000Z") }
    }
  },
  // Hora e dia da semana locais (timezone da config), por observação.
  {
    $set: {
      hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },
      dowCivil: { $dayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }
    }
  },
  // Turno gerado de config.turnos v1; dow pela regraNoite = dia_civil (incluirDow = false:
  // dow 0, chave só por turno).
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
      dow: { $literal: 0 }
    }
  },
  // Chave sem data: { origem, destino, tipoVeiculo, dow, turno }. Soma e contagem
  // guardadas para que turno/geral sejam somas corretas na consulta.
  {
    $group: {
      _id: {
        origem: "$origem",
        destino: "$destino",
        tipoVeiculo: "$tipoVeiculo",
        dow: "$dow",
        turno: "$turno"
      },
      somaMin: { $sum: "$tempoMin" },
      somaKm: { $sum: "$distanciaKm" },
      n: { $sum: 1 }
    }
  },
  // Média calculada uma vez aqui (somas a 6 casas: $sum de doubles depende da ordem).
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
  // Troca atômica da collection (preserva índices e validator): leitores veem a versão
  // anterior ou a nova; chaves fora da janela deixam de existir.
  { $out: "trecho_media_historica" }
])
