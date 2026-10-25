#!/usr/bin/env bash
# Builds a throwaway Vectana instance per language, fills it with demo data and
# takes the documentation screenshots.
#   tools/screenshots/run.sh [out-dir]   (default: tools/screenshots/out)
#
# Uses the dev PostgreSQL container (`mise run services`) with its own database
# `vectana_docs`, which is dropped and recreated for each language. Scans hit
# the real OSV and endoflife.date APIs. Expects a fresh `web/out` build.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="$(mkdir -p "${1:-$here/out}" && cd "${1:-$here/out}" && pwd)"
port=8099
base="http://127.0.0.1:$port"
db=vectana_docs

[ -d "$root/web/out" ] || { echo "web/out is missing: run \`mise run web:build\` first" >&2; exit 1; }
[ -d "$here/node_modules" ] || (cd "$here" && npm ci && npx playwright install chromium)

docker compose -f "$root/compose.yaml" up -d --wait db

export DATABASE_URL="postgresql+asyncpg://vectana:vectana@localhost:5432/$db"
export ALEMBIC_DATABASE_URL="$DATABASE_URL"
export SECRET_KEY="docs-screenshots-only-0123456789abcdef"
export STATIC_DIR="$root/web/out"
export WEB_URL="$base"
export MAIL_BACKEND=none
export SCAN_ON_CHANGE=false

api_pid=""
cleanup() { [ -n "$api_pid" ] && kill "$api_pid" 2>/dev/null || true; }
trap cleanup EXIT

admin() { node --input-type=module -e "import { admin } from '$here/data.mjs'; console.log(admin['$1']['$2'])"; }
admin_email() { node --input-type=module -e "import { ADMIN_EMAIL } from '$here/data.mjs'; console.log(ADMIN_EMAIL)"; }
admin_password() { node --input-type=module -e "import { ADMIN_PASSWORD } from '$here/data.mjs'; console.log(ADMIN_PASSWORD)"; }

for locale in ja en; do
  echo "== $locale"
  docker compose -f "$root/compose.yaml" exec -T db psql -qU vectana -d postgres \
    -c "DROP DATABASE IF EXISTS $db WITH (FORCE)" -c "CREATE DATABASE $db"

  export GROUP_NAME="$(admin "$locale" group)"
  (
    cd "$root/api"
    uv run alembic upgrade head >/dev/null
    VECTANA_ADMIN_PASSWORD="$(admin_password)" uv run python -m app.cli create-admin \
      --email "$(admin_email)" --name "$(admin "$locale" name)" --company "$(admin "$locale" company)"
  )

  (cd "$root/api" && exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$port" --log-level warning) &
  api_pid=$!
  for _ in $(seq 60); do curl -sf "$base/api/health" >/dev/null && break; sleep 0.5; done

  node "$here/seed.mjs" "$base" "$locale"
  (cd "$root/api" && uv run python -m app.worker --once)
  node "$here/seed.mjs" "$base" "$locale" --webhooks
  node "$here/capture.mjs" "$base" "$locale" "$out"

  kill "$api_pid"; wait "$api_pid" 2>/dev/null || true; api_pid=""
done

echo "Screenshots written to $out"
