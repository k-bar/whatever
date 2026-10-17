#!/usr/bin/env bash
# Deploy infrastructure changes (CDK). App code does NOT go through here: it ships by
# merging to dev/master (see .github/workflows/release.yml and deploy/deploy.sh).
#   infra/deploy.sh                      # all stacks
#   infra/deploy.sh WarszawaLiveDev      # one stack
set -euo pipefail
cd "$(dirname "$0")"
npx -y aws-cdk@2.1145.0 deploy "${@:---all}" --require-approval never --outputs-file outputs.json
