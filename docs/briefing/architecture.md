# Arquitetura

Extraído do código em `frota/`, `jobs/`, `scripts/`, `api/`, `frontend/` e `atlas-trigger/` (v2.0.0).

## Componentes

| Módulo | Responsabilidade |
|---|---|
| `frota/settings.py` | `.env` → alvo (Atlas se `MONGODB_URI` preenchida, senão Docker 27027; `FROTA_MONGO=local` força), bancos, porta, semente. Constantes de negócio no código: `TZ`, `JANELA_DIAS=180`, `MIN_AMOSTRAS=5`, `TTL_RAW_DIAS=200`, `DIAS_SIMULADOS=14`, TTL do salvo (padrão 7, máx. 30), `JOB_HORA_LOCAL=(3, 10)`, crons UTC do job e da ingestão. Sem collection `config`. |
| `frota/db.py` | `MongoClient` único por URI (`w=majority`, `retryWrites`), codec tz-aware UTC, `guardar_escrita` (destrutivo só em `*_test` ou com `ALLOW_DEMO_DB_WRITE=1`), `mascarar` (tira host/porta/URI de mensagens de erro). |
| `frota/schemas.py` | `$jsonSchema` de cada collection (`strict`/`error`) e o `enum` de tipos de veículo. |
| `frota/bootstrap.py` | `createCollection`/`collMod` só quando o contrato mudou, índices, ajuste de TTL e remoção de índices fora do contrato; idempotente. |
| `frota/janela.py` | Funções puras: `inicio_dia`, `hoje_local`, `janela_padrao`, `horas_da_faixa` (semiaberta, cruza meia-noite), atalhos Manhã/Tarde/Noite, `proximo_job`, `periodo_para_intervalo` (padrão, datas, últimos N dias). |
| `frota/pipelines/` | Builders comentados (`Estagio(comentario, estagio)`): `job` (raw → base), `cenario` (`base` e `raw`, com `$merge` opcional em `consultas_salvas`), `ingestao` (fila → raw). |
| `frota/job.py` | `rodar_job(db, data_ref, origem)`: lê o relógio do servidor (`hello.localTime`), roda o pipeline, limpa `atualizadoEm < inícioDoRun`, registra `job_runs` (erro mascarado). |
| `frota/cenario.py` | `Filtro` (validação, chave sha1, `veiculoId` opcional), `veiculos_por_tipo` (distinct da raw em ordem natural), `consultar`: base pronta (só janela padrão sem veículo) com ampliação por poucas amostras, ou sob demanda na raw com leitura/gravação em `consultas_salvas`. |
| `frota/ingestao.py` | `ingerir(db, agora)`: escolhe os `_id` já vencidos da fila, `$merge` só deles e apaga só eles. |
| `frota/previa.py` | Prévia do próximo job (só leitura): dia que entra, dia que sai, chaves que somem. O `$group` das chaves percorre 180 dias de raw (~3,4 s no Atlas); a API guarda esse número em memória por (banco, dataRef, último run ok, tamanho estimado da raw), então a revisita é imediata e a ingestão ou um novo job invalidam. |
| `frota/operadores.py`, `frota/mongosh.py` | Bloco `query` (lê, grava, mongosh, operadores explicados) e serialização para JSON/mongosh. |
| `frota/gerador.py`, `frota/seed.py` | Gerador determinístico (perfis `demo` com 15 veículos por tipo e `teste` com 3, padrões por dia/hora/veículo, trechos esparsos) e `resetar` em torno do instante do clique (raw até agora, 14 dias futuros na fila, job). |
| `jobs/materializar.py` | CLI do job (`--data`, `--db`), origem `cli`. |
| `scripts/` | `bootstrap_db.py`, `seed.py`, `ingerir.py`, `export_pipelines.py` (docs + Functions), `trigger_deploy.sh`, `limpar_atlas.py`, `ui_smoke.py`, `capturar_prints.py`. |
| `atlas-trigger/` | App App Services com 2 Scheduled Triggers (`jobDiario` 03:10 SP, `ingestaoSimulada` de hora em hora); Functions geradas por `make pipelines`. Não implantado na demo. |
| `api/main.py` | FastAPI 8410; único lugar que lê `datetime.now()`; serve `frontend/dist` quando compilado. |
| `frontend/` | Vite + React 5410, proxy para 8410, uma página com roteiro de 5 passos. Sem lógica de negócio. |

## Fluxo

```
ingestao_simulada ──(de hora em hora: $match _id ∈ vencidos → $project → $merge on viagemId+seq)──▶ trecho_observacoes
trecho_observacoes ──(job: $match janela → $set dow/hora → $group → $project → $merge replace)──▶ trecho_media_dow_hora
trecho_media_dow_hora ──($match chave + dow + hora → $group)──▶ cenário "Job diário"
trecho_observacoes ──(outro período: $match → $set → $match → $group → $project [→ $merge])──▶ cenário "Sob demanda" / consultas_salvas
```

## Decisões de código

- `dataRef`/`agora` sempre por parâmetro; `$$NOW` só em `atualizadoEm`/`criadoEm`.
- Limites calculados em Python com `zoneinfo` e enviados prontos; limite superior `$lt`.
- `$merge` sempre `whenMatched: "replace"`; documentos guardam somas e contagem.
- Limpeza do job pelo relógio do servidor: dois runs sobrepostos não se apagam; sem lease.
- `/api/reset` libera a escrita no banco da demo só para si (`permitir=True`) e roda numa
  thread; durante o reset `/api/colecoes`, `/api/job` e `/api/cenario` respondem 409 e não há
  bootstrap.
- Respostas e erros da API passam por `mascarar`; o campo `owner` nunca sai.
