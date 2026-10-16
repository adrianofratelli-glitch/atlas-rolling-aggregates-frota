// Consulta de fallback: uma leitura, ≤ 21 docs pelo índice único chave_media_unica
db.trecho_media_historica.find({ origem: "BASE-001", destino: "POSTO-0042", tipoVeiculo: "BITREM" })
db.trecho_media_historica.find({ origem: "BASE-001", destino: "POSTO-0042", tipoVeiculo: "BITREM" }).explain('executionStats')
