#!/usr/bin/env bash
# Implanta atlas-trigger/ (app App Services "frota-eta-job": 2 Functions + 2 Scheduled
# Triggers) no projeto do cluster de MONGODB_URI.
#
# Nada de ID, host ou URI é impresso nem versionado: projeto, cluster e app ficam só no
# .env (ATLAS_PROJECT_ID, ATLAS_CLUSTER_NAME, APPSERVICES_APP_ID). Este script NÃO cria
# credencial: se o appservices CLI não tiver sessão ou permissão, ele para e explica.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$RAIZ/.env"
APP_NOME="frota-eta-job"
PY="${PY:-$RAIZ/.venv/bin/python}"

mascarar() { sed -E 's/[0-9a-f]{24}/<id>/g; s/frota-eta-job-[a-z0-9]+/frota-eta-job-<id>/g'; }

ler() { [ -f "$ENV" ] && grep -E "^$1=" "$ENV" | tail -1 | cut -d= -f2- | tr -d '"' || true; }

gravar() {  # gravar VAR valor — substitui a linha existente ou acrescenta no fim do .env
  "$PY" - "$ENV" "$1" "$2" <<'PYEOF'
import sys
from pathlib import Path
caminho, var, valor = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
linhas = caminho.read_text().splitlines() if caminho.exists() else []
novas = [f"{var}={valor}" if l.startswith(f"{var}=") else l for l in linhas]
if f"{var}={valor}" not in novas:
    novas.append(f"{var}={valor}")
caminho.write_text("\n".join(novas) + "\n")
PYEOF
}

for cmd in atlas appservices; do
  command -v "$cmd" >/dev/null || { echo "erro: '$cmd' CLI não encontrado no PATH" >&2; exit 1; }
done

PROJETO="$(ler ATLAS_PROJECT_ID)"
CLUSTER="$(ler ATLAS_CLUSTER_NAME)"
APP_ID="$(ler APPSERVICES_APP_ID)"

# 1. Projeto e cluster: do .env ou descobertos pelo host de MONGODB_URI (sem imprimir).
if [ -z "$PROJETO" ] || [ -z "$CLUSTER" ]; then
  echo "procurando o projeto do cluster de MONGODB_URI com o atlas CLI..."
  achado="$(MONGODB_URI="$(ler MONGODB_URI)" "$PY" - <<'PYEOF'
import json, os, re, subprocess
uri = os.environ.get("MONGODB_URI", "")
if "://" not in uri:
    raise SystemExit(0)
host = re.sub(r"^.*@", "", uri.split("://", 1)[1]).split("/")[0].split("?")[0].lower()
r = subprocess.run(["atlas", "api", "clusters", "listClusterDetails", "--itemsPerPage", "500"],
                   capture_output=True, text=True)
grupos = json.loads(r.stdout or "{}").get("results", []) if r.returncode == 0 else []
for g in grupos:
    for c in g.get("clusters", []):
        if c.get("name", "").lower() == host.split(".")[0]:
            print(g["groupId"], c["name"])
            raise SystemExit(0)
PYEOF
)"
  if [ -z "$achado" ]; then
    echo "BLOQUEADO: o atlas CLI não enxerga o cluster de MONGODB_URI." >&2
    echo "Preencha ATLAS_PROJECT_ID e ATLAS_CLUSTER_NAME no .env e rode de novo." >&2
    exit 2
  fi
  PROJETO="${achado%% *}"; CLUSTER="${achado#* }"
  gravar ATLAS_PROJECT_ID "$PROJETO"; gravar ATLAS_CLUSTER_NAME "$CLUSTER"
  echo "projeto e cluster gravados no .env"
fi

# 2. Sessão do appservices CLI. Usa a chave do ambiente, se houver; nunca cria uma nova.
if ! appservices apps list --project "$PROJETO" >/dev/null 2>&1; then
  if [ -n "${MONGODB_ATLAS_PUBLIC_API_KEY:-}" ] && [ -n "${MONGODB_ATLAS_PRIVATE_API_KEY:-}" ]; then
    appservices login --api-key "$MONGODB_ATLAS_PUBLIC_API_KEY" \
      --private-api-key "$MONGODB_ATLAS_PRIVATE_API_KEY" -y >/dev/null
  fi
  if ! saida="$(appservices apps list --project "$PROJETO" 2>&1)"; then
    echo "BLOQUEADO: o appservices CLI não tem sessão válida ou permissão no projeto." >&2
    echo "$saida" | mascarar | head -3 >&2
    echo "Rode 'appservices login' com uma chave que tenha Project Owner no projeto" >&2
    echo "(ou exporte MONGODB_ATLAS_PUBLIC_API_KEY/PRIVATE) e repita 'make trigger-deploy'." >&2
    exit 3
  fi
fi

# 3. Cópia temporária com o nome do cluster preenchido (o versionado só tem o marcador).
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$RAIZ/atlas-trigger/." "$TMP/app"
rm -f "$TMP/app/README.md"
sed -i.bak "s/\${ATLAS_CLUSTER_NAME}/$CLUSTER/" "$TMP/app/data_sources/mongodb-atlas/config.json"
rm -f "$TMP/app/data_sources/mongodb-atlas/config.json.bak"

# 4. Push: atualiza o app existente ou cria o app na primeira vez.
if [ -n "$APP_ID" ]; then
  echo "atualizando o app $APP_NOME..."
  appservices push --local "$TMP/app" --remote "$APP_ID" --yes 2>&1 | mascarar
else
  echo "criando o app $APP_NOME..."
  appservices push --local "$TMP/app" --remote "$APP_NOME" --project "$PROJETO" --yes 2>&1 | mascarar
  APP_ID="$(appservices apps list --project "$PROJETO" -f json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
apps = d.get("doc", d) if isinstance(d, dict) else d
for a in apps if isinstance(apps, list) else []:
    if isinstance(a, dict) and a.get("name") == "frota-eta-job":
        print(a.get("client_app_id") or a.get("clientAppId") or ""); break
' || true)"
  if [ -z "$APP_ID" ]; then
    echo "aviso: não consegui ler o ID do app; preencha APPSERVICES_APP_ID no .env" >&2
  else
    gravar APPSERVICES_APP_ID "$APP_ID"
    echo "APPSERVICES_APP_ID gravado no .env"
  fi
fi
echo "ok: app $APP_NOME implantado (triggers jobDiario e ingestaoSimulada)"
