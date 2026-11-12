# ADR 0002 — A raw continua collection comum; volume medido em 1×, 2× e 4×

- Data: 2026-11-12
- Status: aceito

## Contexto

A tese da PoV é que a consulta de ETA lê poucos documentos prontos, qualquer que seja o
volume da raw. Até aqui, isso só tinha sido visto com ~836 mil observações. Também ficava
a pergunta de mercado: uma time series collection (5.0+, block processing no 8.0+) não
seria uma raw melhor?

## Medição

`scripts/bench_escala.py --fonte frota_eta_f2_test --fatores 1 2 4 --ts`, em 2026-11-12, no
cluster Atlas M20 compartilhado do portfólio (MongoDB 9.0.7, replica set, RTT do Mac ≈ 249 ms).
Cada fator copia a raw no servidor (mesmas datas, `viagemId` com sufixo). Tempos de consulta
saem do `explain` `executionStats` (servidor, sem rede). Foi uma execução por fator num
cluster com outras cargas: leia a tendência, não o milissegundo.

| Raw | Docs | Disco + índices | Job (`$group` + `$merge`) | Base: chaves/docs lidos | Base: ms servidor | Raw, janela de 180 d: chaves/docs | Raw: ms servidor |
|---|---|---|---|---|---|---|---|
| 1× | 836 mil | 43 + 136 MB | 17,8 s | 6 / 6 | 15 | 4.320 / 4.320 | 95 |
| 2× | 1,67 mi | 86 + 303 MB | 30,1 s | 6 / 6 | 18 | 8.640 / 8.640 | 331 |
| 4× | 3,35 mi | 174 + 655 MB | 47,3 s | 6 / 6 | 16 | 17.280 / 17.280 | 691 |

A base fica com 29.962 documentos em todos os fatores. A consulta na base lê sempre 6
chaves por IXSCAN no índice único; a mesma pergunta na raw cresce linearmente em chaves lidas (4.320 → 17.280).

Mesma raw (1×) numa time series collection (`timeField: observadoEm`,
`metaField: {origem, destino, tipoVeiculo}`, `granularity: minutes`): **13,2 MB de disco +
2,2 MB de índice**, contra 47,2 + 135,0 MB da collection comum, em 35.486 buckets.

O tempo do job da tabela acima (`rodar_job`) inclui os counts, a limpeza e o `job_runs`. Por
isso a comparação com time series é feita à parte, só com o aggregate do job
(`$match` → `$set` → `$group` → `$project` → `$merge` numa collection de rascunho), igual
nos dois lados e alternado (raw, ts, raw, ts) para a carga do cluster pesar igual
(`bench_escala.py --fatores --ts`, segunda execução no mesmo dia):

| Rodada | Raw comum | Time series |
|---|---|---|
| 1 | 13,6 s | 18,3 s |
| 2 | 44,5 s | 51,2 s |

A carga do cluster compartilhado triplicou o tempo entre as rodadas. Mesmo assim, em cada par a
time series foi 15–35% **mais lenta**: ela desempacota os buckets e precisa de um
`$replaceWith` para trazer a rota do `metaField`. O custo é ler a janela inteira de qualquer
jeito, e o block processing não compensou aqui.

## Decisão

A raw continua collection comum:

- A ingestão grava com `$merge on: [viagemId, seq]` e o índice único `{viagemId, seq}` dá a
  deduplicação de reenvios. Time series não aceita índice único nem `$merge` como destino.
- O job não fica mais rápido em time series (medido: 15–35% mais lento no mesmo aggregate).
  O ganho é de disco: ~12× menos dados + índices na raw (15 MB contra 182 MB).
- O ponto da PoV, a consulta barata, já não depende da raw: a base responde com 6 chaves
  em 1× ou 4×.

## Consequências

- No cliente, se a raw ficar grande (meses × frota inteira) e a deduplicação puder sair do
  banco (chave idempotente na origem ou no Stream Processing), vale migrar a raw para
  time series e manter o mesmo job. A base e as consultas não mudam. O sob demanda na raw
  precisaria do índice secundário em `rota` + `observadoEm` na time series, e isso não foi medido.
- O job cresce abaixo do linear (17,8 s → 30,1 s → 47,3 s: 2,7× o tempo para 4× os dados). Com volume muito maior,
  o próximo passo é incremental: reprocessar só o dia que entra e o que sai, guardando somas
  por dia, em vez de reagrupar 180 dias. Isso não foi implementado.
- Sharding não foi testado (o cluster é replica set). A chave natural seria a da base ou
  `{origem, destino}` na raw. Fica como pendência.
