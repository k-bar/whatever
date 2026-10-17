# Architecture

Syrenka (Warszawa Live) is one live map of everything social in Warsaw. City events, sports classes,
open pitches, venues, ticketed events and amenities appear on one map. People can say "I'm going, come
with me", ask to join others, keep profiles and have friends.

State described here: `dev` at the time of writing (2026-10-18). Prod (`master`) runs an older
commit; see [operations.md](operations.md#environments).

## The pieces

```
                 dane.um.warszawa.pl ──(blocks AWS IPs)──> relay (Poland, Cloudflare tunnel)
                          ▲                                        ▲
 OpenStreetMap Overpass   │                                        │
 kupbilecik.pl            │                                        │
        ▲                 │                                        │
        │      ┌──────────┴───────────── EC2 box (one per env) ────┴──────────────────────┐
        │      │                                                                           │
        ├──────┤ warszawa-ingest.timer   backend/app/ingest/run.py   -> sources, events,   │
        │      │                         (fetchers -> RawEvent -> load) event_occurrences  │
        │      │                         + routes + offline PL->EN translation             │
        │      │ warszawa-conditions.timer app/ingest/conditions.py  -> weather_stations,  │
        │      │                                                        air_stations       │
        └──────┤ warszawa-sync.service   app/ingest/src_sync.py -> Kamil's src/ scheduler  │
               │                         -> raw tables (city_events, toilets, sync_logs…)  │
               │ warszawa-api.service    FastAPI (uvicorn, 2 workers, port 80)             │
               │ warszawa-agent.timer    pull-based deploys (infra/ec2/agent.sh)           │
               └───────────────┬───────────────────────────────────────┬──────────────────┘
                               │ SQL (schema dev or public)            │ HTTP
                               ▼                                       ▼
                 RDS Postgres 16 + PostGIS (shared)        CloudFront (api[-dev].syrenka.me)
                                                                        ▲
                 S3 + CloudFront (syrenka.me / dev.syrenka.me) ──> React UI ──┘
```

- **Backend** (`backend/`): FastAPI + SQLAlchemy 2 + GeoAlchemy2/PostGIS, Alembic migrations, `uv`,
  `ruff`, `pytest`. It serves the API and owns the event pipeline.
- **Kamil's synchronizer** (`src/`, repo root): a standalone Open Data ingestor that writes raw tables. On
  the boxes it runs through `backend/app/ingest/src_sync.py`, which hands it the backend's DB engine and
  the relay. The `src/` code itself is not modified.
- **Frontend** (`frontend/`): React + Vite + MapLibre GL. It is built on the box by `deploy/deploy.sh`
  and published to S3/CloudFront. See [frontend.md](frontend.md).
- **Infra** (`infra/`): AWS CDK (Python), in `eu-north-1` only. **Deploy** (`deploy/`): the on-box deploy
  script and the systemd units. See [operations.md](operations.md).
- **Exploratory** (`backend/db/`): Mateusz's SQLite scrapers. The app doesn't use them.

## Data flow, end to end

1. **Fetch.** Each source in `backend/app/ingest/sources/` has a `SourceSpec`. `fetch_records()` makes
   the network call and `parse(records)` returns `list[RawEvent]` (`app/ingest/base.py`).
2. **Load.** `app/ingest/run.py`:
   - maps the source's labels to our categories (`app/categories.py`);
   - geocodes missing coordinates with Nominatim, cached in `geocode_cache`;
   - drops points outside the Warsaw boundary;
   - upserts into `events` and `event_occurrences`;
   - marks rows the source no longer lists as inactive.

   Past occurrences are kept as history. Occurrences people attend are never deleted.
3. **Translate.** `app/translate.py` turns Polish titles and leads into English with an offline
   Argos/OPUS-MT model (CTranslate2, no API cost). Results go to `events.i18n`, cached per text in
   `text_translations`.
4. **Serve.** The routers in `app/routers/` and `app/userevents/` return GeoJSON for the map plus JSON
   for accounts and the social features. See [api.md](api.md).
5. **Show.** `frontend/src/data/api.js` is the only caller of the API. Pins, boxes, search, profiles.

Parallel to this, Kamil's `src/` keeps its own raw copy of the Open Data sets (with history for
weather and air quality). Only `kupbilecik.py` reads from it, as a fallback. See
[data.md](data.md#two-pipelines).

## Repository map

| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI app, CORS, `/health` |
| `backend/app/config.py` | Settings from env / Secrets Manager (see [operations.md](operations.md#configuration)) |
| `backend/app/models.py` | SQLAlchemy models of the backend's tables |
| `backend/app/schemas.py` | Pydantic request/response models |
| `backend/app/routers/` | `events`, `map`, `users`, `social`, `profiles` |
| `backend/app/userevents/` | Events people create with "+ Create event", plus photo uploads |
| `backend/app/ingest/` | Pipeline: `base.py` (contract), `run.py` (loader), `sources/` (fetchers), `conditions.py`, `routes.py`, `geocode.py`, `src_sync.py` |
| `backend/app/translate.py` | Offline PL->EN translation |
| `backend/app/categories.py` | Category list and label mapping |
| `backend/app/usernames.py` | @username rules |
| `backend/app/busyareas/`, `backend/scripts/build_busy_areas.py` | "Busy areas" polygons, built offline from OSM and committed |
| `backend/alembic/versions/` | Migrations `0001`–`0007` |
| `backend/tests/` | pytest; `fixtures/<slug>.json` are real records per source |
| `src/`, `tests/` (root) | Kamil's synchronizer and its tests |
| `frontend/` | UI; `frontend/scripts/` holds the mermaid icon generator |
| `infra/` | CDK app and stacks; `infra/ec2/` holds the box bootstrap and the deploy agent |
| `deploy/` | `deploy.sh`, `environments.json`, `systemd/` |
| `.github/` | CI, Release, CODEOWNERS, issue and PR templates |
| `docs/` | This documentation, the product plan (`PLAN.md`) |

## Ownership

From `CONTRIBUTING.md` and `.github/CODEOWNERS`:

| Area | Owner |
|---|---|
| Backend, API, infra, deploy | @JustCodeMeV |
| Database schema of the Open Data tables, data sources (`src/`, `backend/app/ingest/sources/`) | Kamil (@kdzwigal) |
| Frontend | Philip (@philpiano) |
| `backend/db/` scrapers | Mateusz (@Informatyczek) |

The backend adapts to Kamil's raw tables, and the UI adapts to the backend.
