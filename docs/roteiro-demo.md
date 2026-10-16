# Roteiro de demo (~10 min)

Antes: `make up && make seed PROFILE=small && make job`, depois `./start.sh` (ou `make api`
com a UI compilada em `make ui-build`). Abra http://127.0.0.1:5410. A UI mostra no topo o
volume de cada camada (raw → buckets → média), lido do banco.

| min | Etapa | O que fazer | O que dizer |
|---|---|---|---|
| 0–1 | **Problema** | Herói da página. | O ETA online calcula com trânsito em tempo real; quando ele cai, a aplicação precisa de uma média histórica pronta por trecho, veículo e período do dia — sem calcular nada na hora. No Oracle, isso seria uma materialized view. |
| 1–2 | **Raw** | Aba *Por baixo do capô* → tabela de collections: `trecho_observacoes` com `$jsonSchema strict`, TTL 200 d e os 3 índices. | Uma observação por trecho percorrido. Data é BSON Date UTC; o validator recusa string. |
| 2–4 | **Job / `$merge`** | Aba *Job*: rodar com o asOf atual. Abrir "Ver pipeline da camada 1". | Camada 1 relê só D-1…D-3 (e dias com atraso detectado), agrupa por dia **local** e hora com `$dateTrunc`/`$hour` com timezone, e grava com `$merge whenMatched: "replace"`. O `$merge` não roda sozinho: o job é que recalcula. Mostrar os badges, derivados do pipeline executado. |
| 4–5 | **Buckets → média** | Abrir "Ver pipeline da camada 2". | Os buckets guardam soma e contagem (componíveis). A camada 2 recorta a janela `[início, fim)` e agrupa por `{dow, turno}` — chave sem data. "Toda sexta à noite" é `{dow: 6, turno: "N"}`. |
| 5–6 | **Consulta rápida** | Aba *Consulta ETA*: mostrar a grade dow × turno e a chave consultada. Aba *Raw vs Materializado* → executar com explain. | Uma leitura, ≤ 21 docs pelo índice único. Do lado da raw, o mesmo resultado custa examinar todas as observações do trecho na janela. Os números são do explain real. |
| 6–7 | **Sem dado específico** | Trocar para um trecho/veículo com poucas amostras (ou destino "sem histórico"). | A hierarquia desce: dow+turno → turno → geral → sem_historico, e diz qual nível usou. É uma proposta para validar com vocês. |
| 7–8 | **Dado atrasado** | Aba *Job*: "Injetar observação atrasada em D-2", rodar o job, ver o bucket D-2 08h; rodar de novo: inseridos 0. | Atraso dentro de k é coberto por reprocessar a janela curta; além de k, o watermark de `ingeridoEm` detecta e reprocessa o dia. `replace` torna o job idempotente. |
| 8–9 | **Avançar a janela** | Aba *Janela móvel*: "Avançar 1 dia". Alternar `$merge + runId` / `$out` e avançar de novo. | Entra o dia que era hoje, sai o D-181. As chaves que dependiam só do dia que saiu são removidas — listadas na tela. Dois modos de limpeza, com trade-offs. |
| 9–10 | **Mudar turno sem reprocessar** | Aba *Config*: mudar N para 20–05, salvar e rerodar só a camada 2. | Prova na tela: camada 1 não executou, 0 observações da raw lidas, runId dos buckets inalterado. A hora está no grão do bucket. |
| 10 | **Decisões pendentes** | `docs/decisoes-cliente.md`. | Turnos, regra da noite, partida vs chegada, identidade dos pontos, k, mínimo de amostras, hierarquia, retenção, média vs percentil. |

Depois da demo: `make seed PROFILE=small && make job` restaura o estado inicial.

## Perguntas prováveis

- **"É uma materialized view?"** É o mesmo resultado (collection materializada + job
  agendado). A diferença é que o refresh é incremental na camada 1; a camada 2 é um
  recálculo completo, mas sobre buckets, não sobre a raw.
- **"E se o job falhar no meio?"** Rodar de novo produz o mesmo resultado (teste
  `test_retomada_apos_falha_produz_mesmo_resultado`). O lock com lease impede dois jobs
  simultâneos; um lease vencido é retomado.
- **"Funciona no Atlas?"** Todos os operadores usados existem no Atlas com MongoDB 8.0. Esta
  POV foi testada no Atlas M30 (MongoDB 9.0.4) e no MongoDB 8.0.34 local.
