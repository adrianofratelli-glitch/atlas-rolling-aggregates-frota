// Cenário sob demanda salvo: o $merge em consultas_salvas é o último estágio (TTL apaga quando passa do expiraEm).
db.trecho_observacoes.aggregate([
  // Pega as observações da rota e do tipo de veículo no período pedido (o fim fica de
  // fora).
  {
    $match: {
      origem: "BASE-001",
      destino: "POSTO-11",
      tipoVeiculo: "CARRETA",
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
  // Arredonda as somas e calcula a estimativa: média e desvio padrão do tempo e média de
  // km, identifica a consulta pela chave do filtro e marca até quando ela vale.
  {
    $project: {
      _id: { $literal: "<chave do filtro>" },  // a chave é o identificador do filtro: a mesma consulta cai no mesmo documento
      n: 1,
      somaMin: { $round: [ "$somaMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaQuadMin: { $round: [ "$somaQuadMin", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      somaKm: { $round: [ "$somaKm", 6 ] },  // arredonda para 6 casas (tira ruído de ponto flutuante)
      mediaMin: { $divide: [ "$somaMin", "$n" ] },  // média do tempo (min) = somaMin ÷ n
      desvioMin: {  // desvio padrão = raiz( média dos quadrados − quadrado da média ); $max(0, …) evita raiz de negativo por arredondamento
        $sqrt: {
          $max: [
            0,
            {
              $subtract: [
                { $divide: [ "$somaQuadMin", "$n" ] },
                { $pow: [ { $divide: [ "$somaMin", "$n" ] }, 2 ] }
              ]
            }
          ]
        }
      },
      mediaKm: { $divide: [ "$somaKm", "$n" ] },  // média = soma ÷ quantidade de observações
      filtro: {
        $literal: {
          origem: "BASE-001",
          destino: "POSTO-11",
          tipoVeiculo: "CARRETA",
          dias: [ 1, 2, 3, 4, 5 ],
          horas: [ 6, 7, 8, 9, 10, 11 ],
          periodo: { tipo: "padrao" }
        }
      },
      periodo: { $literal: "relativo" },
      criadoEm: "$$NOW",  // $$NOW = o instante em que o documento é gravado
      expiraEm: { $literal: ISODate("2026-10-23T06:10:00.000Z") }  // o índice TTL apaga o documento quando chegar nesta data
    }
  },
  // Grava o resultado em consultas_salvas: a mesma consulta substitui a anterior; o índice
  // TTL apaga o documento quando passa do expiraEm.
  {
    $merge: {
      into: "consultas_salvas",  // collection de destino
      on: "_id",  // campos que dizem quando é "o mesmo documento"
      whenMatched: "replace",  // mesma chave: troca o documento inteiro (nunca soma por cima)
      whenNotMatched: "insert"  // chave nova: insere
    }
  }
])
