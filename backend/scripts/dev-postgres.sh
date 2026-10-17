#!/usr/bin/env bash
# Local Postgres 16 + PostGIS without Docker or sudo. Everything lives in <repo>/.dev/ (gitignored).
#
#   backend/scripts/dev-postgres.sh start    # first run installs (~1 min), then starts on port 54329
#   backend/scripts/dev-postgres.sh stop
#   backend/scripts/dev-postgres.sh psql
#
# Have Docker? `docker compose up -d db` from the repo root does the same thing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEV="$ROOT/.dev"
PG="$DEV/pg/bin"
DATA="$DEV/pgdata"
PORT=54329

install() {
  mkdir -p "$DEV"
  if [ ! -x "$DEV/bin/micromamba" ]; then
    case "$(uname -s)-$(uname -m)" in
      Linux-x86_64) plat=linux-64 ;;
      Linux-aarch64) plat=linux-aarch64 ;;
      Darwin-arm64) plat=osx-arm64 ;;
      Darwin-x86_64) plat=osx-64 ;;
      *) echo "unsupported platform, use docker compose" >&2; exit 1 ;;
    esac
    curl -sL "https://micro.mamba.pm/api/micromamba/$plat/latest" | tar -xj -C "$DEV" bin/micromamba
  fi
  MAMBA_ROOT_PREFIX="$DEV/mamba" "$DEV/bin/micromamba" create -y -q -p "$DEV/pg" -c conda-forge postgresql=16 postgis
}

case "${1:-start}" in
  start)
    [ -x "$PG/postgres" ] || install
    if [ ! -d "$DATA" ]; then
      "$PG/initdb" -D "$DATA" -U postgres -A trust -E UTF8 >/dev/null
    fi
    "$PG/pg_ctl" -D "$DATA" status >/dev/null 2>&1 || "$PG/pg_ctl" -D "$DATA" -o "-p $PORT -k $DEV -c listen_addresses=localhost" -l "$DEV/pg.log" -w start >/dev/null
    for db in warszawa warszawa_test; do
      "$PG/psql" -qh localhost -p $PORT -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
        || "$PG/psql" -qh localhost -p $PORT -U postgres -c "CREATE DATABASE $db"
    done
    echo "Postgres running: postgresql+psycopg://postgres@localhost:$PORT/warszawa"
    ;;
  stop) "$PG/pg_ctl" -D "$DATA" stop ;;
  psql) shift; exec "$PG/psql" -h localhost -p $PORT -U postgres -d warszawa "$@" ;;
  *) echo "usage: $0 start|stop|psql" >&2; exit 1 ;;
esac
