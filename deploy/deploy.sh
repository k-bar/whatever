#!/usr/bin/env bash
# Deploy the checked-out commit on this EC2 box. Run by the agent (infra/ec2/agent.sh) as root,
# from the repo root, with GIT_SHA set. Must be safe to re-run; non-zero exit = rollback.
set -euo pipefail
set -a; . /etc/warszawa/instance.env; set +a
: "${GIT_SHA:?}"
ROOT=$(pwd)
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache UV_PYTHON=3.12
log() { echo "[deploy] $*"; }

# --- release metadata visible to the services (/health reports it) ---------------------------
printf 'GIT_SHA=%s\nAPP_ENV=%s\n' "$GIT_SHA" "$APP_ENV" > /etc/warszawa/release.env

# --- backend ----------------------------------------------------------------------------------
log "backend: uv sync"
(cd backend && uv sync --frozen --no-dev -q)
chmod -R a+rX /opt/uv/python
# the 30 demo people (app/mocksocial.py); never on prod, and never a reason to roll back
[ "$APP_ENV" = prod ] || (cd backend && .venv/bin/python -m app.mocksocial) || log "backend: demo people not refreshed"

log "backend: migrations (schema ${DB_SCHEMA:-public})"
(cd backend && .venv/bin/alembic upgrade head)

# --- offline translation model (app/translate.py): PL -> EN, Argos Translate / OPUS-MT, ~70 MB -----
MODEL_DIR=/opt/warszawa/models
if [ ! -f "$MODEL_DIR/translate-pl_en-1_9/model/model.bin" ]; then
  log "translate: downloading the PL -> EN model"
  mkdir -p "$MODEL_DIR"
  tmp=$(mktemp)
  curl -fsSL https://argos-net.com/v1/translate-pl_en-1_9.argosmodel -o "$tmp"
  echo "07eda9edbd6ae5121df7c1d7bd847030423269b8c5056f1c222495c4a81e1721  $tmp" | sha256sum -c --quiet
  "$ROOT/backend/.venv/bin/python" -m zipfile -e "$tmp" "$MODEL_DIR"
  rm -f "$tmp"
  chmod -R a+rX "$MODEL_DIR"
fi

# --- systemd units ----------------------------------------------------------------------------
for unit in deploy/systemd/*.service deploy/systemd/*.timer; do
  sed -e "s|@ROOT@|$ROOT|g" -e "s|@INGEST_SCHEDULE@|$INGEST_SCHEDULE|g" "$unit" \
    > "/etc/systemd/system/$(basename "$unit")"
done
systemctl daemon-reload

systemctl enable -q warszawa-api.service
systemctl restart warszawa-api.service
systemctl enable -q --now warszawa-ingest.timer
systemctl enable -q --now warszawa-conditions.timer
systemctl enable -q --now warszawa-translate.timer
# Kamil's src/ synchronizer (raw Open Data tables), launched by app/ingest/src_sync.py
systemctl enable -q warszawa-sync.service
systemctl restart warszawa-sync.service

# --- health check: the new code must answer with the new sha ----------------------------------
for i in $(seq 1 30); do
  if body=$(curl -fsS -m 5 http://127.0.0.1/health 2>/dev/null) && [ "$(jq -r .sha <<<"$body")" = "$GIT_SHA" ]; then
    log "api healthy: $body"
    break
  fi
  [ "$i" = 30 ] && { log "api did not become healthy"; journalctl -u warszawa-api -n 40 --no-pager; exit 1; }
  sleep 2
done

# --- frontend -> S3 + CloudFront (skipped when unchanged) -------------------------------------
NODE_VERSION=22.12.0
if [ ! -x "/opt/node/bin/node" ] || [ "$(/opt/node/bin/node -v)" != "v$NODE_VERSION" ]; then
  rm -rf /opt/node && mkdir -p /opt/node
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-arm64.tar.xz" \
    | tar -xJ --strip-components=1 -C /opt/node
fi
export PATH="/opt/node/bin:$PATH"
log "frontend: npm ci && npm run build"
# the UI calls the API cross-origin (VITE_API_URL defaults to "/api", which only exists on the vite dev proxy)
(cd frontend && npm ci --no-audit --no-fund && VITE_API_URL="$API_URL" VITE_APP_ENV="$APP_ENV" npm run build)
OUT=$(mktemp -d)
cp -r frontend/dist/. "$OUT/"
find "$OUT" -name '.DS_Store' -delete
jq -n --arg api "$API_URL" --arg env "$APP_ENV" '{apiUrl: $api, env: $env}' > "$OUT/config.json"
hash=$(cd "$OUT" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
if [ "$hash" != "$(cat /var/lib/warszawa/site.hash 2>/dev/null || true)" ]; then
  log "frontend: publishing to s3://$WEB_BUCKET"
  aws s3 sync "$OUT" "s3://$WEB_BUCKET" --delete --only-show-errors
  aws cloudfront create-invalidation --distribution-id "$WEB_DISTRIBUTION_ID" --paths '/*' >/dev/null
  echo "$hash" > /var/lib/warszawa/site.hash
fi
rm -rf "$OUT"

log "done: $GIT_SHA"
