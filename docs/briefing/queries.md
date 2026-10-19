# Consultas e pipelines

Fonte: `frota/pipelines/*.py`, `frota/job.py`, `frota/cenario.py`, `frota/ingestao.py`,
`frota/previa.py`, `api/main.py`. Versões coláveis em `docs/pipelines/`.

| Operação | Collection | Forma | Índice |
|---|---|---|---|
| Job diário | `trecho_observacoes` | `$match observadoEm [início, fim)` → `$set dow: $isoDayOfWeek{tz}, hora: $hour{tz}` → `$group` por o/d/tipo/dow/hora (`n`, `somaMin`, `somaQuadMin`, `somaKm`) → `$project` (`$round` 6, médias, janela, `dataRef`, `runId`, `atualizadoEm: $$NOW`) → `$merge` on chave, `replace`/`insert` | `observadoEm_1_ttl`; `chave_unica` (exigido pelo `on`) |
| Limpeza do job | `trecho_media_dow_hora` | `deleteMany({atualizadoEm: {$lt: inícioDoRun}})` (relógio do servidor) | — (collection pequena) |
| Contagem de lidos | `trecho_observacoes` | `countDocuments({observadoEm: [início, fim)})` | `observadoEm_1_ttl` |
| Docs lidos do sob demanda | `trecho_observacoes` | `countDocuments` com o filtro do primeiro `$match` (com `veiculoId`, conta só o veículo e um segundo count sem `veiculoId` vira `docsExaminados`, o que o índice percorre: trecho × tipo inteiro) | `origem_1_destino_1_tipoVeiculo_1_observadoEm_1` |
| Cenário na base | `trecho_media_dow_hora` | `$match {o, d, tipo, dow $in, hora $in}` → `$group` somando `n`/somas, `docs` | `chave_unica` |
| Ampliação | `trecho_media_dow_hora` | mesmo aggregate com todos os dias e depois com 24 horas, se `n < 5` | `chave_unica` |
| Sob demanda (outro período, ou um veículo mesmo na janela padrão) | `trecho_observacoes` | `$match o/d/tipo (+ veiculoId) + observadoEm [início, fim)` → `$set dow/hora` → `$match dow/hora` → `$group` → `$project` [→ `$merge` em `consultas_salvas` on `_id`, `replace`] | `origem_1_destino_1_tipoVeiculo_1_observadoEm_1` |
| Veículos por tipo (`/api/opcoes`) | `trecho_observacoes` | `$group {_id: {t: tipoVeiculo, v: veiculoId}}` (uma vez por banco, em cache na API até o reset) | — (varre a raw) |
| Leitura do salvo | `consultas_salvas` | `findOne({_id: chave, expiraEm: {$gt: agora}})` | `_id`; TTL `expiraEm_ttl` |
| Ingestão simulada | `ingestao_simulada` | `find(observadoEm < agora, {_id})` → `$match _id $in` → `$project {_id: 0}` → `$merge` em `trecho_observacoes` on `{viagemId, seq}`, `replace` → `deleteMany(_id $in)` | `observadoEm_1`; `viagemId_1_seq_1` |
| Prévia do próximo job | `trecho_observacoes`, `trecho_media_dow_hora` | `countDocuments` do dia que entra e do que sai; `$group` de chaves distintas na nova janela vs chaves da base | `observadoEm_1_ttl` |
| Amostra do passo 1 | `trecho_observacoes` | `find({o, d, tipo}).sort({observadoEm: -1}).limit(3000)` + escolha de 12 em Python | `origem_1_destino_1_tipoVeiculo_1_observadoEm_1` |
| Schema do passo 1 | `trecho_observacoes` | `listCollections` (validator) e `listIndexes` | — |
| Histórico | `job_runs` | `find().sort({iniciadoEm: -1}).limit(n)` | `iniciadoEm_-1` |

Nenhuma consulta usa `$regex`, `$lte` no limite superior da janela, `$inc` em `$merge` ou o
relógio do sistema para limites.
