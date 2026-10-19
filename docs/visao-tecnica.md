# Visão técnica — agregados em janela móvel (fallback de ETA)

Versão 2.0.0. Extraído do código em `frota/`, `api/`, `jobs/` e `atlas-trigger/`. Os
exemplos de documento vêm do banco `frota_eta` depois de um reset (dados sintéticos).

## O problema

O ETA online calcula com trânsito em tempo real. Quando esse serviço cai, a aplicação
precisa de uma **média histórica pronta** por trecho (origem → destino), tipo de veículo e
período ("toda sexta à tarde"), sem calcular nada na hora. A média usa **D-1 a D-180**: o
dia de hoje ainda não terminou e fica de fora. O resultado é recalculado uma vez por dia,
o equivalente a uma materialized view do Oracle com refresh agendado.

## Desenho

```
trecho_observacoes ──(job diário: $match janela → $isoDayOfWeek/$hour → $group → $merge replace)──▶ trecho_media_dow_hora
trecho_media_dow_hora ──($match chave + dow ∈ dias + hora ∈ faixa → $group)──▶ resposta "Job diário"
trecho_observacoes ──(outro período: mesmo cálculo; opcional $merge)──▶ consultas_salvas ──▶ resposta "Sob demanda"
ingestao_simulada ──(de hora em hora: $merge por viagemId + seq)──▶ trecho_observacoes   (só na demo)
```

- **Grão da base:** origem × destino × tipoVeiculo × dia da semana ISO × hora. São no
  máximo 7 × 24 = 168 documentos por trecho e veículo. Qualquer combinação de dias e faixa
  de horas é uma soma desses documentos; manhã, tarde e noite viram atalhos de faixa
  (06–12, 12–18, 18–06), não parte da chave.
- **Janela padrão:** `[início do dia (dataRef − 180), início do dia dataRef)` em
  `America/Sao_Paulo`, calculada em Python com `zoneinfo` (a subtração de dias é feita no
  calendário local) e enviada pronta ao pipeline. Limite superior sempre `$lt`.
- **`dataRef` e `agora` são parâmetros** de toda função de janela, ingestão e validade.
  `datetime.now()` só nos entrypoints (API, CLI); `$$NOW` só em `atualizadoEm` e
  `criadoEm`. Não há relógio simulado: o seed gera dados em torno da data real.
- **Dia da semana:** `$isoDayOfWeek` (1 = segunda … 7 = domingo) e `$hour`, ambos com
  `timezone`. A UI mostra os nomes dos dias.
- **Somas, não médias:** cada documento guarda `n`, `somaMin`, `somaQuadMin` e `somaKm`
  (arredondadas a 6 casas). Média = soma / n; desvio-padrão populacional =
  √(somaQuad / n − média²). É isso que permite somar horas e dias diferentes.

## Equivalente a uma materialized view do Oracle

| | Oracle MV | Esta POV |
|---|---|---|
| Resultado materializado | segmento da MV | collection `trecho_media_dow_hora` |
| Quem atualiza | `DBMS_MVIEW.REFRESH` / scheduler | job diário (Atlas Scheduled Trigger em produção; botão do passo 3 na demo) |
| Janela relativa a hoje | `SYSDATE` torna a MV inelegível para fast refresh: refresh COMPLETE agendado | `dataRef` é parâmetro; os limites chegam prontos |
| Refresh | COMPLETE | `$group` da janela + `$merge` replace, idempotente |
| Objeto novo no banco | tabela/MV com aprovação de DDL | collections no MongoDB que já faz parte da solução |

`$merge` grava o resultado; quem atualiza é o job, não o banco. A comparação é de
arquitetura, não de desempenho: o Oracle não foi medido.

## Modelo de dados (referência)

Banco `frota_eta`. Datas sempre **BSON Date UTC**. Toda collection é criada com
`$jsonSchema` (`validationLevel: strict`, `validationAction: error`) pelo bootstrap
idempotente (`frota/bootstrap.py`, `scripts/bootstrap_db.py`), que também remove índices
fora do contrato. **É um modelo de referência: adapte ao cadastro mestre real** (códigos
de pontos, tipos de veículo, identidade da viagem).

**`trecho_observacoes`** (raw, uma observação por trecho percorrido). `observadoEm` é a
**partida** do trecho e define dia e hora.
```js
{ origem: "POSTO-31", destino: "POSTO-32", tipoVeiculo: "TRUCK", veiculoId: "VEI-TRUCK-3",
  viagemId: "VIA-20261019-001499", seq: 1, observadoEm: ISODate("2026-10-19T15:40:39Z"),
  distanciaKm: 42.17, tempoMin: 46.66 }
```

**`trecho_media_dow_hora`** (a base pronta).
```js
{ origem: "BASE-001", destino: "POSTO-11", tipoVeiculo: "CARRETA", dow: 5, hora: 17,
  n: 78, somaMin: 8628.97, somaQuadMin: 987874.9181, somaKm: 4246.99,
  mediaMin: 110.6278205128205, mediaKm: 54.44858974358974,
  janelaInicio: ISODate("2026-04-22T03:00:00Z"), janelaFim: ISODate("2026-10-19T03:00:00Z"),
  dataRef: "2026-10-19", runId: "2026-10-19T15:42:11Z-6952",
  atualizadoEm: ISODate("2026-10-19T15:42:12.220Z") }
```

**`consultas_salvas`** (resultado sob demanda guardado). `_id` = sha1 do filtro
normalizado (rota, tipo, dias, horas e período resolvido: datas absolutas, ou "últimos N
dias" + `dataRef`, de modo que o relativo muda de chave quando o dia vira). Campos:
`filtro`, `n`, `somaMin`, `somaQuadMin`, `somaKm`, `periodo` (`absoluto`|`relativo`),
`criadoEm`, `expiraEm`.

**`job_runs`** (histórico do job): `_id` = `runId`, `origem` (`trigger`, `botao`, `cli`,
`reset`), `dataRef`, `iniciadoEm`, `status`, `janelaInicio`, `janelaFim`, `lidos`,
`gravados`, `removidos`, `ms` e, em falha, `erro` mascarado (sem host).
```js
{ _id: "2026-10-19T15:42:11Z-6952", origem: "reset", dataRef: "2026-10-19", status: "ok",
  lidos: 312164, gravados: 8834, removidos: 0, ms: 5808.1, ... }
```

**`pontos`** e **`trechos`** (só para os selects). A chave do ponto é um código estável,
nunca coordenada GPS bruta.
```js
{ _id: "BASE-001", tipo: "base", nome: "Base Paulínia", cidade: "Paulínia", uf: "SP",
  location: { type: "Point", coordinates: [ -47.15, -22.76 ] } }
{ _id: "BASE-001|POSTO-11", origem: "BASE-001", destino: "POSTO-11",
  distanciaBaseKm: 54.7, tempoBaseMin: 59.7, esparso: false }
```

**`ingestao_simulada`** — **só da demo**, simula a chegada de dados e não faz parte do
modelo. Mesmo schema da raw; guarda as observações dos próximos 14 dias geradas no reset.

### Índices e por que cada um existe

| Collection | Índice | Por quê |
|---|---|---|
| `trecho_observacoes` | `{viagemId, seq}` único | identidade da observação: reenvio do mesmo trecho da mesma viagem não duplica (e é o `on` do `$merge` da ingestão) |
| | `{origem, destino, tipoVeiculo, observadoEm}` | cenários fora da janela padrão: rota + período direto na raw |
| | `{observadoEm}` TTL 200 dias | range do job diário e retenção |
| `trecho_media_dow_hora` | `{origem, destino, tipoVeiculo, dow, hora}` único (`chave_unica`) | exigido pelo `on` do `$merge` e serve à leitura dos cenários |
| `consultas_salvas` | `{expiraEm}` TTL 0 | o próprio banco apaga o salvo quando passa da validade |
| `job_runs` | `{iniciadoEm: -1}` | últimas execuções |
| `trechos` | `{origem, destino}` único | um par válido por trecho |
| `ingestao_simulada` | `{viagemId, seq}` único, `{observadoEm}` | fila da simulação: dedup e "o que já aconteceu" |

### Retenção

A raw fica **200 dias** (TTL): cobre a janela de 180 dias com margem e permite consultas
sob demanda em períodos um pouco mais antigos. Período anterior à retenção responde "sem
dados brutos para esse período" (e o bloco mostrado não traz `$merge`, porque nada roda);
período que só começa antes dela é calculado com o que há e avisa "parte do período não
tem mais dados brutos". O salvo sob demanda vive 1–30 dias (padrão 7) se o período é
absoluto e até o próximo job se é relativo ou se termina hoje (ainda está crescendo). Leituras filtram `expiraEm > agora`,
porque o monitor de TTL roda a cada ~60 s.

## Pipelines

Os builders ficam em `frota/pipelines/` (listas de `Estagio(comentario, estagio)`); a UI,
`docs/pipelines/` e as Functions do trigger recebem exatamente o que o driver recebe.
`make pipelines` regenera `docs/pipelines/*.js|json` e `atlas-trigger/functions/*.js`.

| Pipeline | Collection | Forma |
|---|---|---|
| Job diário | `trecho_observacoes` | `$match observadoEm [início, fim)` → `$set dow/hora` (`$isoDayOfWeek`, `$hour`, tz) → `$group` por o/d/tipo/dow/hora (`n`, somas) → `$project` (somas `$round` 6, médias, janela, `dataRef`, `runId`, `atualizadoEm: $$NOW`) → `$merge` em `trecho_media_dow_hora` on a chave única, `replace`/`insert`; depois `deleteMany({atualizadoEm < inícioDoRun})` |
| Cenário na base | `trecho_media_dow_hora` | `$match {o, d, tipo, dow $in, hora $in}` → `$group` somando `n` e somas, `docs: $sum 1` |
| Cenário sob demanda (outro período ou um veículo) | `trecho_observacoes` | `$match o/d/tipo (+ veiculoId) + observadoEm [início, fim)` → `$set dow/hora` → `$match dow/hora` → `$group` → `$project`; se guardar, `$merge` em `consultas_salvas` on `_id`, `replace` |
| Ingestão simulada | `ingestao_simulada` | `$match _id $in [escolhidos]` → `$project {_id: 0}` → `$merge` em `trecho_observacoes` on `{viagemId, seq}`, `replace`; depois `deleteMany` só dos escolhidos |

### Por que o job é idempotente e seguro em paralelo

`$merge` com `whenMatched: "replace"` recalcula a chave inteira a cada run (nunca `$inc`),
então rodar duas vezes dá o mesmo resultado. O `inícioDoRun` é lido do relógio do
**servidor** (`hello.localTime`) antes do `aggregate`; a limpeza apaga só o que tem
`atualizadoEm` anterior a ele. Dois runs sobrepostos (trigger + botão) não apagam o
resultado um do outro, e uma chave que saiu da janela é removida pelo run mais novo. Não há
lease nem lock em banco.

### Ampliação por poucas amostras (proposta para validação)

Só na base pronta, com mínimo de 5 amostras (`MIN_AMOSTRAS`): dias e horas pedidos →
todos os dias da semana nas mesmas horas → dia inteiro nos dias pedidos → sem histórico.
A resposta diz qual nível usou. O sob demanda não amplia: o período foi escolhido de
propósito e o `n` aparece como veio.

### Bloco `query` em toda resposta

Toda rota que executa algo devolve `query`: `{le, grava, operacao, mongosh, operadores:
[{op, explicacao}]}` (`frota/operadores.py`), e as respostas da base trazem também
`geradoPor` (o pipeline do último job com status `ok`, com a janela e o `runId` dele). É o
que a gaveta "Ver query / chamada executada" mostra.

`/api/cenario` também devolve `origem`: `base` (base pronta), `raw` (calculado agora; com
`expiraEm` preenchido, o resultado foi gravado em `consultas_salvas`) ou `salvo` (lido de
`consultas_salvas`). O mapa do fluxo do passo 4 acende o ramo por esse campo.

`docsLidos` é a prova de custo: na base, quantos documentos prontos foram somados; na raw,
quantos documentos passaram pelo primeiro `$match` (rota + período), antes do filtro de dia
e hora (as `amostras` são o `n` que sobra). O tempo exibido é medido no app e no Atlas é
quase todo ida e volta de rede, por isso a UI o chama de "ida e volta ao banco".

## Agendamento (Atlas Scheduled Triggers)

App App Services `frota-eta-job` em `atlas-trigger/`, com dois Scheduled Triggers:
`jobDiario` (cron UTC `10 6 * * *` = 03:10 em São Paulo) e `ingestaoSimulada` (`5 * * * *`).
A Function do job calcula `dataRef` = hoje em São Paulo com deslocamento fixo de −3 h (sem
horário de verão desde 2019), roda o mesmo pipeline e grava `job_runs` com origem
`trigger`. `tests/test_trigger_export.py` garante que o template é igual ao pipeline Python
e roda as Functions no node com `context` falso.

**Na demo os triggers não estão implantados**: o deploy exige chave com Project Owner no
projeto do cluster. O passo 5 mostra o agendamento planejado e informa que o job roda pelo
botão do passo 3. Implantação: `make trigger-deploy` (ver `atlas-trigger/README.md`).

## Compatibilidade de operadores

Executado e testado (107 testes) em **MongoDB 8.0.34** (Docker, replica set de 1 nó) e
**MongoDB 9.0.4** (Atlas). As versões mínimas são as da documentação.

| Operador / recurso | Uso | Disponível desde |
|---|---|---|
| `$isoDayOfWeek`, `$hour` com `timezone` | dia da semana ISO e hora local | 3.6 |
| `$merge` em collection existente, `on` com índice único | job, ingestão, salvo sob demanda | 4.2 |
| `$round` | somas com 6 casas | 4.2 |
| `$jsonSchema` validator | todas as collections | 3.6 |
| TTL index | raw (200 dias), salvo (`expiraEm`) | — |

O validator usa `$jsonSchema` draft 4, em que `exclusiveMinimum` é booleano.

## Como rodar

```bash
make up        # MongoDB local (se for o alvo) + collections, validators e índices
make seed      # recria frota_eta em torno de agora e roda o job (ALLOW_DEMO_DB_WRITE=1)
./start.sh     # API 127.0.0.1:8410 + UI 127.0.0.1:5410
make test      # pytest no alvo (banco frota_eta_test)
```

Outros alvos: `make job [DATA=AAAA-MM-DD]`, `make ingerir`, `make pipelines`,
`make trigger-deploy`, `make limpar-atlas [CONFIRMAR=1]` (dropa só os bancos da allowlist
exata `frota_eta_bench` e `frota_eta_*_test`; `frota_eta` nunca é dropado, só perde as
collections fora do schema v2, sobras da v1; sem `CONFIRMAR=1` apenas lista). Alvo: Atlas se `MONGODB_URI` estiver preenchida, senão Docker
local (27027); `FROTA_MONGO=local` força o local.

## Integração com o portfólio

- **Portal** (`pov-portfolio/povs.json`): `rolling-aggregates`, portas 5410/8410,
  `bash start.sh` (contrato do launcher: primeiro plano, derruba a árvore no SIGTERM).
- **Portas**: reservadas em `PoVs/PORTS.md` (5410/8410 e 27027 do Docker local).
- **Player**: a réplica offline `rolling` do `pov-demo-player` foi gravada da API 1.0.1 e
  está **obsoleta**; precisa ser regravada para a v2.

## Limitações

- Testado num cluster Atlas compartilhado e no MongoDB 8.0 local; nada com sharding nem
  com o volume real do cliente (a demo tem ~836 mil observações em 60 trechos).
- Média simples e desvio populacional, outliers incluídos. `$median`/`$percentile` não se
  compõem entre horas a partir de soma e contagem.
- Triggers com código pronto e testado fora do Atlas, mas não implantados.
- A Function usa UTC−3 fixo; se o horário de verão voltar, revisar a constante e o cron.
