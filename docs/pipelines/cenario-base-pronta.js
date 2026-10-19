// Cenário na janela padrão: soma os documentos prontos do job (seg–sex, 6h–12h).
db.trecho_media_dow_hora.aggregate([
  // Pega na base pronta só a rota e o tipo de veículo pedidos, nos dias da semana e nas
  // horas escolhidos.
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-11",
      tipoVeiculo: "CARRETA",
      dow: { $in: [ 1, 2, 3, 4, 5 ] },  // dias da semana escolhidos (1 = segunda … 7 = domingo)
      hora: { $in: [ 6, 7, 8, 9, 10, 11 ] }  // horas cheias escolhidas (8 = das 08:00 às 08:59)
    }
  },
  // Soma as contagens e as somas guardadas pelo job e conta quantos documentos prontos
  // foram somados.
  {
    $group: {
      _id: null,  // null = um grupo só: soma tudo que passou pelo filtro
      n: { $sum: "$n" },  // total de observações = soma das contagens que o job já guardou
      somaMin: { $sum: "$somaMin" },  // soma dos tempos de viagem, em minutos
      somaQuadMin: { $sum: "$somaQuadMin" },  // soma de tempo × tempo: é o que permite calcular o desvio padrão depois
      somaKm: { $sum: "$somaKm" },  // soma das distâncias, em km
      docs: { $sum: 1 }  // quantos documentos prontos entraram na conta
    }
  }
])
