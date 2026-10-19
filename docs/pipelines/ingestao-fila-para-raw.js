// Ingestão simulada às 2026-10-22T14:05Z: o que já passou sai da fila e entra na raw ($merge por viagemId + seq).
db.ingestao_simulada.aggregate([
  // Pega da fila só as observações cujo horário já passou.
  { $match: { observadoEm: { $lt: ISODate("2026-10-22T14:05:00.000Z") } } },
  // Tira o _id para que cada documento ganhe um novo na collection de destino.
  { $project: { _id: 0 } },
  // Grava na collection de observações; se a mesma viagem e trecho já estiverem lá, o
  // documento é substituído (não duplica).
  {
    $merge: {
      into: "trecho_observacoes",
      on: [ "viagemId", "seq" ],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
