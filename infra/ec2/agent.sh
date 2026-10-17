#!/usr/bin/env bash
# Pull-based CD agent. Runs every minute (warszawa-agent.timer).
# GitHub Actions moves release/<env> only after CI passes; this agent notices, deploys, and rolls
# back to the previous release if deploy/deploy.sh fails. State lives in /var/lib/warszawa.
set -euo pipefail
exec 9>/run/warszawa-agent.lock
flock -n 9 || exit 0

set -a; . /etc/warszawa/instance.env; set +a
STATE=/var/lib/warszawa
REPO=/opt/warszawa/repo
mkdir -p "$STATE"
log() { echo "[agent] $*"; }

# Deploy key (read-only, added by the repo owner) from Secrets Manager; refreshed every run
key=$(aws secretsmanager get-secret-value --secret-id "$DEPLOY_KEY_SECRET_ARN" --query SecretString --output text)
if [[ "$key" != *"PRIVATE KEY"* ]]; then log "deploy key not set yet"; exit 0; fi
umask 077; printf '%s\n' "$key" > /etc/warszawa/deploy_key; umask 022
export GIT_SSH_COMMAND="ssh -i /etc/warszawa/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=/etc/warszawa/known_hosts"

if [ ! -d "$REPO/.git" ]; then
  git init -q "$REPO" && git -C "$REPO" remote add origin "$GIT_REPO"
fi
cd "$REPO"
if ! git fetch -q origin "+refs/heads/$RELEASE_BRANCH:refs/remotes/origin/$RELEASE_BRANCH" 2>"$STATE/fetch.err"; then
  log "fetch failed (branch missing or key not authorized yet): $(tail -1 "$STATE/fetch.err")"
  exit 0
fi

new=$(git rev-parse "origin/$RELEASE_BRANCH")
cur=$(cat "$STATE/deployed" 2>/dev/null || true)
[ "$new" = "$cur" ] && exit 0
[ "$new" = "$(cat "$STATE/failed" 2>/dev/null || true)" ] && exit 0

deploy() {
  git checkout -qf "$1"
  GIT_SHA="$1" bash deploy/deploy.sh
}

log "deploying $new (was ${cur:-nothing})"
if deploy "$new"; then
  echo "$new" > "$STATE/deployed"
  rm -f "$STATE/failed"
  log "deployed $new"
else
  echo "$new" > "$STATE/failed"
  log "deploy of $new FAILED"
  if [ -n "$cur" ]; then
    log "rolling back to $cur"
    deploy "$cur" && log "rolled back to $cur" || log "ROLLBACK FAILED"
  fi
  exit 1
fi
