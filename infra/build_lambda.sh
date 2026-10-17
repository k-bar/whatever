#!/usr/bin/env bash
# Build the Lambda code bundle (arm64, Python 3.12 on Amazon Linux 2023 = glibc 2.34) into infra/build/lambda without Docker.
set -euo pipefail

INFRA="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$INFRA/../backend"
OUT="$INFRA/build/lambda"

rm -rf "$OUT" && mkdir -p "$OUT"
cd "$BACKEND"
uv export --frozen --no-dev --no-hashes --no-emit-project -q -o "$INFRA/build/requirements.txt"
# boto3 already ships with the Lambda runtime; uvicorn is only for local dev
grep -vE '^(boto3|botocore|s3transfer|uvicorn|uvloop|httptools|watchfiles|websockets)==' \
  "$INFRA/build/requirements.txt" > "$INFRA/build/requirements.lambda.txt"
uv pip install -q -r "$INFRA/build/requirements.lambda.txt" --target "$OUT" \
  --python-platform aarch64-manylinux_2_28 --python-version 3.12 --only-binary :all:
cp -r app alembic alembic.ini "$OUT/"
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +
du -sh "$OUT" | awk '{print "lambda bundle: " $1}'
