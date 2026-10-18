#!/usr/bin/env python3
"""Warszawa Live on AWS (everything in eu-north-1: the org SCP denies CloudFormation elsewhere).

  WarszawaLiveDb    shared: RDS Postgres 16 + PostGIS (prod = schema public, dev = schema dev),
                    app security group, secrets (DB, JWT, Warsaw API token, GitHub deploy key)
  WarszawaLiveZone  Route53 zone             } only once "domain" is set in cdk.json
  WarszawaLiveDns   CloudFront certificate   }
  WarszawaLiveMail  SES identity (DKIM, MAIL FROM, DMARC) }
  WarszawaLiveProd  EC2 box + API CloudFront + website, deploys release/prod
  WarszawaLiveDev   EC2 box + API CloudFront + website, deploys release/dev
  WarszawaLiveTeam  IAM users + DB logins for teammates' DB clients (dev schema, via SSM tunnel)

Code reaches the boxes by pull, not push (the SCP blocks GitHub OIDC roles): CI passes ->
.github/workflows/release.yml moves release/<env> -> the box's agent deploys it (deploy/deploy.sh).
Infra changes: infra/deploy.sh.
"""

import aws_cdk as cdk

from stacks.db_stack import DbStack
from stacks.dns_stack import DnsStack, ZoneStack
from stacks.env_stack import EnvConfig, EnvStack
from stacks.mail_stack import MailStack
from stacks.team_stack import TeamStack

app = cdk.App()
env = cdk.Environment(account="015454941566", region="eu-north-1")
cdk.Tags.of(app).add("project", "warszawa-live")

domain = app.node.try_get_context("domain")  # e.g. "warszawa.live"; set in cdk.json once bought

db = DbStack(
    app,
    "WarszawaLiveDb",
    env=env,
    termination_protection=True,
    open_to_internet=bool(app.node.try_get_context("db_open_to_internet")),
)
zone = ZoneStack(app, "WarszawaLiveZone", env=env, domain=domain) if domain else None
dns = DnsStack(app, "WarszawaLiveDns", env=env, zone=zone) if zone else None
mail = MailStack(app, "WarszawaLiveMail", env=env, zone=zone) if zone else None

ENVS = [
    EnvConfig(
        name="prod",
        release_branch="release/prod",
        db_schema="",
        ingest_schedule="*-*-* *:17:00",
        geocode_limit=200,
        web_hosts=("", "www"),
        api_host="api",
    ),
    EnvConfig(
        name="dev",
        release_branch="release/dev",
        db_schema="dev",
        ingest_schedule="*-*-* 00/6:37:00",
        geocode_limit=30,
        web_hosts=("dev",),
        api_host="api-dev",
    ),
]
for cfg in ENVS:
    s = EnvStack(app, f"WarszawaLive{cfg.name.capitalize()}", env=env, cfg=cfg, db=db, dns=dns)
    if mail:
        mail.grant_send(s.role, f"no-reply@{domain}")  # backend/app/config.py mail_from
    cdk.Tags.of(s).add("env", cfg.name)

TeamStack(app, "WarszawaLiveTeam", env=env, db=db)

app.synth()
