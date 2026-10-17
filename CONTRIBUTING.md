# Working on Warszawa Live

## Who owns what

| Folder | Owner | What goes there |
|---|---|---|
| `backend/app/ingest/sources/` | Kamil (@kdzwigal) | One file per data source: fetch records, turn them into `RawEvent`s |
| `backend/` (everything else) | @JustCodeMeV | Database, loading, API |
| `frontend/` | Philip (@philpiano) | The map UI |
| `infra/`, `deploy/` | @JustCodeMeV | AWS (CDK, Python): RDS, EC2 boxes, CloudFront, domain; on-box deploy scripts |
| `backend/db/` | Mateusz (@Informatyczek) | scrapers (`db/db/fetch_*.py`: Warsaw Open Data, kupbilecik.pl, streets.gl) and their local SQLite snapshots (gitignored; see `db/db/db.md`) |

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

Each environment is one EC2 box running the API, the ingest timer and Kamil's `src/` ingestor (once merged).

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
uv run python scripts/import_sqlite.py db/db/events.db db/db/sport.db   # load Mateusz's snapshots
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

## Using the API (Philip)

- Interactive docs and schemas: `<api-url>/docs`. OpenAPI JSON: `<api-url>/openapi.json`.
- Map: `GET /events?bbox=west,south,east,north&from=&to=&category=music` returns GeoJSON, one feature per occurrence.
- Login: `POST /auth/login` returns `access_token`. Send it as `Authorization: Bearer <token>`.
- Need something else? Open an **API request** issue.

## On the box (needs AWS access to account 015454941566, ask @JustCodeMeV)

No SSH: use Session Manager (`aws ssm start-session --target <instance from deploy/environments.json>`).

```bash
journalctl -u warszawa-agent -f        # deploys
journalctl -u warszawa-api -f          # API
sudo systemctl start warszawa-ingest   # run ingestion now; results in GET /sources
journalctl -u warszawa-ingestor -f     # Kamil's src/ ingestor
```

## Infrastructure changes

`infra/deploy.sh` (CDK). App code never goes through it: merging is the deploy.
