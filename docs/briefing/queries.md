# Consultas e pipelines

Fonte: `frota/pipelines/*.py`, `frota/consulta.py`, `frota/job.py`. Versões coláveis em
`docs/pipelines/`.

| Operação | Collection | Forma | Índice |
|---|---|---|---|
| Camada 1 | `trecho_observacoes` | `$match observadoEm [a,b)` (um `$or` se houver dias atrasados não contíguos) → `$group` por o/d/tipo + `$dateTrunc(day, tz)` + `$hour(tz)` → `$project` (+`dowCivil`) → `$merge` on chave do bucket, `replace`/`insert` | `observadoEm_1_ttl`; `chave_bucket_unica` (exigido pelo `on`) |
| Limpeza camada 1 | `trecho_bucket_diario` | `deleteMany({dataLocal ∈ dias, runId ≠ atual})` | `dataLocal_1_ttl` |
| Detecção de atraso | `trecho_observacoes` | `$match ingeridoEm (wmAnterior, wmNovo]` → `$match observadoEm` na janela → `$group` por dia local | `ingeridoEm_1` |
| Camada 2 | `trecho_bucket_diario` | `$match dataLocal [início, fim)` → `$set turno ($switch), dow` → `$group` por o/d/tipo/dow/turno → `$project` médias → `$merge` ou `$out` | `dataLocal_1_ttl`; `chave_media_unica` |
| Limpeza camada 2 (`merge_runid`) | `trecho_media_historica` | `deleteMany({runId ≠ atual})` | — (scan da collection pequena) |
| Fallback | `trecho_media_historica` | `find({origem, destino, tipoVeiculo})` | `chave_media_unica` (prefixo) |
| On the fly | `trecho_observacoes` | `$match o/d/tipo + observadoEm [início, fim)` → `$set hora/dowCivil` → turno/dow → `$group` | `origem_1_destino_1_tipoVeiculo_1_observadoEm_1` |
| Lock | `job_locks` | `findOneAndUpdate({_id, expiraEm < agora}, $set, upsert)`; `DuplicateKeyError` = ocupado | `_id`; TTL `expiraEm_ttl` |

Nenhuma consulta usa `$regex`, `$lte` no limite superior da janela, `$inc` em `$merge` ou relógio do sistema para limites.
