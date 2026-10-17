# Fluxos da UI

Fonte: `frontend/src/App.jsx` e as rotas de `api/main.py`.

Painel único de filtros (origem, destino, tipo, hora, asOf) → `GET /api/eta`, que devolve
o contexto derivado (janela local, dow, turno com limites, chave consultada), o resultado
do fallback, os ≤ 21 documentos do agregado e badges.

| Aba | Ação | Rota | Resultado exibido |
|---|---|---|---|
| Consulta ETA | mudar filtros | `GET /api/eta` | média, n, docs lidos, nível usado, grade dow × turno, gaveta com o `find` e a resposta. |
| Raw vs Materializado | botão explícito | `GET /api/comparar` | duas colunas com `explain("executionStats")`: estágio vencedor, keys/docs examinados, `executionTimeMillis`, latência no cliente, veredito "mesma resposta". |
| Simples × Incremental | botão explícito | `POST /api/comparar-modos` | os dois desenhos sobre a mesma raw e asOf (sem gravar a config): tempo por run, raw/buckets lidos, veredito "mesmo agregado", contagens por camada e o benchmark escala do arquivo. |
| Job e janela | rodar job; injetar atraso D-2 | `POST /api/job`, `POST /api/atrasado`, `GET /api/buckets`, `GET /api/job_runs` | contadores por camada, dias reprocessados, atrasados (fora de k), pipelines como enviados, buckets D-3…D-1, histórico. |
| Job e janela (seção Janela móvel) | avançar 1 dia; trocar limpeza (só incremental) | `POST /api/avancar`, `POST /api/config`, `GET /api/janela` | dias nas bordas da janela (o que saiu/entrou), observações de hoje fora das médias, agregados removidos. |
| Config | turnos, regra da noite, mínimo, desenho (simples/incremental), grão, dia da semana na chave | `POST /api/config` com `rerodarCamada2` | o que foi relido por desenho: simples = raw da janela; incremental/turno = camada 1 refeita; incremental/hora = só buckets. |
| Por baixo do capô | — | `GET /api/capo` | pipelines atuais em mongosh, validators e índices/TTLs lidos do banco. |

Estados: sem backend → aviso com a ação (`make api`); agregado vazio → aviso com
`make seed && make job`; lock ocupado → HTTP 409 exibido como erro.
