# Working on Warszawa Live

## Who owns what

| Folder | Owner | What goes there |
|---|---|---|
| `backend/app/ingest/sources/` | Kamil (@kdzwigal) | One file per data source: fetch records, turn them into `RawEvent`s |
| `backend/` (everything else) | @JustCodeMeV | Database, loading, API |
| `frontend/` | Philip (@philpiano) | The map UI |
| `infra/`, `deploy/` | @JustCodeMeV | AWS (CDK, Python): RDS, EC2 boxes, CloudFront, domain; on-box deploy scripts |
| `backend/db/` | Mateusz (@Informatyczek) | exploratory scrapers (`db/fetch_*.py`: kupbilecik.pl, streets.gl) and their local SQLite snapshots (gitignored; see `db/db.md`). Production sources live in `backend/app/ingest/sources/` |

```
fetchers (sources/*.py) ── list[RawEvent] ──> ingest/run.py ──> RDS Postgres ──> FastAPI ──> UI
        systemd timer on the EC2 box (prod hourly)     (AWS eu-north-1)    same EC2 box, behind CloudFront
```

## Environments

| | dev | prod |
|---|---|---|
| Git branch | `dev` | `master` |
| API | see `deploy/environments.json` | see `deploy/environments.json` |
| Website | see `deploy/environments.json` | see `deploy/environments.json` |
| Database | RDS, schema `dev` | same RDS, schema `public` |

Each environment is one EC2 box running the API, the ingest timer (prod hourly, dev every 6 h), the 10-minute conditions timer and Kamil's
`src/` sync service. Details: [docs/operations.md](docs/operations.md).

## Everyday flow

1. Pull: `git pull`
2. Branch: `git switch -c <name>/<topic>`, e.g. `kamil/meetup-source`
3. Commit, push, open a PR to **`dev`**. The template asks three questions.
4. CI runs. Wait for **ci-ok** to go green. CODEOWNERS asks the right person to review.
5. Merge → CI runs on `dev` → the **Release** workflow moves `release/dev` → the dev box deploys it
   within a minute and Release goes green once `/health` reports your commit.
6. Ship to prod: open a PR `dev → master`. Merging it releases to prod the same way.

A deploy that fails its health check rolls back to the previous commit automatically, and Release goes red.
Never push to `release/*` by hand.

Never commit `.env`, `apiKey.txt`, tokens or `*.db` files. CI runs gitleaks and fails the PR if it finds a secret.

## Running the backend locally

```bash
cd backend
uv sync                                   # installs Python deps (https://docs.astral.sh/uv/)
scripts/dev-postgres.sh start             # local Postgres+PostGIS in .dev/, no Docker or sudo
                                          # (or: docker compose up -d db)
cp .env.example .env                      # add WARSAW_API_TOKEN if you have one
uv run alembic upgrade head               # create tables
uv run python -m app.ingest.run --geocode-limit 0   # load real data (needs WARSAW_API_TOKEN)
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs
uv run pytest                             # tests
```

## Adding a data source (Kamil)

1. Copy the shape of `backend/app/ingest/sources/warsaw_open_data.py`. Each source is a `SourceSpec` with:
   - `fetch_records()`: network call that returns plain dicts;
   - `parse(records)`: pure function that returns `list[RawEvent]` (see `backend/app/ingest/base.py`).
2. Register it in `backend/app/ingest/sources/__init__.py`.
3. Save 5–20 real records as `backend/tests/fixtures/<slug>.json`.
4. `uv run pytest tests/test_contract.py`. That's the same check CI runs for you.
5. Try it for real: `uv run python -m app.ingest.run --source <slug>`.

Rules for `RawEvent`:
- `external_key` must stay the same across runs (source URL or id, never a row number).
- Datetimes must be timezone-aware.
- No coordinates? Fill `address`. The loader geocodes it.
- Put the source's own category labels in `categories_raw`. The backend maps them in `app/categories.py`.

## Using the API (Philip & consumers)

The API runs on EC2 next to RDS (`eu-north-1`) and reads the environment's schema:

- **Dev** (schema `dev`): `https://api-dev.syrenka.me`
- **Prod** (schema `public`): `https://api.syrenka.me`
- Interactive docs and schemas: `<api-url>/docs`. OpenAPI JSON: `<api-url>/openapi.json`. That is the
  source of truth for parameters; the table below is a summary.

| Endpoint | What | Main parameters |
|---|---|---|
| `GET /events` | GeoJSON, one feature per occurrence | `bbox=west,south,east,north`, `from`, `to`, `category` (repeatable), `kind=event\|class`, `q`, `limit`, `lang=pl\|en` |
| `GET /events/now` | Happening near a point within a few hours | `lat`, `lng`, `radius_m`, `hours`, `lang` |
| `GET /events/{id}` | One event / place / class with all occurrences | `lang` |
| `GET /places` | Venues and amenities (toilets and AEDs only when asked for by `category`) | `bbox`, `category`, `q`, `lang` |
| `GET /conditions` | Latest weather and air quality as GeoJSON points | |
| `GET /routes` | Tourist routes as LineStrings, built from Kamil's `tourist_routes.traces` | |
| `GET /sources` | Ingestion status per source (`last_status`, `last_run_at`, `item_count`) | |
| `GET /categories` | Category slugs and labels (`app/categories.py`) | |
| `GET /busyareas` | GeoJSON polygons of busy areas | |

- Login: `POST /auth/login` returns `access_token`. Send it as `Authorization: Bearer <token>`.
- Need something else? Open an **API request** issue.

## On the box (needs AWS access to account 015454941566, ask @JustCodeMeV)

`deploy/deploy.sh` does everything on each merge: `alembic upgrade head` in the box's schema (including
Kamil's raw tables from `src/models.py`, migration `0007`), then the systemd units:

| Unit | What |
|---|---|
| `warszawa-api` | FastAPI |
| `warszawa-ingest.timer` | `app/ingest/run.py`: fetchers -> `events`, plus tourist routes |
| `warszawa-conditions.timer` | weather + air quality -> `weather_stations`, `air_stations` |
| `warszawa-translate.timer` | every 10 min: PL -> EN titles and descriptions for new or changed events (`app/translate.py`) |
| `warszawa-sync` | Kamil's `src/` scheduler -> raw tables (`toilets`, `city_events`, `streets_gl_venues`, `sync_logs`, ...), via `app/ingest/src_sync.py` |

`src_sync.py` gives Kamil's code the box's DB credentials (Secrets Manager), the `<DB_SCHEMA>, public`
search_path and the Warsaw API relay. `src/` honours `DB_SCHEMA` (default `public`, which is prod), so when
running `python -m src.main` by hand against RDS always set `DB_SCHEMA=dev`.

No SSH: use Session Manager (`aws ssm start-session --target <instance from deploy/environments.json>`).

```bash
journalctl -u warszawa-agent -f        # deploys
journalctl -u warszawa-api -f          # API
journalctl -u warszawa-sync -f         # Kamil's src/ sync; results also in the sync_logs table
sudo systemctl start warszawa-ingest   # run ingestion now; results in GET /sources
sudo systemctl start warszawa-conditions  # refresh weather + air quality now
sudo systemctl start warszawa-translate   # translate pending events now
```

## Connecting a DB client (DataGrip) to the dev schema

You get your own Postgres login (all rights on schema `dev`, no access to prod) and an AWS user that can
only open a tunnel through the dev box. Ask @JustCodeMeV to add you to `DEV_DB_USERS` in
`infra/stacks/team_stack.py`.

1. Install the AWS CLI v2 and the
   [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html),
   then `aws configure --profile syrenka` with the keys you were sent (region `eu-north-1`).
2. Your DB password:
   `aws secretsmanager get-secret-value --profile syrenka --secret-id warszawa-live/dev/db-users/<you> --query SecretString --output text`
3. Open the tunnel and leave it running:
   ```bash
   aws ssm start-session --profile syrenka \
     --target "$(aws ec2 describe-instances --profile syrenka --filters Name=tag:env,Values=dev Name=instance-state-name,Values=running --query 'Reservations[0].Instances[0].InstanceId' --output text)" \
     --document-name AWS-StartPortForwardingSessionToRemoteHost \
     --parameters '{"host":["warszawalivedb-postgres9dc8bb04-covqyqx6uo8t.cba6qiu6ipoi.eu-north-1.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["15432"]}'
   ```
4. DataGrip: host `localhost`, port `15432`, database `warszawa`, user = your name, SSL mode `require`.
   Your tables live in schema `dev`: in the data source's **Schemas** tab tick `dev`, then Refresh (Ctrl+F5).
   `public` is prod and deliberately invisible to you, so it looks empty.

## Adding a data source

Kamil owns the database schema and the data sources; the backend adapts to them. Two places:

- `src/` (Kamil): raw Open Data tables, defined in `src/models.py`. New or changed tables need a backend
  migration that creates them in the right schema (see `0007_kamil_tables.py`); ping @JustCodeMeV.
- `backend/app/ingest/sources/`: fetchers that feed `events`. They return RawEvents; they may read
  Kamil's raw tables but never write to them:

1. Write `fetch_records()` (network; Warsaw Open Data goes through `warsaw_open_data.fetch(action)`, which
   handles the API key and the relay) and a pure `parse(records) -> list[RawEvent]` (`app/ingest/base.py`).
2. Add your `SPECS` to `app/ingest/sources/__init__.py`.
3. Save a few real records as `backend/tests/fixtures/<slug>.json` and add a parser test in `tests/test_ingest.py`.

Data that isn't an event or a place (readings, lines) gets a model + Alembic migration and a `Feed`
(`app/ingest/conditions.py`, `routes.py`). Never create tables by hand or with `create_all` on RDS.

## Don't change AWS resources in the console

Everything in AWS is defined in `infra/` (CDK). Console changes drift from it and can break deploys. Example:
turning on "Manage master credentials in Secrets Manager" on the RDS instance rotated the master password
and took both boxes offline. Need DB access? Use your own login (above), never the master user.

## Infrastructure changes

`infra/deploy.sh` (CDK). App code never goes through it: merging is the deploy.
