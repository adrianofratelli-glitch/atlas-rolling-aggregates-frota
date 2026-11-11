# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
RUN apt-get update \
  && apt-get install -y --no-install-recommends nginx curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 10001 app

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Configuração só por variável de ambiente em runtime (MONGODB_URI, MONGODB_DB,
# FROTA_MONGO...): nenhum .env entra na imagem. A imagem não inclui MongoDB:
# sem MONGODB_URI o backend tentaria o mongo local do docker-compose.
COPY backend/ ./backend/
# GET /api/trigger-script lê as Functions geradas em atlas-trigger/.
COPY atlas-trigger/ ./atlas-trigger/
COPY --from=frontend-build /build/dist ./frontend/dist
COPY nginx.conf /etc/nginx/nginx.conf
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh && chown -R app:app /app
USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health/live || exit 1

CMD ["/start.sh"]
