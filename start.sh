#!/bin/bash
# Sobe MongoDB (docker), backend (8410) e frontend (5410).
#
# Segue o contrato do launcher do PoV Portfolio (mesmo de atlas-timeseries-pagamentos):
#   1. fica em primeiro plano, para o grupo de processos segurar os filhos;
#   2. derruba a árvore inteira no SIGTERM (`npm run preview` gera um neto vite);
#   3. arma o trap antes de subir qualquer coisa e tolera porta ainda fechando.
# O container do MongoDB não é derrubado ao sair: ele guarda os dados da demo.
set -u

BASE="$(cd "$(dirname "$0")" && pwd)"
BACKEND_LOG="${TMPDIR:-/tmp}/frota-eta-backend.log"
FRONTEND_LOG="${TMPDIR:-/tmp}/frota-eta-frontend.log"
BACKEND_PORT=8410
FRONTEND_PORT=5410
PORT_WAIT_SECONDS=10
BACKEND_PID=""
FRONTEND_PID=""

fail() { echo "❌ $1" >&2; exit 1; }

kill_tree() {
  local pid="$1" sig="${2:-TERM}"
  [[ -z "$pid" ]] && return 0
  local kids
  kids="$(pgrep -P "$pid" 2>/dev/null || true)"
  for kid in $kids; do kill_tree "$kid" "$sig"; done
  kill -"$sig" "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM
  kill_tree "$FRONTEND_PID"
  kill_tree "$BACKEND_PID"
  sleep 1
  kill_tree "$FRONTEND_PID" KILL
  kill_tree "$BACKEND_PID" KILL
}
trap cleanup EXIT INT TERM

wait_for_url() {
  local url="$1" attempts="${2:-40}"
  for ((i = 1; i <= attempts; i++)); do
    curl --fail --silent --max-time 2 "$url" >/dev/null && return 0
    sleep 1
  done
  return 1
}

wait_port_free() {
  for ((i = 0; i < PORT_WAIT_SECONDS; i++)); do
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 || return 0
    sleep 1
  done
  return 1
}

command -v curl >/dev/null || fail "curl não encontrado."
command -v npm >/dev/null || fail "npm não encontrado."
[[ -f "$BASE/.env" ]] || cp "$BASE/.env.example" "$BASE/.env"
[[ -x "$BASE/.venv/bin/uvicorn" ]] || fail "Virtualenv ausente. Rode: make venv"
[[ -d "$BASE/frontend/node_modules" ]] || fail "Dependências do frontend ausentes. Rode: (cd frontend && npm install)"

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  wait_port_free "$port" || fail "Porta $port segue ocupada após ${PORT_WAIT_SECONDS}s; o processo existente foi preservado."
done

echo "🚚 Agregados em janela móvel · fallback de ETA"
echo "=============================================="

cd "$BASE"
ALVO="$(.venv/bin/python -c 'from frota import settings; print(settings.ALVO)')"
echo "▶ MongoDB: $ALVO"
if [[ "$ALVO" == "local" ]] && ! .venv/bin/python -c "from frota.db import client; client().admin.command('ping')" >/dev/null 2>&1; then
  echo "▶ MongoDB 8.0 (docker, replica set de 1 nó)..."
  if docker compose version >/dev/null 2>&1; then docker compose up -d --wait; else docker-compose up -d --wait; fi \
    || fail "MongoDB não subiu. Docker/colima está rodando?"
fi

echo "▶ backend (porta $BACKEND_PORT)..."
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
if ! wait_for_url "http://127.0.0.1:$BACKEND_PORT/health/live" 40; then
  echo "❌ Backend não ficou pronto. Últimas linhas do log:" >&2
  tail -n 25 "$BACKEND_LOG" >&2
  exit 1
fi

# aquece: bootstrap idempotente e cache de metadados antes de anunciar "pronto"
curl --silent --max-time 60 "http://127.0.0.1:$BACKEND_PORT/api/estado" >/dev/null || true

echo "▶ frontend (porta $FRONTEND_PORT)..."
cd "$BASE/frontend"
if [[ "${POV_DEV:-0}" == "1" ]]; then
  npm run dev > "$FRONTEND_LOG" 2>&1 &
else
  if [[ ! -d dist ]] || [[ -n "$(find src index.html vite.config.js -newer dist -print -quit 2>/dev/null)" ]]; then
    npm run build > "$FRONTEND_LOG" 2>&1 || { echo "❌ build do frontend falhou" >&2; tail -n 20 "$FRONTEND_LOG" >&2; exit 1; }
  fi
  npm run preview >> "$FRONTEND_LOG" 2>&1 &
fi
FRONTEND_PID=$!
if ! wait_for_url "http://127.0.0.1:$FRONTEND_PORT/" 40; then
  echo "❌ Frontend não ficou pronto." >&2
  tail -n 25 "$FRONTEND_LOG" >&2
  exit 1
fi

echo
echo "✅ pronto"
echo "   UI      http://127.0.0.1:$FRONTEND_PORT"
echo "   API     http://127.0.0.1:$BACKEND_PORT/docs"
echo "   Banco vazio? make seed PROFILE=small && make job"
wait
