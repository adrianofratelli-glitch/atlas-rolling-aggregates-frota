# POV — agregados em janela móvel (fallback de ETA para frota)
PY      ?= .venv/bin/python
COMPOSE ?= $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo docker-compose)
PROFILE ?= small
ASOF    ?=
DAYS    ?= 1
DB      ?=
DBARG    = $(if $(DB),--db $(DB),)
ASOFARG  = $(if $(ASOF),--asof $(ASOF),)

.PHONY: help venv up down seed fixtures job advance api ui ui-build test bench reset pipelines trigger-deploy smoke

help:
	@echo "make up | seed PROFILE=small|escala | fixtures | job ASOF=YYYY-MM-DD | advance DAYS=1"
	@echo "make api | ui | ui-build | test | bench | reset | pipelines | trigger-deploy"

.venv/bin/python:
	python3.12 -m venv .venv || python3 -m venv .venv
	.venv/bin/pip install -q -r requirements.txt

venv: .venv/bin/python

.env:
	cp .env.example .env

ALVO = $(shell $(PY) -c "from frota import settings; print(settings.ALVO)" 2>/dev/null || echo local)

# Alvo local: MongoDB 8.0 replica set de 1 nó no docker. Alvo Atlas: só o bootstrap.
up: venv .env
	@echo "alvo MongoDB: $(ALVO)"
	@if [ "$(ALVO)" = "local" ]; then $(COMPOSE) up -d --wait; fi
	$(PY) scripts/bootstrap_db.py $(DBARG)

down:
	$(COMPOSE) down

# recria o banco da demo (guarda explícita: ALLOW_DEMO_DB_WRITE=1 só neste alvo)
seed: venv .env
	ALLOW_DEMO_DB_WRITE=1 $(PY) scripts/seed.py --profile $(PROFILE) $(DBARG) $(ASOFARG)

fixtures: venv .env
	$(PY) scripts/fixtures.py $(DBARG)

job: venv
	$(PY) jobs/materializar.py $(ASOFARG) $(DBARG)

advance: venv
	$(PY) scripts/advance.py --days $(DAYS) $(DBARG)

api: venv
	$(if $(DB),MONGODB_DB=$(DB),) .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8410

frontend/node_modules:
	cd frontend && npm install

ui: frontend/node_modules
	cd frontend && npm run dev

ui-build: frontend/node_modules
	cd frontend && npm run build

test: venv
	$(PY) -m pytest -q tests

bench: venv
	ALLOW_DEMO_DB_WRITE=1 $(PY) -u scripts/bench.py

# docs/pipelines/ e as Functions de atlas-trigger/ saem dos mesmos builders Python
pipelines: venv
	$(PY) scripts/export_pipelines.py

# implanta o app App Services (2 Scheduled Triggers) no projeto do cluster de MONGODB_URI
trigger-deploy: venv
	PY=$(PY) bash scripts/trigger_deploy.sh

# esvazia o banco da demo (preserva validators e índices)
reset: venv
	ALLOW_DEMO_DB_WRITE=1 $(PY) scripts/reset.py $(DBARG)

smoke:
	@echo "requer Playwright para Python: <python> scripts/ui_smoke.py"
