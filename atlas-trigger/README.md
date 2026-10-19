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
`frota/pipelines/`. O gerador chama o builder com marcadores (`"__INICIO__"`, `"__FIM__"`,
`"__DATA_REF__"`, `"__RUN_ID__"`, `"__IDS__"`, `"__AGORA__"`) e a Function só troca cada
marcador pelo valor da execução. `tests/test_trigger_export.py` garante que o template
substituído é igual ao pipeline do Python, que os `.js` versionados estão atualizados e que
a Function, executada no node com um `context` falso, faz as mesmas chamadas que
`frota/job.py` e `frota/ingestao.py`. Não edite os `.js` à mão.

## Fuso fixo de −3 h

A Function calcula a data local somando `OFFSET_SP_HORAS = -3` ao instante UTC. São Paulo
não tem horário de verão desde 2019, então o fuso é UTC−3 o ano todo e a janela fica
`[00:00 local de (hoje − 180), 00:00 local de hoje)`, como `frota/janela.py::janela_padrao`.
O Python usa `America/Sao_Paulo` (zoneinfo); se o horário de verão voltar, revise a
constante e o cron.

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
