# Consultas no mongosh

Comandos para conferir cada camada direto no banco. As saídas abaixo foram **copiadas do
mongosh** sobre o dataset de fixtures (`make fixtures`, banco `frota_eta_fixtures`, asOf
2026-10-16). Com o perfil sintético (`make seed`) os valores mudam; a forma não.

```bash
mongosh "mongodb://localhost:27027/frota_eta_fixtures?replicaSet=rs0"
```

Os pipelines completos, comentados estágio a estágio, estão em [`pipelines/`](pipelines/)
(`*.js` para colar no mongosh, `*.json` em EJSON). São gerados por `make pipelines` a
partir dos mesmos módulos que o job executa.

## 1. Agregado de um trecho/veículo (o que o fallback lê)

```js
db.trecho_media_historica.find(
  { origem: "BASE-001", destino: "POSTO-0042", tipoVeiculo: "BITREM" },
  { _id: 0, dow: 1, turno: 1, n: 1, somaMin: 1, mediaMin: 1, mediaKm: 1 }
).sort({ dow: 1, turno: 1 })
```
```text
[
  { somaMin: 30, n: 1, dow: 1, turno: 'N', mediaMin: 30, mediaKm: 38 },
  { somaMin: 45, n: 1, dow: 5, turno: 'N', mediaMin: 45, mediaKm: 39 },
  { somaMin: 168, n: 3, dow: 6, turno: 'N', mediaMin: 56, mediaKm: 40 },
  { somaMin: 70, n: 1, dow: 7, turno: 'N', mediaMin: 70, mediaKm: 42 }
]
```

`{dow: 6, turno: "N"}` soma as três sextas (25/09, 02/10, 09/10). `dow: 1` é a borda
inicial (19/04 00:00:00.000) e `dow: 5` a borda final (15/10 23:59:59.999).

## 2. Explain da consulta de fallback

```js
const e = db.trecho_media_historica
  .find({ origem: "BASE-001", destino: "POSTO-0042", tipoVeiculo: "BITREM" })
  .explain("executionStats");
printjson({ stage: e.queryPlanner.winningPlan.stage,
            input: e.queryPlanner.winningPlan.inputStage.stage,
            index: e.queryPlanner.winningPlan.inputStage.indexName,
            keys: e.executionStats.totalKeysExamined,
            docs: e.executionStats.totalDocsExamined })
```
```text
{ stage: 'FETCH', input: 'IXSCAN', index: 'chave_media_unica', keys: 4, docs: 4 }
```

## 3. Hoje e bordas fora da janela não vazam

As observações 5, 7 e 9 do contrato (hoje 20:00, D-181 23:59:59.999, hoje 00:00) têm
`tempoMin: 999`. Estão na raw e em nenhum agregado:

```js
db.trecho_observacoes.countDocuments({ tempoMin: 999 })            // 3
db.trecho_media_historica.countDocuments({ somaMin: { $gte: 999 } }) // 0
```

## 4. Buckets no dia/hora **local**

A observação de terça 13/10 23:30 em São Paulo é 14/10 02:30 em UTC. O bucket fica em
13/10, hora 23:

```js
db.trecho_bucket_diario.find(
  { destino: "POSTO-0007", tipoVeiculo: "CARRETA" },
  { _id: 0, dataLocal: 1, hora: 1, dowCivil: 1, n: 1, somaMin: 1 }
).sort({ hora: 1 })
```
```text
[
  { somaMin: 30, n: 1, dataLocal: ISODate('2026-10-13T03:00:00.000Z'), hora: 7, dowCivil: 3 },
  { somaMin: 25, n: 1, dataLocal: ISODate('2026-10-13T03:00:00.000Z'), hora: 14, dowCivil: 3 },
  { somaMin: 18, n: 1, dataLocal: ISODate('2026-10-13T03:00:00.000Z'), hora: 23, dowCivil: 3 }
]
```

`dataLocal` é 00:00 do dia em São Paulo guardado como instante UTC (03:00Z).

## 5. Validator recusa data como string

```js
db.trecho_observacoes.insertOne({ origem: "BASE-001", destino: "POSTO-0042",
  tipoVeiculo: "BITREM", veiculoId: "V", viagemId: "X", seq: 1,
  observadoEm: "2026-10-15T20:00:00-03:00", ingeridoEm: new Date(),
  distanciaKm: 39, tempoMin: 50 })
```
```text
121 Document failed validation
```

## 6. Índices e TTL lidos do banco

```js
db.trecho_bucket_diario.getIndexes().map(i => [i.name, i.unique || false, i.expireAfterSeconds])
```
```text
[
  [ '_id_', false, undefined ],
  [ 'chave_bucket_unica', true, undefined ],
  [ 'dataLocal_1_ttl', false, 16416000 ]   // 190 dias
]
```

## 7. Último run do job

```js
db.job_runs.find({}, { _id: 0, runId: 1, asOf: 1, status: 1, "stats.camada1.modo": 1,
  "stats.camada1.lidos": 1, "stats.camada2.inseridos": 1 }).sort({ iniciadoEm: -1 }).limit(1)
```
```text
[ { runId: '2026-10-16T20:53:21Z-8558', asOf: '2026-10-16', status: 'ok',
    stats: { camada1: { modo: 'carga_inicial', lidos: 11 }, camada2: { inseridos: 9 } } } ]
```

(`lidos: 11` = observações dentro da janela: 14 no dataset menos as 3 marcadas com 999.)
