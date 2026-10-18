# Data: sources, pipelines, tables

## Two pipelines

The same data arrives through two pipelines. They write different tables:

| | Backend pipeline | Kamil's synchronizer |
|---|---|---|
| Code | `backend/app/ingest/` | `src/` (repo root), launched by `backend/app/ingest/src_sync.py` |
| Writes | `sources`, `events`, `event_occurrences`, `weather_stations`, `air_stations`, `tourist_routes` | raw tables from `src/models.py` (below), `sync_logs` |
| Read by the API | yes, everything the map shows | only `tourist_routes` |
| Schedule | `warszawa-ingest.timer` (prod hourly at `:17`, dev every 6 h at `:37`), `warszawa-conditions.timer` (every 10 min) | `warszawa-sync.service`, a long-running scheduler: weather and air every 10 min, the rest every 2 h |
| Status | `GET /sources` | `sync_logs` table, `journalctl -u warszawa-sync` |

Both pipelines call `dane.um.warszawa.pl`, which drops connections from AWS IPs. Each call goes
through the relay in Poland (see [operations.md](operations.md#warsaw-api-relay)).

## Backend sources (`backend/app/ingest/sources/`)

| Slug | Source | Kind | Refresh | Notes |
|---|---|---|---|---|
| `warsaw_events` | Open Data `get_bmm_kalendarz_wydarzen` (event calendar) | event | every ingest run | ~650 events |
| `warsaw_sport` | Open Data `get_bmm_zajecia_sportowe` (sports classes) | class | every ingest run | ~590 |
| `warsaw_pitches` | Open Data `get_be_otwarte_boiska` (open school pitches) | place | every ingest run | ~1200, opening hours per weekday |
| `warsaw_toilets` | Open Data `get_m_toalety` | place, category `toilets` | every ingest run | hidden from `/places` unless asked for |
| `warsaw_aed` | Open Data `get_scb_lokalizacja_defibrylatorow` | place, category `aed` | every ingest run | hidden from `/places` unless asked for |
| `osm_venues` | OpenStreetMap Overpass (theatres, cinemas, clubs, museums, stadiums…) | place | 24 h | ~450, ODbL, ported from Kamil's streets.gl query |
| `osm_restaurants` | OpenStreetMap Overpass (restaurants, cafes, bars, pubs, biergartens, food courts) | place | 24 h | ODbL (Kamil) |
| `songkick` | songkick.com Warsaw metro listings (JSON-LD `MusicEvent`, up to 5 pages) | event | 6 h | concerts (Kamil) |
| `waw4free` | waw4free.pl Warsaw category pages | event | 4 h | free events, parties, concerts (Kamil) |

Non-event feeds (`Feed` in `app/ingest/conditions.py`):

| Slug | Source | Table | Schedule |
|---|---|---|---|
| `warsaw_weather` | Open Data `get_zom_pogoda` (16 stations) | `weather_stations` (latest per station) | 10 min |
| `warsaw_air` | Open Data `get_bopipk_monitoring_jakosci_powietrza` (~141 stations) | `air_stations` (latest per station) | 10 min |
| `warsaw_routes` | Open Data `get_sbt_trasy_turystyczne` (9 routes) | `tourist_routes` | every ingest run |

### Adding a backend source

See `CONTRIBUTING.md`, section "Adding a data source". In short:

1. Add `fetch_records()` and a pure `parse()`.
2. Register its `SPECS` in `sources/__init__.py`.
3. Commit real records as `backend/tests/fixtures/<slug>.json`.

CI runs every parser against its fixture (`tests/test_contract.py`).

### Loader rules (`app/ingest/run.py`)

- **Upsert key:** `(source_id, external_key)`. `external_key` must stay the same across runs.
- **Categories:** the source's labels go through `LABEL_MAP` and a keyword pass (`app/categories.py`).
  Amenities (`toilets`, `aed`) skip the keyword pass.
- **Coordinates:** missing coordinates are geocoded through Nominatim, cached in `geocode_cache`. The
  number of lookups per source is capped by `--geocode-limit`: 200 on prod, 30 on dev. Points outside
  `app/data/warsaw_boundary.geojson` are dropped.
- **Removals:** a row the source stops listing gets `is_active = false`. An upcoming occurrence that
  disappears is deleted, unless someone attends it or has asked to join it. Finished occurrences are
  kept as history.
- **Slow sources:** a source with `refresh_hours > 0` is skipped while its last success is recent.
- **Translation:** at the end of each run, up to 3000 events are translated PL->EN (`app/translate.py`).
  Only Polish texts are translated; English originals are kept. The model lives on the box in
  `/opt/warszawa/models/translate-pl_en-1_9`; `deploy.sh` downloads it once and checks its sha256.

## Kamil's synchronizer (`src/`)

Datasets come from `dane.txt` (Open Data catalogue URLs) plus OpenStreetMap (`streets_gl`):

| Key | Tables | Strategy |
|---|---|---|
| `weather` | `weather_measurements` | history, `(lokalizacja, czas)` |
| `air_quality` | `air_quality_stations`, `air_quality_measurements` | stations upserted, measurement history |
| `tourist_routes` | `tourist_routes`, `tourist_points` | upsert by title / point id |
| `toilets` | `toilets` | upsert by `(lokalizacja, lon, lat)` |
| `defibrillators` | `defibrillators` | upsert by `defibrillator_id` |
| `sports_activities` | `sports_activities` | upsert by `url` |
| `open_sports_fields` | `open_sports_fields` | upsert by school / address / type / equipment |
| `city_events` | `city_events` | upsert by `url` |
| `streets_gl` | `streets_gl_venues` | upsert by OSM id |
| restaurants | `restaurants` | OSM restaurants, cafes, bars |
| entertainment | `entertainment_events` | Songkick + Waw4Free events |

The tables are created by Alembic migration `0007` in the environment's schema, not by `create_all`.
`src/` honours `DB_SCHEMA` (default `public`, which is prod): when running `python -m src.main` by hand
against RDS, always set `DB_SCHEMA=dev`. Kamil's own docs: `API.md` (Polish) and `man.md` (see [known-issues.md](known-issues.md)).

## Tables

The database is one RDS instance; each environment has its own schema (`public` = prod, `dev` = dev).

### Backend (`backend/app/models.py`, `backend/app/userevents/models.py`)

| Table | What |
|---|---|
| `sources` | One row per backend source: `last_status`, `last_run_at`, `last_error`, `item_count` |
| `events` | Every event, class and place (`kind`), with PostGIS `location`, `categories`, `opening_hours`, `contact`, `i18n`, the source's `raw` record |
| `event_occurrences` | Dates of an event (`starts_at`, `ends_at`, `daily`); unique per `(event_id, starts_at)` |
| `users` | Accounts: email, password hash, `display_name`, `username` (unique), `gender`, `bio`, `photos`, `interests`, `links`, `hangouts`, `favourite_ids` |
| `attendance` | "I'm going" per user and occurrence, `wants_company`, `max_group` |
| `join_requests` | Requests to join someone at an occurrence, with status |
| `friendships` | One row per pair of people; `pending` or `accepted` |
| `user_events`, `user_event_photos` | Events people create in the app, and uploaded photos (profile pictures use them too) |
| `geocode_cache` | Nominatim results |
| `text_translations` | Translated text, keyed by the original |
| `weather_stations`, `air_stations` | Latest reading per station (`GET /conditions`) |
| `tourist_routes` | In Kamil's shape (`traces`, `tourist_points` JSONB); `GET /routes` builds the LineStrings when it reads them |

### Kamil's (`src/models.py`)

`tourist_routes`, `tourist_points`, `toilets`, `weather_measurements`, `defibrillators`,
`sports_activities`, `open_sports_fields`, `city_events`, `air_quality_stations`,
`air_quality_measurements`, `sync_logs`, `streets_gl_venues`, `restaurants`, `entertainment_events`.
Column lists: `API.md`, section 2.

### Migrations (`backend/alembic/versions/`)

| Rev | What |
|---|---|
| `0001` | Initial schema: sources, events, occurrences, users, attendance, join requests, geocode cache |
| `0002` | Weather stations, air stations, tourist routes |
| `0003` | User events and photos |
| `0004` | Translations (`events.i18n`, `text_translations`) |
| `0005` | `users.favourite_ids` |
| `0006` | Profiles: `username`, `gender`, `hangouts`; `friendships` |
| `0007` | Kamil's raw tables; `tourist_routes` takes his shape |
| `0008` | kupbilecik removed: drop `kupbilecik_events`, its events marked inactive |
| `0009` | `users.first_name`, `last_name`, `age` (private, `/me` only) |
| `0010` | Kamil's `restaurants` and `entertainment_events` |

`deploy.sh` runs `alembic upgrade head` in the box's schema on every deploy. CI runs `alembic upgrade
head && alembic check` on an empty database, so models and migrations must match.

## Categories (`backend/app/categories.py`, mirrored in `frontend/src/data/categories.js`)

`music`, `nightlife`, `theatre`, `film`, `exhibitions`, `meetups`, `grzybki`, `study_buddies`, `running`,
`yoga`, `sports`, `festivals`, `markets`, `culture`, `education`, `family`, `business`, `health`, `other`,
plus the amenities `toilets` and `aed`. Colours exist only in the frontend.
