# Plano de implementação

Estado em 2026-10-16. Versão 0.1.0 (não publicada).

## Concluído

1. Infra: `docker-compose.yml` (MongoDB 8.0 replica set de 1 nó, porta 27027), `.env`, `Makefile`, `start.sh` no contrato do launcher do portfólio.
2. Bootstrap idempotente: 11 collections com `$jsonSchema` strict, índices e TTLs (`scripts/bootstrap_db.py`).
3. Fixtures do contrato 14.1 + testes da camada 1.
4. Camada 2 (dois modos de limpeza) e consulta de fallback com hierarquia.
5. Job com lease, retry com backoff, watermark de atrasos e retomada segura.
6. Gerador determinístico (`small`, `escala`, `teste`), relógio simulado com `ingestao_pendente`, `advance`.
7. API FastAPI + UI Vite/React (5 abas + "Por baixo do capô"), badges derivados.
8. Benchmark `escala` (local e Atlas) e documentação.
9. Validação no Atlas M30 (MongoDB 9.0.4): 90 testes, bateria de resiliência (35 casos), caos real no Docker, jornada de UI.
10. Registro no portal (`povs.json`) e reserva de portas 5410/8410 (+27027).

## Não feito / próximos passos

- Réplica gravada para o `pov-demo-player`.
- Merge da reserva de portas no `_shared` (branch `chore/portas-rolling-aggregates`).
- Camada 2 incremental (somar dia que entra, subtrair o que sai) se o volume de buckets crescer.
