# Syrenka (Warszawa Live)

One live map of everything social happening in Warsaw: city events, sports classes, open pitches,
venues, plus "I'm going, come with me" to find company. Product plan: [`docs/PLAN.md`](docs/PLAN.md).

| | prod | dev |
|---|---|---|
| Website | https://syrenka.me | https://dev.syrenka.me |
| API | https://api.syrenka.me/docs | https://api-dev.syrenka.me/docs |
| Branch | `master` | `dev` |

## Repository

| Folder | What |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + PostGIS API (`app/`), Alembic migrations, the ingest pipeline (`app/ingest/`), tests |
| `backend/app/ingest/sources/` | One file per data source (Warsaw Open Data, OpenStreetMap, ...) |
| `src/`, `tests/` | Kamil's Open Data synchronizer (raw tables), run on the boxes by `backend/app/ingest/src_sync.py` |
| `backend/db/` | Exploratory scrapers and local SQLite snapshots; not used by the app (see `backend/db/db.md`) |
| `frontend/` | React + Vite + MapLibre UI (see `frontend/README.md`) |
| `infra/` | AWS CDK (Python): EC2 boxes, RDS, CloudFront, DNS |
| `deploy/` | On-box deploy script and systemd units (API, ingest, conditions, Kamil's sync) |
| `docs/` | Documentation: architecture, data, API, frontend, operations, known issues |

## Documentation

Start at [`docs/README.md`](docs/README.md): [architecture](docs/architecture.md), [data](docs/data.md),
[API](docs/api.md), [frontend](docs/frontend.md), [operations](docs/operations.md),
[known issues / cleanup backlog](docs/known-issues.md).

## Getting started

How to run things locally, the branch and PR flow, who owns what, and how to add a data source:
[`CONTRIBUTING.md`](CONTRIBUTING.md).
