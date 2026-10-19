# Consultas no mongosh

Comandos para conferir cada etapa direto no banco. As saídas foram obtidas no banco da
demo `frota_eta` logo depois de um reset em 2026-10-19 (dataRef 2026-10-19, janela
`[2026-04-22T03:00Z, 2026-10-19T03:00Z)`). Os dados são sintéticos; depois de outro reset
os números mudam, a forma não.

```bash
mongosh "<sua connection string>/frota_eta"
```

Os pipelines completos, comentados estágio a estágio, estão em [`pipelines/`](pipelines/)
(`*.js` para colar no mongosh, `*.json` em EJSON). São gerados por `make pipelines` a
partir dos mesmos módulos que o job e a API executam.

## 1. A base pronta de um trecho (sexta, 12h–18h)

```js
db.trecho_media_dow_hora.find(
  { origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA",
    dow: 5, hora: { $in: [12, 13, 14, 15, 16, 17] } },
  { _id: 0, dow: 1, hora: 1, n: 1, mediaMin: 1, mediaKm: 1 }
).sort({ hora: 1 })
```
```text
[
  { n: 26, dow: 5, hora: 12, mediaMin: 89.16538461538462, mediaKm: 54.62346153846154 },
  { n: 26, dow: 5, hora: 13, mediaMin: 83.91576923076923, mediaKm: 54.94653846153846 },
  { n: 26, dow: 5, hora: 14, mediaMin: 90.1573076923077, mediaKm: 54.5226923076923 },
  { n: 26, dow: 5, hora: 15, mediaMin: 88.31884615384615, mediaKm: 54.58153846153846 },
  { n: 26, dow: 5, hora: 16, mediaMin: 87.75500000000001, mediaKm: 54.905 },
  { n: 78, dow: 5, hora: 17, mediaMin: 110.6278205128205, mediaKm: 54.44858974358974 }
]
```

`dow` segue o `$isoDayOfWeek`: 5 = sexta. A hora 17 tem mais amostras e é mais lenta (pico
da tarde no gerador). Um trecho × veículo tem no máximo 168 documentos (7 × 24):

```js
db.trecho_media_dow_hora.countDocuments({ origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA" })  // 168
```

## 2. O cenário: somar os documentos prontos

É o que o passo 4 executa (`docs/pipelines/cenario-base-pronta.js`):

```js
db.trecho_media_dow_hora.aggregate([
  { $match: { origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA",
              dow: { $in: [5] }, hora: { $in: [12, 13, 14, 15, 16, 17] } } },
  { $group: { _id: null, n: { $sum: "$n" }, somaMin: { $sum: "$somaMin" },
              somaQuadMin: { $sum: "$somaQuadMin" }, somaKm: { $sum: "$somaKm" },
              docs: { $sum: 1 } } }
])
```
```text
[ { _id: null, n: 208, somaMin: 20051.09, somaQuadMin: 2027706.9007, somaKm: 11360.05, docs: 6 } ]
```

Média = 20051,09 / 208 = **96,4 min**; desvio = √(2027706,9007 / 208 − 96,4²) ≈ **21,3
min**; km = 11360,05 / 208 ≈ **54,6 km** — os números da tela do passo 4.

## 3. Explain do cenário

```js
const e = db.trecho_media_dow_hora.explain("executionStats").aggregate([ /* o pipeline acima */ ]);
```
```text
GROUP ← FETCH ← IXSCAN chave_unica · totalKeysExamined: 6 · totalDocsExamined: 6
```

Seis chaves e seis documentos, independentemente de quantas observações o trecho tem.

## 4. Mesmo cenário em outro período, direto na raw

Sextas à tarde de 2026-09-21 a 2026-10-18 (passo 4 com "Datas específicas", sem guardar):

```js
db.trecho_observacoes.aggregate([
  { $match: { origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA",
              observadoEm: { $gte: ISODate("2026-09-21T03:00:00Z"), $lt: ISODate("2026-10-19T03:00:00Z") } } },
  { $set: { dow: { $isoDayOfWeek: { date: "$observadoEm", timezone: "America/Sao_Paulo" } },
            hora: { $hour: { date: "$observadoEm", timezone: "America/Sao_Paulo" } } } },
  { $match: { dow: { $in: [5] }, hora: { $in: [12, 13, 14, 15, 16, 17] } } },
  { $group: { _id: null, n: { $sum: 1 }, somaMin: { $sum: "$tempoMin" },
              somaQuadMin: { $sum: { $multiply: ["$tempoMin", "$tempoMin"] } },
              somaKm: { $sum: "$distanciaKm" } } },
  { $project: { _id: 0, n: 1, somaMin: { $round: ["$somaMin", 6] },
                somaQuadMin: { $round: ["$somaQuadMin", 6] }, somaKm: { $round: ["$somaKm", 6] } } }
])
```
```text
[ { n: 32, somaMin: 3244.23, somaQuadMin: 362166.8369, somaKm: 1743.93 } ]
```

Média ≈ 101,4 min em 32 amostras. Com "guardar o resultado", o pipeline ganha um `$merge` em
`consultas_salvas` no fim (`docs/pipelines/cenario-raw-salvo.js`).

### 4.1 Um veículo específico, na janela padrão

A base é por tipo de veículo, então um veículo vai sempre à raw, mesmo na janela padrão. O
`$match` ganha `veiculoId` e usa o mesmo índice composto (sem índice novo):

```js
db.trecho_observacoes.aggregate([
  { $match: { origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA",
              veiculoId: "VEI-CARRETA-7",
              observadoEm: { $gte: ISODate("2026-04-22T03:00:00Z"), $lt: ISODate("2026-10-19T03:00:00Z") } } },
  /* $set, $match de dia/hora, $group e $project iguais aos da seção 4 */
])
```
```text
[ { n: 14, somaMin: 1528.06, somaQuadMin: 183642.88, somaKm: 768.62 } ]
```

Média ≈ 109,1 min em 14 amostras; 432 observações do veículo no período ("docs lidos" na
tela). O `explain` mostra o custo de verdade: `IXSCAN origem_1_destino_1_tipoVeiculo_1_observadoEm_1`
com 6480 chaves e 6480 documentos examinados (todas as observações do trecho × tipo na
janela; o `veiculoId` é filtrado depois do índice). Com "guardar o resultado" (o padrão na
tela), o fim do pipeline é o mesmo `$merge` e o salvo vale até o próximo job
(`docs/pipelines/cenario-raw-veiculo.js`).

Saída medida com o gerador da v2.1 (semente 42, `dataRef` 2026-10-19) num banco local de
teste; as demais seções não mudam com a v2.1 (o volume e os tempos sorteados são os mesmos,
só a distribuição entre veículos mudou).

## 5. Hoje fica fora

```js
db.trecho_observacoes.countDocuments({ observadoEm: { $gte: ISODate("2026-10-19T03:00:00Z") } })  // 902
db.trecho_media_dow_hora.countDocuments({ janelaFim: { $ne: ISODate("2026-10-19T03:00:00Z") } })  // 0
```

A raw já tem 902 observações de hoje; nenhum documento da base usa outro fim de janela.

## 6. Índices e TTL

```js
db.trecho_observacoes.getIndexes()
```
```text
[
  { name: '_id_', key: { _id: 1 } },
  { name: 'viagemId_1_seq_1', key: { viagemId: 1, seq: 1 }, unique: true },
  { name: 'origem_1_destino_1_tipoVeiculo_1_observadoEm_1',
    key: { origem: 1, destino: 1, tipoVeiculo: 1, observadoEm: 1 } },
  { name: 'observadoEm_1_ttl', key: { observadoEm: 1 }, expireAfterSeconds: 17280000 }
]
```

`17280000` s = 200 dias.

```js
db.trecho_media_dow_hora.getIndexes()   // _id_ e chave_unica {origem, destino, tipoVeiculo, dow, hora} unique
db.consultas_salvas.getIndexes()        // _id_ e expiraEm_ttl {expiraEm: 1}, expireAfterSeconds: 0
```

## 7. Última execução do job

```js
db.job_runs.find({}, { _id: 0, origem: 1, dataRef: 1, status: 1, lidos: 1, gravados: 1, removidos: 1, ms: 1 })
  .sort({ iniciadoEm: -1 }).limit(1)
```
```text
[ { origem: 'reset', dataRef: '2026-10-19', status: 'ok', lidos: 312164, gravados: 8834, removidos: 0, ms: 5808.1 } ]
```

312.164 observações da janela viraram 8.834 documentos prontos em ~5,8 s (Atlas).
