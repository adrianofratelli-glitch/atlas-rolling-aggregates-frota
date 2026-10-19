// Cenário na janela padrão: soma os documentos prontos do job (seg–sex, 6h–12h).
db.trecho_media_dow_hora.aggregate([
  // Pega na base pronta só a rota e o tipo de veículo pedidos, nos dias da semana e nas
  // horas escolhidos.
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-11",
      tipoVeiculo: "CARRETA",
      dow: { $in: [ 1, 2, 3, 4, 5 ] },
      hora: { $in: [ 6, 7, 8, 9, 10, 11 ] }
    }
  },
  // Soma as contagens e as somas guardadas pelo job e conta quantos documentos prontos
  // foram somados.
  {
    $group: {
      _id: null,
      n: { $sum: "$n" },
      somaMin: { $sum: "$somaMin" },
      somaQuadMin: { $sum: "$somaQuadMin" },
      somaKm: { $sum: "$somaKm" },
      docs: { $sum: 1 }
    }
  }
])
