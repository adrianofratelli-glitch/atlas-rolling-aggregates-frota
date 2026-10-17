# Roteiro de demo (~10 min)

Antes: `make up && make seed PROFILE=small && make job`, depois `./start.sh` (ou `make api`
com a UI compilada em `make ui-build`). Abra http://127.0.0.1:5410. A UI mostra no topo o
volume de cada camada (raw → buckets → média), lido do banco.

| min | Etapa | O que fazer | O que dizer |
|---|---|---|---|
| 0–1 | **Problema** | Herói da página. | O ETA online calcula com trânsito em tempo real; quando ele cai, a aplicação precisa de uma média histórica pronta por trecho, veículo e período do dia — sem calcular nada na hora. No Oracle, isso seria uma materialized view. |
| 1–2 | **Raw** | Aba *Por baixo do capô* → tabela de collections: `trecho_observacoes` com `$jsonSchema strict`, TTL 200 d e os 3 índices. | Uma observação por trecho percorrido. Data é BSON Date UTC; o validator recusa string. |
| 2–4 | **Job (simples)** | Aba *Job e janela*: rodar com o asOf atual. Abrir "Ver query / chamada executada · simples". | Um pipeline: recorta a janela `[início, fim)` no fuso local, deriva turno e dia da semana, agrupa por `{origem, destino, tipoVeiculo, dow, turno}` — chave sem data — e troca a collection com `$out`. "Toda sexta à noite" é `{dow: 6, turno: "N"}`. O `$out` não roda sozinho: o job é que recalcula. |
| 4–5 | **Simples × Incremental** | Aba *Simples × Incremental*: rodar os dois desenhos. | Mesmo agregado nos dois. O incremental (buckets por turno com `$merge` de k dias) é a opção para raw de retenção curta ou volume maior; os tempos medidos estão no bloco do benchmark. |
| 5–6 | **Consulta rápida** | Aba *Consulta ETA*: mostrar a grade dow × turno e a chave consultada. Aba *Raw vs Materializado* → executar com explain. | Uma leitura, ≤ 21 docs pelo índice único. Do lado da raw, o mesmo resultado custa examinar todas as observações do trecho na janela. Os números são do explain real. |
| 6–7 | **Sem dado específico** | Trocar para um trecho/veículo com poucas amostras (ou destino "sem histórico"). | A hierarquia desce: dow+turno → turno → geral → sem_historico, e diz qual nível usou. É uma proposta para validar com vocês. |
| 7–8 | **Dado atrasado** | Aba *Job e janela*: "Injetar observação atrasada em D-2", rodar o job; rodar de novo: inseridos 0. | No simples, o run seguinte relê a janela e a observação entra. No incremental, dentro de k é coberto por reprocessar a janela curta; além de k, o watermark de `ingeridoEm` detecta o dia. |
| 8–9 | **Avançar a janela** | Aba *Job e janela*: "Avançar 1 dia". | Entra o dia que era hoje, sai o D-181. As chaves que dependiam só do dia que saiu são removidas — listadas na tela. Dois modos de limpeza, com trade-offs. |
| 9–10 | **Mudar turno** | Aba *Config*: mudar N para 20–05, "Salvar e recalcular o necessário". | A tela diz o que foi relido: no simples, a raw da janela; no incremental por hora, só os buckets. Opção "só turno (M/T/N)" mostra a versão mais simples aceita (≤ 3 docs por trecho/veículo). |
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
