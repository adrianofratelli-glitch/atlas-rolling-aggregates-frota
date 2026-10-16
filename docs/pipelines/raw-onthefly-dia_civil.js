// Mesma resposta do fallback calculada na raw (regraNoite dia_civil).
db.trecho_observacoes.aggregate([
  // Todas as observações do trecho/veículo na janela [início, fim). Usa o índice { origem,
  // destino, tipoVeiculo, observadoEm }.
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-0042",
      tipoVeiculo: "BITREM",
      observadoEm: { $gte: ISODate("2026-04-19T03:00:00.000Z"), $lt: ISODate("2026-10-16T03:00:00.000Z") }
    }
  },
  // Hora e dia da semana locais de cada observação, no momento da consulta.
  {
    $set: {
      hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },
      dowCivil: { $dayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } }
    }
  },
  // Mesmas expressões de turno/dow da camada 2.
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
  // Mesmo grão do agregado: dow × turno.
  {
    $group: {
      _id: { dow: "$dow", turno: "$turno" },
      somaMin: { $sum: "$tempoMin" },
      somaKm: { $sum: "$distanciaKm" },
      n: { $sum: 1 }
    }
  },
  // Mesmo formato dos documentos de trecho_media_historica.
  {
    $project: { _id: 0, dow: "$_id.dow", turno: "$_id.turno", somaMin: 1, somaKm: 1, n: 1 }
  }
])
