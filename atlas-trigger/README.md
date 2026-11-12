# atlas-trigger — Scheduled Triggers da POV

App App Services `frota-eta-job` no formato do `appservices` CLI. Tem só o que ainda é
suportado: **Functions** e **Scheduled Triggers** (sem Device Sync, Data API ou HTTPS
endpoints). As Functions rodam como sistema contra o data source `mongodb-atlas`, ligado
ao cluster de `MONGODB_URI`, e escrevem no banco da demo `frota_eta`.

| Trigger | Cron (UTC) | Horário em São Paulo | Function | O que faz |
| --- | --- | --- | --- | --- |
| `jobDiario` | `10 6 * * *` | 03:10 todo dia | `rodarJob` | job diário: raw da janela padrão → `trecho_media_dow_hora`, registra em `job_runs` (origem `trigger`) |
| `ingestaoSimulada` | `5 * * * *` | minuto 5 de toda hora | `ingerirSimulado` | move de `ingestao_simulada` para `trecho_observacoes` o que já aconteceu |

Os dois têm `skip_catchup_events: true`: se o app ficar parado, não recupera execuções perdidas.

## Mesmo pipeline do Python

`functions/rodarJob.js` e `functions/ingerirSimulado.js` são **gerados** por
`make pipelines` (`scripts/export_pipelines.py`) a partir dos builders de
`backend/frota/pipelines/`. O gerador chama o builder com marcadores (`"__INICIO__"`, `"__FIM__"`,
`"__DATA_REF__"`, `"__RUN_ID__"`, `"__IDS__"`, `"__AGORA__"`) e a Function só troca cada
marcador pelo valor da execução. `tests/test_trigger_export.py` garante que o template
substituído é igual ao pipeline do Python, que os `.js` versionados estão atualizados e que
a Function, executada no node com um `context` falso, faz as mesmas chamadas que
`backend/frota/job.py` e `backend/frota/ingestao.py`. Não edite os `.js` à mão.
O marcador `"__AGORA__"` também entra no pipeline de janela do job.

## Janela calculada no servidor (sem offset fixo)

A Function não soma offset ao UTC. Antes do job, ela manda o instante da execução ao MongoDB
e recebe, numa ida só, o 00:00 de hoje e o de 180 dias antes em `America/Sao_Paulo`
(`$dateTrunc`/`$dateSubtract` com `timezone`), o `dataRef` e o relógio do cluster. O
pipeline vem de `backend/frota/pipelines/job.py::janela_no_servidor` e dá a mesma janela
de `backend/frota/janela.py::janela_padrao`, horário de verão incluído. Se ele voltar, o cron
UTC dispara às 04:10 locais e a janela continua certa. Decisão e medição em
[`docs/adr/0001-janela-do-trigger-no-servidor.md`](../docs/adr/0001-janela-do-trigger-no-servidor.md).

## Executada num MongoDB de verdade

O deploy continua pendente, mas a Function versionada já roda contra um banco `*_test`:
`tests/js/rodar_function_mongosh.js` troca só o `context` do App Services por uma conexão do
mongosh. `tests/test_live_trigger.py` exige que o resultado seja idêntico ao job do Python:
mesmas chaves, `n`, somas e janela, mesmos `lidos`/`gravados` e a chave velha removida.

## Como implantar

Pré-requisitos: `atlas` e `appservices` CLI instalados e com sessão válida
(`appservices login`) numa chave com acesso de Project Owner ao projeto do cluster.

```bash
make trigger-deploy
```

O script `scripts/trigger_deploy.sh`:

1. lê `ATLAS_PROJECT_ID` e `ATLAS_CLUSTER_NAME` do `.env` (ou descobre pelo host de
   `MONGODB_URI` com o `atlas` CLI, sem imprimir host nem ID);
2. confere a sessão do `appservices` CLI; sem sessão ou sem permissão, **para e explica**
   (não cria credencial);
3. copia esta pasta para um diretório temporário e preenche o nome do cluster no data source
   (o arquivo versionado só tem `${ATLAS_CLUSTER_NAME}`);
4. faz `appservices push`: atualiza o app de `APPSERVICES_APP_ID` ou, na primeira vez, cria
   o app e grava o ID no `.env`.

Para conferir depois: `appservices apps describe --app <id>` lista os dois triggers e
`appservices function run --app <id> --name rodarJob` roda o job uma vez (novo documento em
`job_runs` com origem `trigger`).

Nenhum ID de projeto, de app, host ou connection string é versionado: eles ficam só no `.env`.
