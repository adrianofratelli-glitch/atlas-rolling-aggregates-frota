# Mapa do código — atlas-rolling-aggregates-frota

> Também conhecida como: **Agregados em janela móvel (frota/ETA)**. Portas: frontend 5410 / backend 8410. Em uma frase: um job diário com `$merge` materializa a média de tempo por trecho × tipo de veículo × dia da semana × hora (janela de 180 dias), e a consulta de ETA lê essa base pronta, ou calcula na hora sobre a raw quando o filtro foge da base.

Briefings: [briefing/architecture.md](briefing/architecture.md), [briefing/queries.md](briefing/queries.md), [briefing/ui-flows.md](briefing/ui-flows.md). Outros: [consultas.md](consultas.md), [visao-tecnica.md](visao-tecnica.md), [roteiro-demo.md](roteiro-demo.md).

## 1. Árvore anotada

Todo o código Python fica em `backend/`, dividido em três pacotes (imports absolutos `backend.frota`, `backend.api`, `backend.jobs`):

- **`backend/api/` = as rotas** (FastAPI). Só recebe HTTP e chama o domínio.
- **`backend/frota/` = o domínio** (regra de negócio, pipelines, acesso ao banco, seed).
- **`backend/jobs/` = o job do Trigger**, versão linha de comando do job diário (em produção, quem roda é o Scheduled Trigger do Atlas, em `atlas-trigger/`).

```
backend/api/
  main.py                   todas as rotas /api/*, reset em thread, cache de veículos/prévia; serve frontend/dist se existir
backend/frota/
  settings.py               constantes de negócio (janela 180 d, mín. 5 amostras, 03:10, crons) e escolha do alvo (Atlas ou Docker local)
  db.py                     MongoClient, mascarar host em erro, guardar_escrita (só *_test sem ALLOW_DEMO_DB_WRITE=1)
  job.py                    rodar_job: o job diário (count, aggregate com $merge, remove quem saiu, grava job_runs)
  cenario.py                a consulta do passo 4: Filtro, consultar -> _da_base ou _sob_demanda (raw, com $merge opcional); defasagem_dias/aviso_defasagem (base de outro dia)
  ingestao.py               ingestão simulada: fila ingestao_simulada -> trecho_observacoes ($merge)
  previa.py                 prévia do próximo job (só leitura: o que entra, o que sai)
  janela.py                 datas: janela padrão, fuso São Paulo, faixas manhã/tarde/noite, período relativo
  pipelines/
    job.py                  pipeline do job (match, set, group, project, merge em trecho_media_dow_hora) e janela_no_servidor (janela calculada pelo MongoDB, usada pela Function)
    cenario.py              pipelines da consulta: base() e raw() (com $merge em consultas_salvas)
    ingestao.py             pipeline da ingestão (merge em trecho_observacoes)
    __init__.py             Estagio (estágio + comentário) e estagios()/comentados()
  operadores.py, mongosh.py gaveta "Ver query": explica operadores e converte o pipeline em texto mongosh
  colecoes.py               descrição escrita à mão das 7 collections (passo 1)
  schemas.py                $jsonSchema (validators) e tipos de veículo
  bootstrap.py              cria collections, validators e índices (idempotente)
  seed.py, gerador.py       recria a demo e gera dados sintéticos determinísticos
backend/jobs/
  materializar.py           CLI do job diário (python -m backend.jobs.materializar [--data] [--db])
atlas-trigger/              app do Atlas App Services (appservices CLI): o job de verdade em produção
  functions/rodarJob.js     Function do job diário (GERADA a partir de backend/frota/pipelines/job.py; não editar à mão)
  functions/ingerirSimulado.js  Function da ingestão (GERADA)
  triggers/jobDiario.json   Scheduled Trigger, cron 10 6 * * * UTC (03:10 em São Paulo)
  triggers/ingestaoSimulada.json  cron 5 * * * * (todo minuto 5)
  data_sources/, root_config.json, README.md
frontend/src/
  App.jsx                   trilho de 5 passos, rodapé (frescor da base, Resetar demo), hash #passo=N
  api.js                    get/post com mensagem amigável de erro
  passos/                   uma tela por passo: Colecoes, Regra, GerarBase, Consultar, QuandoAtualiza
  comp/                     MapaFluxo (SVG do fluxo), GavetaQuery, FiltroCenario, Resultado, Selo, ResetDemo
  fmt.js                    formatação de números e datas
scripts/                    seed.py, bootstrap_db.py, ingerir.py, export_pipelines.py (gera os .js e docs/pipelines), trigger_deploy.sh, limpar_atlas.py, ui_smoke.py, capturar_prints.py, bench_escala.py (raw 1×/2×/4× e time series)
tests/                      pytest contra o banco *_test; tests/js/rodar_function.js roda a Function no node; tests/js/rodar_function_mongosh.js + test_live_trigger.py rodam a Function de verdade no *_test
docs/                       adr/, briefing/, pipelines/ (exportados), consultas.md, decisoes-cliente.md, roteiro-demo.md, visao-tecnica.md
Makefile, start.sh, docker-compose.yml   atalhos de execução; Mongo local na porta 27027
```

## 2. "Apertei o botão X, o que roda?"

Todo clique passa por `frontend/src/api.js` (`get`/`post`); o Vite encaminha `/api` ao 8410 (`frontend/vite.config.js`).

| Tela / botão | Componente (arquivo:linha) | Chamada HTTP | Handler | Função de negócio | Onde toca o MongoDB |
|---|---|---|---|---|---|
| Abrir a página (alvo, frescor da base) | `App.jsx:52` | `GET /api/estado` | `backend/api/main.py:121` `estado` | `backend/frota/ingestao.py::simulado_ate` | `backend/api/main.py::estado` (`job_runs.find_one` x2, :127-128; `cenario.defasagem_dias` :135); `ingestao.py::simulado_ate` (`$group $max`, `ingestao_simulada`) |
| Abrir a página (listas de trecho/veículo) | `App.jsx:52` | `GET /api/opcoes` | `backend/api/main.py:178` `opcoes` | `_trechos` (:144), `_veiculos` (:154) -> `cenario.py::veiculos_por_tipo` (:122) | `pontos.find`, `trechos.find` (:145-151); `$group` tipo×veículo na raw (`cenario.py:124`), `trecho_observacoes` |
| Passo 1, Collections e schema | `passos/Colecoes.jsx:75` | `GET /api/colecoes` | `backend/api/main.py:205` `colecoes` | `_info_colecoes` (:187), `backend/frota/colecoes.py::COLECOES`, `ingestao.bloco` | `listCollections`, `list_indexes`, `estimated_document_count` (:187-201), todas as collections |
| Passo 2, A regra | `passos/Regra.jsx` | nenhuma (usa `estado` já carregado) | n/a | n/a | n/a |
| Banner "A base foi gerada para … há N dias" (todos os passos) | `App.jsx:148` | nenhuma (usa `estado.baseDefasadaDias`) | `backend/api/main.py::estado` | `backend/frota/cenario.py::defasagem_dias` | `job_runs.find_one` (último ok) |
| Passo 3, "Rodar job agora" | `passos/GerarBase.jsx:50` `rodar`, botão :67 | `POST /api/job` | `backend/api/main.py:242` `job` | `backend/frota/job.py::rodar_job` (:27) | `count_documents` + `aggregate` com `$merge` em `trecho_observacoes` -> `trecho_media_dow_hora`; `delete_many` dos antigos; `insert_one` em `job_runs` |
| Passo 3, "Ver script do trigger" (gaveta) | `passos/GerarBase.jsx:13` | `GET /api/trigger-script` | `backend/api/main.py:229` `trigger_script` | lê arquivos de `atlas-trigger/` | não |
| Passo 4, mudança de filtro com janela padrão e sem veículo (consulta automática, 300 ms) | `comp/FiltroCenario.jsx:37` `useConsultaAuto` (post em :46); usado em `passos/Consultar.jsx:48` | `POST /api/cenario` | `backend/api/main.py:251` `cenario_api` | `backend/frota/cenario.py::consultar` (:311) -> `_da_base` (:217) | `aggregate` em `trecho_media_dow_hora` (`cenario.py:224`), `job_runs.find_one` (:190; o mesmo run alimenta `aviso_defasagem`, :233) |
| Passo 4, "Calcular" (veículo específico, datas, últimos N dias) | `passos/Consultar.jsx:50` `calcular`, botão :95 | `POST /api/cenario` | idem | `cenario.py::consultar` -> `_sob_demanda` (:253) | `consultas_salvas.find_one` (:275), `aggregate` na raw `trecho_observacoes` (:284) com `$merge` em `consultas_salvas` se "guardar o resultado" marcado, `count_documents` de docs lidos (:295, :300) |
| Passo 4, chips de dia, faixa e atalhos Manhã/Tarde/Noite | `comp/FiltroCenario.jsx:97-98` (dia), `:115-117` (atalho) | só mudam o filtro; a chamada é a de cima | idem | `backend/frota/janela.py::ATALHOS` (:17), `horas_da_faixa` (:37) | idem |
| Passo 5, Quando atualiza | `passos/QuandoAtualiza.jsx:15` | `GET /api/job_runs?limite=5` e `GET /api/proximo-job` | `backend/api/main.py:269` `job_runs`; `:264` `proximo_job` | `backend/frota/previa.py::proximo` (:40) | `job_runs.find().sort`; `count_documents` na raw e `$group` das chaves (`previa.py:24-50`) |
| Passo 5, "Ir ao passo 3" | `passos/QuandoAtualiza.jsx:36` | nenhuma | n/a | n/a | n/a |
| Rodapé, "Resetar demo" (confirma no diálogo) | `comp/ResetDemo.jsx:32`, confirma :43 -> `App.jsx:87` `iniciarReset` (`post` em :89) | `POST /api/reset` (202), depois `GET /api/reset/status` + `GET /api/estado` a cada ~1 s (`App.jsx:101-107`) | `backend/api/main.py:296` `reset`; `:308` `reset_status` | thread `_executar_reset` (:280) -> `backend/frota/seed.py::resetar` (:25) | `drop_collection`, `bootstrap`, `insert_many` (`seed.py:45`) e um `rodar_job` final |
| Copiar query (gaveta "Ver query / chamada executada") | `comp/GavetaQuery.jsx:46` | nenhuma (texto já veio na resposta, montado por `backend/frota/operadores.py::bloco_query`) | n/a | n/a | n/a |

Não há botão de ingestão simulada na UI: ela roda pelo trigger `ingestaoSimulada` ou por `make ingerir` (`scripts/ingerir.py` -> `backend/frota/ingestao.py::ingerir`).

## 3. Onde estão as queries MongoDB

Briefing: [briefing/queries.md](briefing/queries.md). Pipelines exportados em `docs/pipelines/`.

| O que faz | arquivo::função (linha) | Operador / pipeline principal | Collection(s) |
|---|---|---|---|
| Job diário: materializa a média | `backend/frota/job.py::rodar_job` (:27, aggregate em :39) com pipeline de `backend/frota/pipelines/job.py::pipeline` (:18) | `$match` -> `$set` (`$isoDayOfWeek`, `$hour`, fuso SP) -> `$group` -> `$project` -> `$merge` (replace/insert, chave `CHAVE` :15) | lê `trecho_observacoes`, grava `trecho_media_dow_hora` |
| Job: contagem lida / gravada | `job.py::rodar_job` (:38, :40) | `count_documents` | `trecho_observacoes`, `trecho_media_dow_hora` |
| Job: remove chaves que saíram da janela | `job.py::rodar_job` (:41) | `delete_many {atualizadoEm: {$lt: início do run}}` | `trecho_media_dow_hora` |
| Job: registro da execução | `job.py::rodar_job` (:44, :48) | `insert_one` (ok ou erro) | `job_runs` |
| Consulta pela base | `cenario.py::_da_base` (:217; aggregate :224) com `pipelines/cenario.py::base` (:46) | `$match` (rota, dow, hora) -> `$group` somando; com ampliação em 3 tentativas (pedido, todos os dias, dia inteiro) | `trecho_media_dow_hora` |
| Consulta sob demanda (raw) | `cenario.py::_sob_demanda` (:253; aggregate :284) com `pipelines/cenario.py::raw` (:63) | `$match` por rota/período -> `$set` -> `$match` dow/hora -> `$group`; `$merge` opcional (`pipelines/cenario.py:100`) | lê `trecho_observacoes` |
| Consulta: salvo ainda válido | `cenario.py::_sob_demanda` (:275), releitura após `$merge` (:288) | `find_one {_id, expiraEm > agora}` | `consultas_salvas` (TTL por `expiraEm`) |
| Docs lidos / examinados | `cenario.py::_sob_demanda` (:295, :300) | `count_documents` | `trecho_observacoes` |
| Veículos por tipo | `cenario.py::veiculos_por_tipo` (:122, aggregate :124) | `$group` por tipo e veículo | `trecho_observacoes` |
| Último job ok | `cenario.py::_gerado_por` (:188, :190), `backend/api/main.py::estado` (:127), `_veiculos` (:155) | `find_one` ordenado por `iniciadoEm` | `job_runs` |
| Trechos e nomes de ponto | `backend/api/main.py::_trechos` (:144-151) | `find` | `pontos`, `trechos` |
| Schema e índices reais | `backend/api/main.py::_info_colecoes` (:187) | `listCollections`, `list_indexes`, `estimated_document_count` | todas |
| Execuções recentes | `backend/api/main.py::job_runs` (:269) | `find().sort(iniciadoEm -1).limit` | `job_runs` |
| Prévia do próximo job | `backend/frota/previa.py::proximo` (:40), `_chaves_na_raw` (:24), `_chaves_que_somem` (:32) | `count_documents`, `$group` de chaves | `trecho_observacoes`, `trecho_media_dow_hora`, `job_runs` |
| Ingestão simulada | `backend/frota/ingestao.py::ingerir` (:31) com `pipelines/ingestao.py::pipeline` (:22; `$merge` :36) | `find` dos pendentes, aggregate `$match _id $in` -> `$project` -> `$merge` em `trecho_observacoes`, depois `delete_many` na fila | `ingestao_simulada` -> `trecho_observacoes` |
| Até onde vai a simulação | `ingestao.py::simulado_ate` (:17) | `$group` com `$max` | `ingestao_simulada` |
| Índices, validators, TTL | `backend/frota/bootstrap.py::indices` (:17), `bootstrap` (:51; `collMod` :61, :74, `create_indexes` :77) | índices únicos, TTL de 200 dias na raw, TTL em `consultas_salvas` | todas |
| Reset / seed | `backend/frota/seed.py::resetar` (:25; `drop_collection`, `insert_many` :45) | apagar, recriar, inserir em lotes | todas |
| Teste de saúde | `backend/api/main.py::ready` (:112) | `ping` | admin |
| As mesmas chamadas, no Atlas | `atlas-trigger/functions/rodarJob.js`, `ingerirSimulado.js` | mesmo pipeline, em JavaScript | idem |

Não há `$search` nem `$vectorSearch`; não há change stream.

## 4. Compartilhado × só desta PoV

- **`_shared`:** nenhum. Não há import de `_shared` no código (conferido com rg). Não há LLM, Voyage nem Langfuse.
- **Variáveis de ambiente** (`.env.example`, lidas em `backend/frota/settings.py`):
  - Comum do portfólio: `MONGODB_URI` (vem do `.env.shared` via `sync_env.py`, conforme comentário do `.env.example`); `ATLAS_PROJECT_ID`, `ATLAS_CLUSTER_NAME` (usadas por `scripts/trigger_deploy.sh`).
  - Locais: `MONGODB_URI_LOCAL` (Mongo do docker, porta 27027), `FROTA_MONGO` (`auto`/`atlas`/`local`), `MONGODB_DB` (padrão `frota_eta`), `MONGODB_TEST_DB` (`frota_eta_test`), `BACKEND_PORT`, `FRONTEND_PORT`, `SEED`, `APPSERVICES_APP_ID` (só indica que o trigger foi implantado).
  - `ALLOW_DEMO_DB_WRITE=1` libera recriar o banco da demo (`backend/frota/db.py::guardar_escrita`); o `make seed` já passa.
- **Banco/coleções:** `frota_eta` com 7 collections (`trecho_observacoes`, `trecho_media_dow_hora`, `consultas_salvas`, `trechos`, `pontos`, `job_runs`, `ingestao_simulada`), todas exclusivas desta PoV. Testes usam `frota_eta_test`.
- **Chamadas externas:** só MongoDB (Atlas ou o docker local). Para implantar o trigger, `scripts/trigger_deploy.sh` usa o `appservices` CLI.

## 5. "Quero mexer em..."

- Texto ou título de um passo -> `PASSOS` em `frontend/src/App.jsx:12`.
- Aparência/layout de uma tela -> `frontend/src/passos/<Passo>.jsx` e `frontend/src/index.css`.
- Mapa do fluxo (nós, ordem acesa por passo) -> `frontend/src/comp/MapaFluxo.jsx`.
- Janela de 180 dias, mínimo de amostras, horário do job, retenções -> `backend/frota/settings.py` (constantes no topo).
- Pipeline do job diário -> `backend/frota/pipelines/job.py`; depois rode `make pipelines` para regenerar `atlas-trigger/functions/*.js` e `docs/pipelines/`.
- Lógica da consulta (base × raw, ampliação, salvo) -> `backend/frota/cenario.py` e `backend/frota/pipelines/cenario.py`.
- Adicionar rota -> `backend/api/main.py`, seguindo o padrão de `@app.get("/api/...")`.
- Índices ou validators -> `backend/frota/bootstrap.py::indices` e `backend/frota/schemas.py`.
- Dados do seed (trechos, perfis, outliers, semente) -> `backend/frota/gerador.py`, `SEED` no `.env`.
- Horário do trigger -> `atlas-trigger/triggers/jobDiario.json` e `CRON_JOB_UTC` em `settings.py` (devem andar juntos).
- Explicação dos operadores na gaveta -> `backend/frota/operadores.py` e `backend/frota/mongosh.py`.
- Descrição de cada collection/campo (passo 1) -> `backend/frota/colecoes.py`.
- Portas -> `.env` (`BACKEND_PORT`, `FRONTEND_PORT`), `frontend/vite.config.js`, `Makefile` (`api`), `start.sh`.

## 6. Testes

Comando (Makefile/README): `make test` (equivale a `.venv/bin/python -m pytest -q tests`), contra o banco `frota_eta_test`; configurado em `pytest.ini`. Rodam no cluster ou Mongo local, não são mockados.

- `tests/conftest.py` — fixtures: banco `*_test`, validators, índices, esvazia collections por teste.
- `tests/test_job.py` — job: dia de hoje excluído, idempotência, dois runs sobrepostos, remoção de chave que saiu, `$isoDayOfWeek` na meia-noite local.
- `tests/test_cenario.py` — consulta pela base, sob demanda, salvo e ampliação.
- `tests/test_janela.py` — janela meio-aberta, fuso de São Paulo, faixas que cruzam a meia-noite, períodos, próximo job.
- `tests/test_api.py` — rotas da API sobre o banco de teste.
- `tests/test_ingestao.py` — ingestão simulada e prévia.
- `tests/test_previa.py` — prévia do próximo job (só leitura).
- `tests/test_operadores.py` — explicação de operadores e bloco de query.
- `tests/test_bootstrap.py`, `tests/test_seed.py` — índices/validators e gerador determinístico.
- `tests/test_trigger_export.py` — Functions do trigger equivalem aos pipelines Python (usa `tests/js/rodar_function.js`).
- `tests/test_limpar_atlas.py` — script de limpeza.
