# Operations

Owner: @JustCodeMeV. Everything in AWS is defined in `infra/` (CDK). **Never change AWS resources in the
console**: it drifts from CDK and has already taken both boxes offline once (the RDS master password
rotation).

## Environments

| | prod | dev |
|---|---|---|
| Website | https://syrenka.me | https://dev.syrenka.me |
| API | https://api.syrenka.me | https://api-dev.syrenka.me |
| Git branch → release branch | `master` → `release/prod` | `dev` → `release/dev` |
| EC2 box | `i-0967b0e218956695c` | `i-0c0288ca5854c3e5e` |
| DB schema | `public` | `dev` |
| Ingest schedule | hourly at `:17` | every 6 h at `:37` |
| Geocode limit per source and run | 200 | 30 |

`deploy/environments.json` is the machine-readable copy of this table. Both boxes are `t4g.micro` (arm64,
916 MB RAM) and share one RDS instance (`t4g.micro`, Postgres 16 + PostGIS).

## AWS layout (`infra/app.py`)

- **Account and region:** account `015454941566`, region `eu-north-1` only. The organization's SCP denies
  every other region, including `eu-central-1` and the Warsaw Local Zone.
- **Stacks:**

  | Stack | What |
  |---|---|
  | `WarszawaLiveDb` | RDS, the app security group, secrets |
  | `WarszawaLiveZone` | Route 53 zone |
  | `WarszawaLiveDns` | CloudFront certificate |
  | `WarszawaLiveProd`, `WarszawaLiveDev` | Per environment: the EC2 box, the API CloudFront, the website (S3 + CloudFront) |
  | `WarszawaLiveTeam` | IAM users and dev-schema DB logins for teammates (`DEV_DB_USERS` in `infra/stacks/team_stack.py`) |

- **Network:** Postgres only accepts the app boxes. The boxes only accept HTTP from CloudFront's origin
  IP ranges. There is no SSH; use SSM Session Manager.
- **Changing infra:** `infra/deploy.sh`. CI runs `cdk synth` and shellcheck on every PR.

## Deploys (pull-based)

The SCP blocks GitHub OIDC roles, so GitHub never pushes to AWS.

1. A PR is merged into `dev` or `master`. CI runs on the push.
2. `.github/workflows/release.yml` moves `release/dev` or `release/prod` to that commit once CI is green.
3. On each box, `warszawa-agent.timer` runs `infra/ec2/agent.sh` every minute. The agent notices the new
   release commit and runs `deploy/deploy.sh` from the repo root with `GIT_SHA` set. If the deploy fails,
   it rolls back to the previous release.
4. `deploy/deploy.sh`:
   - runs `uv sync`, then `alembic upgrade head` in `DB_SCHEMA`;
   - downloads the translation model once and checks its sha256;
   - installs `deploy/systemd/*` and restarts the API and the sync service;
   - waits until `/health` reports the new sha (otherwise it exits non-zero, which triggers the rollback);
   - builds the frontend with `VITE_API_URL` and `VITE_APP_ENV`;
   - syncs the site to S3 and invalidates CloudFront, but only when the built site changed.

Never push to `release/*` by hand. To promote, open a PR `dev → master`. Before every promotion, check
that dev tools are stripped (see [frontend.md](frontend.md#dev-tools-never-on-prod)).

## Services on each box (`deploy/systemd/`)

| Unit | Runs | When |
|---|---|---|
| `warszawa-api.service` | `uvicorn app.main:app` on port 80, 2 workers | always (`Restart=always`) |
| `warszawa-ingest.timer` → `.service` | `python -m app.ingest.run --geocode-limit $INGEST_GEOCODE_LIMIT` | `INGEST_SCHEDULE` |
| `warszawa-conditions.timer` → `.service` | `python -m app.ingest.conditions` | every 10 min |
| `warszawa-sync.service` | `python -m app.ingest.src_sync --watch` (Kamil's `src/` scheduler) | long-running (`Restart=on-failure`) |
| `warszawa-agent.timer` | `infra/ec2/agent.sh` (deploys) | every minute |

## Configuration

`backend/app/config.py` reads environment variables, from `/etc/warszawa/instance.env` (written by CDK
user data) and `/etc/warszawa/release.env` (`GIT_SHA`, `APP_ENV`). Secrets are fetched from Secrets
Manager at startup by ARN:

| Secret | Holds | Env var with its ARN |
|---|---|---|
| `warszawa-live/db` | RDS credentials (generated) | `DB_SECRET_ARN` |
| `warszawa-live/<env>/jwt` | JWT signing key | `JWT_SECRET_ARN` |
| `warszawa-live/warsaw-api-token` | JSON `{token, relay_url, relay_token}` | `WARSAW_API_TOKEN_SECRET_ARN` |
| `warszawa-live/deploy-key` | Read-only GitHub deploy key | `DEPLOY_KEY_SECRET_ARN` |
| `warszawa-live/dev/db-users/<name>` | Teammates' dev DB passwords | — |

Other variables: `API_URL`, `APP_ENV`, `DB_SCHEMA`, `DB_POOL_SIZE`, `INGEST_SCHEDULE`,
`INGEST_GEOCODE_LIMIT`, `WEB_BUCKET`, `WEB_DISTRIBUTION_ID`, `GIT_REPO`, `RELEASE_BRANCH`. Locally,
`backend/.env` (template: `backend/.env.example`).

Never print, log or commit secret values. CI runs gitleaks on every PR (`.gitleaksignore` lists the
acknowledged old leak).

### Prompt search (the Assistant)

`POST /assistant` uses deterministic rules (k-bar's rule-based search). It does not call an LLM and
does not send prompts to an external service. It extracts known categories, music genres, cuisines,
soft preferences, Warsaw districts and areas, dates, and near-me / open-now requests. Then it applies
those filters in PostgreSQL. Category names come from `backend/app/categories.py`. The aliases and
phrase rules are in `backend/app/assistant/nlu.py`.

`results` holds exact matches only: every asked word appears in the listing, and the category matches.
Broader matches go in `suggestions`, in groups whose label says what was relaxed: the area, the day, or
the genre. A broad match (for example, another music event when the asked genre is not in the listing)
is labelled as unconfirmed. It is never presented as an exact match. "Near me" without a position gets
no exact results: the answer says the location is missing. Soft preferences such as "free" and
"family-friendly" only affect ranking. They are not guaranteed unless the listing confirms them.

The parser is bounded on purpose: it understands the phrases in its word lists, not arbitrary
language. Add a rule only together with a test for the prompt and the expected filters. Search can
only return records already in the database. Exact genre and cuisine matching depends on the source
records containing that detail.

## Warsaw API relay

`dane.um.warszawa.pl` drops connections from AWS IPs, and the SCP rules out a Polish AWS region. Calls
therefore go through an HTTP relay on a teammate's homelab in Poland, exposed as a Cloudflare tunnel.

- **Configured in:** the secret `warszawa-live/warsaw-api-token` (`relay_url`, `relay_token`).
- **Backend:** `app/ingest/sources/warsaw_open_data.py` `api_request()` sends `Authorization: Bearer
  <relay token>`, `X-Relay-Target: <real URL>` and `X-Relay-Authorization: <API token>`.
- **Kamil's `src/`:** gets a `requests.Session` from `src_sync.py` that does the same.
- **No relay configured:** both call the API directly. This works from Poland, which is how it runs
  locally.
- **The current tunnel URL is temporary (until 2026-10-24).** When it changes, update only the secret.
  The boxes read it on each run.

## Runbook

SSM shell: `aws ssm start-session --target <instance id>`. Read-only checks:

```bash
journalctl -u warszawa-agent -f              # deploys and rollbacks
journalctl -u warszawa-api -n 100            # API errors
journalctl -u warszawa-ingest -n 50          # last ingest: one line per source + translate
journalctl -u warszawa-sync -n 50            # Kamil's scheduler; also the sync_logs table
systemctl list-timers 'warszawa-*'
curl -s localhost/health
```

Actions:

```bash
sudo systemctl start warszawa-ingest         # ingest now (results: GET /sources)
sudo systemctl start warszawa-conditions     # weather + air now
```

To run a single source once, use `systemd-run`, so that it gets the same user and environment as the
timer:

```bash
WD=$(systemctl show -p WorkingDirectory --value warszawa-ingest.service)
sudo systemd-run --wait --uid=warszawa -p WorkingDirectory=$WD \
  -p EnvironmentFile=/etc/warszawa/instance.env -p EnvironmentFile=/etc/warszawa/release.env \
  $WD/.venv/bin/python -m app.ingest.run --source osm_venues --geocode-limit 0
```

If a deploy breaks and the code didn't change, check CloudTrail for console changes first.

## Database access for people

Each teammate gets their own Postgres login, with all rights on schema `dev` and no access to prod.
They connect through an SSM port-forward via the dev box. The steps (AWS CLI profile, tunnel, DataGrip
settings) are in `CONTRIBUTING.md`, section "Connecting a DB client". In DataGrip, tick the `dev`
schema; `public` looks empty on purpose.

## CI (`.github/workflows/ci.yml`)

The jobs run only when their part of the repo changed:

| Job | Runs |
|---|---|
| `fetchers` | Parser contract tests |
| `backend` | `ruff check`, `ruff format --check`, `alembic upgrade head && alembic check`, `pytest` on PostGIS |
| `infra` | shellcheck, `cdk synth` |
| `frontend` | `npm ci && npm run build` |
| `secrets` | gitleaks |

`ci-ok` is the required check.
