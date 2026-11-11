#!/bin/sh
set -e

cd /app
# Alvo do banco: só do ambiente. Com MONGODB_URI preenchida (FROTA_MONGO=auto) o
# backend usa o Atlas; a imagem não sobe nem depende do mongo do docker-compose.
# Um worker: o estado do reset (/api/reset/status) e os caches vivem em memória.
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --workers 1 &
nginx -g 'daemon off;'
