# Arquitetura

Extraído do código em `frota/`, `jobs/`, `api/` e `frontend/`.

## Componentes

| Módulo | Responsabilidade |
|---|---|
| `frota/settings.py` | `.env` → URI, nomes de banco, porta, valores iniciais da `config`. |
| `frota/db.py` | `MongoClient` único por URI (`w=majority`, `retryWrites`), codec tz-aware UTC, guarda `guardar_escrita` (destrutivo só em `*_test`/`*_fixtures` ou com `ALLOW_DEMO_DB_WRITE=1`). |
| `frota/schemas.py` | `$jsonSchema` de cada collection (`strict`/`error`). |
| `frota/bootstrap.py` | `createCollection`/`collMod` + índices + TTL via `collMod`; idempotente. |
| `frota/config.py` | Documento `config` `_id: "ativa"`, validação de turnos, `versao` incrementada a cada mudança. |
| `frota/janela.py` | Janela semiaberta em dias locais, `derivar_chave` (dow/turno de um instante), validação de turnos. |
| `frota/pipelines/` | `camada1`, `camada2`, `raw_onthefly`, `expressoes` (turno/dow gerados da config). Cada estágio carrega comentário. |
| `frota/pipelines/simples.py` | Modo simples (default): raw → média num pipeline, `$out`. |
| `frota/job.py` | Despacho por `modoMaterializacao` (simples × incremental) e grão (turno × hora); assinatura e cobertura do grão para decidir carga/recarga/incremental; planejamento da camada 1 (D-1…D-k ∪ atrasos pelo watermark), execução das camadas, lease em `job_locks`, retry com backoff, `job_runs`. |
| `frota/consulta.py` | `fallback` (find ≤ 21 docs + hierarquia) e `onthefly` (mesma pergunta na raw). |
| `frota/explain.py` | Resumo do `explain("executionStats")` (estágio vencedor, índices, keys/docs examinados). |
| `frota/capo.py` | Metadados lidos de `listCollections`/`listIndexes` e badges derivados do pipeline executado. |
| `frota/gerador.py`, `frota/seed.py`, `frota/simulacao.py` | Dados sintéticos determinísticos, relógio simulado, `ingestao_pendente`, avanço de dias, injeção de atraso. |
| `jobs/materializar.py` | CLI do job (o que o agendador chamaria). |
| `api/main.py` | FastAPI 8410; serve `frontend/dist` quando compilado. |
| `frontend/` | Vite + React 5410, proxy para 8410. Sem lógica de negócio. |

## Fluxo

Simples (default):
```
trecho_observacoes ──($match janela → turno/dow → $group → $out)──▶ trecho_media_historica
```

Incremental (grão `turno` em `trecho_bucket_turno` ou `hora` em `trecho_bucket_diario`):
```
trecho_observacoes ──(camada 1: $match dias → $group dia local×hora → $merge replace)──▶ trecho_bucket_diario
trecho_bucket_diario ──(camada 2: $match janela → turno/dow → $group → $merge+runId | $out)──▶ trecho_media_historica
trecho_media_historica ──(find {origem, destino, tipoVeiculo}, ≤ 21 docs)──▶ fallback de ETA
```

## Decisões de código

- `asOf` sempre por parâmetro; `$$NOW` só em `atualizadoEm` (auditoria).
- Limites de janela calculados em Python com `zoneinfo` e enviados prontos ao pipeline.
- Turno/dow são expressões geradas da `config` e compartilhadas pela camada 2 e pela consulta na raw.
- Contadores de inseridos/atualizados/removidos são derivados de contagens antes/depois
  (o `$merge` não devolve contagens).
- Job e mudanças de config vindos da UI são serializados por um lock de processo, além do lease no banco.
