#!/usr/bin/env bash
# Writes /run/warszawa/ingestor.env (root-only, tmpfs) for Kamil's src/ ingestor, which expects
# DATABASE_URL and WARSZAWA_API_TOKEN. Values come from Secrets Manager; nothing touches disk.
set -euo pipefail
set -a; . /etc/warszawa/instance.env; set +a

db=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --query SecretString --output text)
token=$(aws secretsmanager get-secret-value --secret-id "$WARSAW_API_TOKEN_SECRET_ARN" --query SecretString --output text)
schema=${DB_SCHEMA:+$DB_SCHEMA,}public

url=$(jq -r --arg schema "$schema" '
  "postgresql+psycopg://\(.username|@uri):\(.password|@uri)@\(.host):\(.port)/\(.dbname // "warszawa")"
  + "?sslmode=require&options=\("-csearch_path=" + $schema | @uri)"' <<<"$db")

mkdir -p /run/warszawa
umask 077
printf 'DATABASE_URL=%s\nWARSZAWA_API_TOKEN=%s\n' "$url" "$token" > /run/warszawa/ingestor.env
