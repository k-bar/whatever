#!/usr/bin/env python3
"""Warszawa Live on AWS.

  WarszawaLiveDb   RDS Postgres 16 + PostGIS, secrets (termination-protected; stateful)
  WarszawaLiveApp  API Lambda + Function URL, hourly ingest Lambda
  WarszawaLiveCi   GitHub OIDC role so .github/workflows/deploy.yml can deploy without keys

Deploy: infra/deploy.sh (builds the Lambda bundle, cdk deploy, runs migrations).
"""

import aws_cdk as cdk

from stacks.app_stack import AppStack
from stacks.ci_stack import CiStack
from stacks.db_stack import DbStack

GITHUB_REPO = "k-bar/whatever"

app = cdk.App()
env = cdk.Environment(account="015454941566", region="eu-north-1")
cdk.Tags.of(app).add("project", "warszawa-live")

db = DbStack(app, "WarszawaLiveDb", env=env, termination_protection=True)
api = AppStack(app, "WarszawaLiveApp", env=env, db=db)
CiStack(app, "WarszawaLiveCi", env=env, github_repo=GITHUB_REPO, migrate_function=api.api_fn)

app.synth()
