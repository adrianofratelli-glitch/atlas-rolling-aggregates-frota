# Fluxos da UI

Fonte: `frontend/src/App.jsx` e as rotas de `api/main.py`.

Painel único de filtros (origem, destino, tipo, hora, asOf) → `GET /api/eta`, que devolve
o contexto derivado (janela local, dow, turno com limites, chave consultada), o resultado
do fallback, os ≤ 21 documentos do agregado e badges.

| Aba | Ação | Rota | Resultado exibido |
|---|---|---|---|
| Consulta ETA | mudar filtros | `GET /api/eta` | média, n, docs lidos, nível usado, grade dow × turno, gaveta com o `find` e a resposta. |
| Raw vs Materializado | botão explícito | `GET /api/comparar` | duas colunas com `explain("executionStats")`: estágio vencedor, keys/docs examinados, `executionTimeMillis`, latência no cliente, veredito "mesma resposta". |
| Job / $merge | rodar job; injetar atraso D-2 | `POST /api/job`, `POST /api/atrasado`, `GET /api/buckets`, `GET /api/job_runs` | contadores por camada, dias reprocessados, atrasados (fora de k), pipelines como enviados, buckets D-3…D-1, histórico. |
| Janela móvel | avançar 1 dia; trocar modo de limpeza | `POST /api/avancar`, `POST /api/config`, `GET /api/janela` | dias nas bordas da janela (o que saiu/entrou), observações de hoje fora das médias, agregados removidos. |
| Config | editar turnos, regra da noite, mínimo | `POST /api/config` com `rerodarCamada2` | prova: camada 1 não executou, 0 observações da raw lidas, runId dos buckets inalterado. |
| Por baixo do capô | — | `GET /api/capo` | pipelines atuais em mongosh, validators e índices/TTLs lidos do banco. |

Estados: sem backend → aviso com a ação (`make api`); agregado vazio → aviso com
`make seed && make job`; lock ocupado → HTTP 409 exibido como erro.
