# Operations & Local Usage Manual (`man.md`)

This manual covers the datasets, CLI commands, and local usage of the **Warszawa Live Open Data SQL Ingestor** (`src/`).

---

## 1. Datasets & Refresh Schedule

The ingestor reads the catalogue URLs from `dane.txt`, authenticates with the Warsaw Open Data REST API (`https://dane.um.warszawa.pl/api/action/...`) as well as OpenStreetMap Overpass API (`streets_gl`), and persists the data into 12 PostgreSQL tables in the configured `DB_SCHEMA` (`public` by default, `dev` on the dev environment):

| Dataset Key | Schedule Group | Refresh Interval | Strategy | Target Tables |
|---|---|---|---|---|
| `weather` | `fast` | **10 minutes** | Append history (`ON CONFLICT DO NOTHING`) | `weather_measurements` |
| `air_quality` | `fast` | **10 minutes** | Upsert stations + append measurement history | `air_quality_stations`, `air_quality_measurements` |
| `tourist_routes` | `slow` | **2 hours** | Upsert by route title & point ID | `tourist_routes`, `tourist_points` |
| `toilets` | `slow` | **2 hours** | Upsert by `(lokalizacja, lon, lat)` | `toilets` |
| `defibrillators` | `slow` | **2 hours** | Upsert by `defibrillator_id` | `defibrillators` |
| `sports_activities` | `slow` | **2 hours** | Upsert by `url` | `sports_activities` |
| `open_sports_fields` | `slow` | **2 hours** | Upsert by school/address/type/equipment | `open_sports_fields` |
| `city_events` | `slow` | **2 hours** | Upsert by `url` (extracts `lat`, `lon`, `district`) | `city_events` |
| `streets_gl` | `external` / `slow` | **2 hours** | Upsert by OpenStreetMap `id` | `streets_gl_venues` |
| *(Audit Log)* | — | Every sync | Append run status and record count | `sync_logs` |

---

## 2. Local Development Quick Reference

### Start Local PostgreSQL + PostGIS
```bash
docker compose up -d db
# or without Docker:
backend/scripts/dev-postgres.sh start
```
- **Default `DATABASE_URL`:** `postgresql+psycopg://postgres@localhost:54329/warszawa`
- **Target Schema (`DB_SCHEMA`):** defaults to `public` (override with `DB_SCHEMA=dev`)

### CLI Usage
```bash
# Install dependencies in virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Initialize database schema only (in current_schema() per DB_SCHEMA)
.venv/bin/python -m src.main --init-only

# Run one-off full synchronization of all datasets
.venv/bin/python -m src.main

# Run one-off synchronization of a specific group (fast = 10m, slow = 2h, external = streets_gl)
.venv/bin/python -m src.main --group fast
.venv/bin/python -m src.main --group slow
.venv/bin/python -m src.main --group external

# Run one-off synchronization of a single dataset
.venv/bin/python -m src.main --dataset weather

# Run continuous scheduler (weather & air_quality every 10m, others every 2h)
.venv/bin/python -m src.main --watch
```

### Run Verification & Tests
```bash
.venv/bin/flake8 src tests
.venv/bin/mypy src tests
.venv/bin/python -m pytest -v
```

---

## 3. AWS Infrastructure & Deployment

All AWS infrastructure (RDS PostgreSQL in `eu-north-1`, EC2 instances for `dev` and `prod`, CloudFront, and IAM/Secrets Manager) is managed exclusively via AWS CDK in [`infra/`](infra/), and application deployments are automated via [`deploy/deploy.sh`](deploy/deploy.sh).

- **Do not create or modify AWS resources manually in the AWS Console.**
- See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`deploy/`](deploy/) for environment details (`dev` schema vs. `public` schema on RDS), systemd services, and API usage.
