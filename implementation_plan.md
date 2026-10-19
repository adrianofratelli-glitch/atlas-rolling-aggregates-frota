# Plano de implementação

Estado em 2026-10-19. Versão 2.1.0 na branch `feat/v2-simplificacao` (ainda não publicada).
A v1.0.1 (desenho simples e incremental, 6 abas) segue em `main` e nas tags v1.0.0/v1.0.1.

## Concluído (v2.0.0)

1. Schema v2 com `$jsonSchema` strict em todas as collections e bootstrap idempotente que
   remove índices fora do contrato; código e collections do desenho incremental apagados.
2. Calendário puro (`frota/janela.py`): janela semiaberta, faixas de hora, próximo job,
   períodos; `dataRef`/`agora` sempre por parâmetro.
3. Gerador com padrões por dia/hora/veículo e trechos esparsos; reset pela data do clique
   com 14 dias de chegadas simuladas.
4. Job diário dow × hora com `$merge` replace e limpeza pelo relógio do servidor.
5. Bloco `query` com operadores explicados em toda resposta.
6. Cenários na base pronta (com ampliação) e sob demanda na raw, com persistência TTL.
7. Ingestão simulada de hora em hora e prévia do próximo job.
8. Atlas Scheduled Triggers em `atlas-trigger/` (Functions geradas e testadas no node).
9. API v2 e UI de uma página com roteiro de 5 passos (Dark Stage v4, 360/768/1440 px).
   Na v2.1: passo único "Consultar" (base pronta ou raw decidido pela API), veículo
   específico sempre na raw, 15 veículos por tipo no gerador, "guardar" marcado por padrão.
10. Limpeza dos bancos antigos (Atlas e local) e alvos do Makefile.
11. Docs públicas, prints do Atlas real, portfólio e grafo.

105 testes no Atlas (9.0.4) e no MongoDB 8.0.34 local.

## Não feito / próximos passos

- Implantar os triggers (`make trigger-deploy`) com uma chave que tenha Project Owner no
  projeto do cluster. Até lá, resetar a demo na manhã da apresentação.
- Regravar a réplica `rolling` do `pov-demo-player` (a atual é da API 1.0.1).
- Limitar `expiraEm` ao próximo job quando um período absoluto salvo inclui dias recentes.
- Publicar a branch e a release 2.0.0 depois do teste do usuário.
