# ADR 0001 — A Function do trigger pede a janela ao MongoDB (sem offset fixo)

- Data: 2026-11-12
- Status: aceito

## Contexto

O job diário roda no Python (botão, CLI, reset) e, em produção, numa Function de Atlas
Scheduled Trigger gerada a partir dos mesmos builders (`scripts/export_pipelines.py`). O
Python calcula a janela `[00:00 local de (hoje − 180), 00:00 local de hoje)` com `zoneinfo`
(`backend/frota/janela.py::janela_padrao`). A Function fazia a mesma conta somando
`OFFSET_SP_HORAS = -3` ao UTC. Isso só vale enquanto São Paulo não tiver horário de verão.
O runtime das Functions não garante a base de fusos do `Intl`.

## Decisão

A Function não calcula data local. Ela manda ao servidor o instante `agora` e recebe, numa
ida só, `inicio`, `fim`, `dataRef` e o relógio do cluster (`$$NOW`, usado como corte da
limpeza, como o `hello.localTime` do Python). O pipeline vem de
`backend/frota/pipelines/job.py::janela_no_servidor`:

- `fim` = `$dateTrunc {unit: "day", timezone: "America/Sao_Paulo"}` de `agora`;
- `inicio` = `$dateTrunc` (de novo) de `$dateSubtract {unit: "day", amount: 180, timezone}`
  de `fim`;
- `dataRef` = `$dateToString {format: "%Y-%m-%d", timezone}` de `agora`;
- `$match {$expr: false}` + `$unionWith {pipeline: [{$documents: [{}]}]}` garantem um único
  documento mesmo com a collection vazia (`$documents` dentro de `$unionWith`: 6.0+).

O segundo `$dateTrunc` é necessário. No dia em que o horário de verão começava (ex.:
15/10/2017), o 00:00 não existe e o dia local começa à 01:00. Subtrair 180 dias mantinha
a 01:00 e o início ficava 1 h depois do Python. Medido: sem ele, 10 de 7.665 instantes
(2017–2019) divergiam; com ele, 0 de 30.681 (2008–2019).

## Consequências

- Se o horário de verão voltar, a janela continua certa sem mudar código. O cron UTC
  `10 6 * * *` passaria a disparar às 04:10 locais, ainda depois da meia-noite, então o
  resultado é o mesmo.
- A janela depende da base de fusos do servidor (tzdata do `mongod`), que é atualizada
  com o MongoDB.
- Uma ida a mais ao servidor no início da Function, que já existia para ler o relógio.
- Prova: `tests/test_live_trigger.py` compara a janela do servidor com `janela_padrao` em
  viradas de horário de verão e roda o `rodarJob.js` versionado pelo mongosh contra o banco
  `*_test`, exigindo a mesma base do job Python. `tests/test_trigger_export.py` continua
  conferindo o JS gerado e a sequência de chamadas no node.
- O deploy do App Services continua pendente (chave Project Owner). A Function deixou de ser
  só "testada no node": ela roda num MongoDB real.
