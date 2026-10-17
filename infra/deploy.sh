#!/usr/bin/env bash
# Build the Lambda bundle, deploy all stacks, run DB migrations. Used locally and by deploy.yml.
#   infra/deploy.sh                 # everything
#   infra/deploy.sh WarszawaLiveApp # one stack
set -euo pipefail
cd "$(dirname "$0")"

CDK="npx -y aws-cdk@2.1145.0"
./build_lambda.sh
$CDK deploy "${@:---all}" --require-approval never --outputs-file build/outputs.json

fn=$(aws cloudformation describe-stacks --stack-name WarszawaLiveApp \
  --query "Stacks[0].Outputs[?OutputKey=='ApiFunctionName'].OutputValue" --output text)
aws lambda invoke --function-name "$fn" --payload '{"action":"migrate"}' \
  --cli-binary-format raw-in-base64-out build/migrate.json >/dev/null
cat build/migrate.json; echo
aws cloudformation describe-stacks --stack-name WarszawaLiveApp \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text | sed 's/^/API: /'
