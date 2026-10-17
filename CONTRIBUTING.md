# Working on Warszawa Live

## Who owns what

| Folder | Owner | What goes there |
|---|---|---|
| `backend/app/ingest/sources/` | Kamil (@kdzwigal) | One file per data source: fetch records, turn them into `RawEvent`s |
| `backend/` (everything else) | @JustCodeMeV | Database, loading, API |
| `frontend/` | Philip (@philpiano) | The map UI |
| `infra/`, `deploy/` | @JustCodeMeV | AWS (CDK, Python): RDS, EC2 boxes, CloudFront, domain; on-box deploy scripts |
| `backend/db/` | Mateusz (@Informatyczek) | scrapers (`db/fetch_*.py`: Warsaw Open Data, kupbilecik.pl, streets.gl) and their local SQLite snapshots (gitignored; see `db/db.md`) |

```
fetchers (sources/*.py) ── list[RawEvent] ──> ingest/run.py ──> RDS Postgres ──> FastAPI ──> UI
              hourly systemd timer on the EC2 box     (AWS eu-north-1)    same EC2 box, behind CloudFront
```

## Environments

| | dev | prod |
|---|---|---|
| Git branch | `dev` | `master` |
| API | see `deploy/environments.json` | see `deploy/environments.json` |
| Website | see `deploy/environments.json` | see `deploy/environments.json` |
| Database | RDS, schema `dev` | same RDS, schema `public` |

Each environment is one EC2 box running the API, the hourly ingest timer and the 10-minute conditions timer.

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
uv run python scripts/import_sqlite.py db/events.db db/sport.db   # load Mateusz's snapshots
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

## Using the API / Fetching data from AWS RDS (Philip & consumers)

The entire backend runs on EC2 in the same AWS VPC (`eu-north-1`) as the PostgreSQL RDS instance (`warszawa`) and serves data directly from RDS behind CloudFront:

- **Dev API** (reads from RDS schema `dev`): `https://api-dev.syrenka.me`
- **Prod API** (reads from RDS schema `public`): `https://api.syrenka.me`
- **Interactive docs & schemas**: `<api-url>/docs` | **OpenAPI JSON**: `<api-url>/openapi.json`

### Endpoints reading from AWS RDS

| Endpoint | Description | Key query parameters |
|---|---|---|
| `GET /events` | GeoJSON `FeatureCollection` of events & classes (one feature per occurrence) | `bbox=west,south,east,north`, `from=ISO8601`, `to=ISO8601`, `category=music,sport,...`, `kind=event\|class\|place`, `q=<search>`, `district=<name>`, `free_only=true`, `lang=pl\|en`, `limit=1000` |
| `GET /events/now` | GeoJSON `FeatureCollection` of events happening right now or starting within `within_hours` | `within_hours=3` (`1`–`24`), `lang=pl\|en` |
| `GET /events/{id}` | Full details of a single event / place / class (including all occurrences and social counts) | `lang=pl\|en` |
| `GET /places` | GeoJSON `FeatureCollection` of static places & amenities (AEDs, public toilets, open pitches, OSM venues) | `bbox=west,south,east,north`, `category=sport,utility,culture,...`, `q=<search>`, `district=<name>`, `lang=pl\|en` |
| `GET /conditions` | Latest weather (`weather_stations`) and air quality (`air_stations`) readings from RDS as GeoJSON points + summary | — |
| `GET /routes` | Tourist routes (`tourist_routes` LineStrings) from RDS as GeoJSON `FeatureCollection` | `lang=pl\|en` |
| `GET /sources` | Ingestion status (`last_status`, `last_run_at`, `item_count`) for all registered RDS data sources (`warsaw_events`, `kupbilecik`, `osm_venues`, `warsaw_sport`, `warsaw_pitches`, `warsaw_aed`, `warsaw_toilets`, `warsaw_air`, `warsaw_weather`, `warsaw_routes`) | — |
| `GET /categories` | Available map categories (`music`, `art`, `film`, `theatre`, `sport`, `science`, `kids`, `food`, `market`, `tour`, `workshop`, `party`, `talks`, `outdoor`, `community`, `utility`, `other`) | `lang=pl\|en` |
| `GET /busy-areas` | GeoJSON polygons of busy areas in Warsaw | — |

### Example API requests (`curl`)

```bash
# 1. Check all RDS data sources and record counts
curl -s https://api-dev.syrenka.me/sources | jq

# 2. Fetch upcoming events in Warsaw (GeoJSON)
curl -s "https://api-dev.syrenka.me/events?limit=100&lang=pl" | jq '.features | length'

# 3. Filter events by bounding box and category (e.g. music & theatre)
curl -s "https://api-dev.syrenka.me/events?bbox=20.85,52.10,21.27,52.37&category=music,theatre" | jq

# 4. Fetch static places/amenities (AEDs, toilets, open pitches, OSM venues)
curl -s "https://api-dev.syrenka.me/places?category=utility,sport" | jq

# 5. Fetch current weather & air quality conditions and tourist routes
curl -s https://api-dev.syrenka.me/conditions | jq '.summary'
curl -s https://api-dev.syrenka.me/routes | jq
```

- Login: `POST /auth/login` returns `access_token`. Send it as `Authorization: Bearer <token>`.
- Need something else? Open an **API request** issue.

## On the box & EC2 + RDS deployment setup (needs AWS access to account 015454941566, ask @JustCodeMeV)

> **Important for whoever deploys on EC2:** The entire backend (`warszawa-api`, `warszawa-ingest`, `warszawa-conditions`, and the `src/` RDS synchronizer) runs on the EC2 instance in the **same AWS VPC (`eu-north-1`) as the RDS PostgreSQL database** (`warszawalivedb-postgres9dc8bb04-covqyqx6uo8t.cba6qiu6ipoi.eu-north-1.rds.amazonaws.com`, database `warszawa`). It connects directly to RDS over the internal AWS network (never through a developer laptop tunnel). Whoever deploys or provisions the EC2 box must make sure the environment, schema migrations, and systemd timers are configured as described below.

1. **Environment configuration (`/etc/warszawa/instance.env`) on the EC2 box** — must be present before running `deploy/deploy.sh` or starting the systemd services:
   ```ini
   APP_ENV=dev                                 # "dev" or "prod"
   DB_SCHEMA=dev                               # "dev" on the dev EC2 box, "public" on prod
   DATABASE_URL=postgresql+psycopg://<db_user>:<db_password>@warszawalivedb-postgres9dc8bb04-covqyqx6uo8t.cba6qiu6ipoi.eu-north-1.rds.amazonaws.com:5432/warszawa?sslmode=require
   WARSAW_API_TOKEN=<api-key-for-dane.um.warszawa.pl>
   INGEST_GEOCODE_LIMIT=200
   INGEST_SCHEDULE=*-*-* *:05:00
   API_URL=https://api-dev.syrenka.me          # or https://api.syrenka.me on prod
   ```
2. **Database migrations & systemd services (`deploy/deploy.sh`)** — when deploying on EC2, ensure:
   - Alembic migrations are applied to the target RDS schema: `cd backend && .venv/bin/alembic upgrade head`
   - All 13 raw/historical tables in RDS (`tourist_routes`, `tourist_points`, `toilets`, `weather_measurements`, `defibrillators`, `sports_activities`, `open_sports_fields`, `city_events`, `air_quality_stations`, `air_quality_measurements`, `kupbilecik_events`, `streets_gl_venues`, `sync_logs`) are initialized and synced:
     ```bash
     DB_SCHEMA=dev DATABASE_URL="..." WARSAW_API_KEY="..." python -m src.main
     ```
   - The systemd services and timers are enabled and running so `events`, `event_occurrences`, `sources`, `weather_stations`, `air_stations`, and `tourist_routes` in RDS stay populated for FastAPI:
     ```bash
     sudo systemctl enable --now warszawa-api.service
     sudo systemctl enable --now warszawa-ingest.timer
     sudo systemctl enable --now warszawa-conditions.timer
     ```

No SSH: use Session Manager (`aws ssm start-session --target <instance from deploy/environments.json>`).

```bash
journalctl -u warszawa-agent -f        # deploys
journalctl -u warszawa-api -f          # API
sudo systemctl start warszawa-ingest   # run ingestion now (including kupbilecik, osm_venues, warsaw_*); results in GET /sources
sudo systemctl start warszawa-conditions  # refresh weather + air quality now
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

Fetchers live in `backend/app/ingest/sources/` and never touch the database:

1. Write `fetch_records()` (network; Warsaw Open Data goes through `warsaw_open_data.fetch(action)`, which
   handles the API key and the relay) and a pure `parse(records) -> list[RawEvent]` (`app/ingest/base.py`).
2. Add your `SPECS` to `app/ingest/sources/__init__.py`.
3. Save a few real records as `backend/tests/fixtures/<slug>.json` and add a parser test in `tests/test_ingest.py`.

Data that isn't an event or a place (readings, lines) gets a model + Alembic migration and a `Feed`
(`app/ingest/conditions.py`, `routes.py`). Never create tables by hand or with `create_all`.

## Don't change AWS resources in the console

Everything in AWS is defined in `infra/` (CDK). Console changes drift from it and can break deploys. Example:
turning on "Manage master credentials in Secrets Manager" on the RDS instance rotated the master password
and took both boxes offline. Need DB access? Use your own login (above), never the master user.

## Infrastructure changes

`infra/deploy.sh` (CDK). App code never goes through it: merging is the deploy.
