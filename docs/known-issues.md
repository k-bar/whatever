# Known issues and cleanup backlog

This is the state of `dev` on 2026-10-18 and the input for the cleanup and normalization pass. Each
item names the files involved. Unless it says "decide", it can be fixed without a product decision.

## Duplication

1. **Two ingestion pipelines for the same Open Data.** Backend `app/ingest/` (→ `events`,
   `weather_stations`, `air_stations`) and Kamil's `src/` (→ `city_events`, `sports_activities`,
   `open_sports_fields`, `toilets`, `defibrillators`, `weather_measurements`, `air_quality_*`) each call
   the same 8 Open Data endpoints. That doubles the relay traffic. The API reads only the backend's
   tables, apart from `tourist_routes`.
   **Decide:** which one is the single source of truth, then have the other read from it instead of
   fetching. Kamil owns the schema, so a natural end state is for the backend sources to read Kamil's
   raw tables.
2. **Overlapping tables:**

   | Backend | Kamil |
   |---|---|
   | `weather_stations` (latest) | `weather_measurements` (history) |
   | `air_stations` (latest) | `air_quality_stations` + `air_quality_measurements` |
   | `events` (osm_venues, warsaw_toilets, warsaw_aed) | `streets_gl_venues`, `toilets`, `defibrillators` |

3. **OSM venues fetched twice:** `osm_venues` (backend, daily) and `streets_gl` (`src/`, every 2 h, the
   same Overpass query).
4. **Profile code from three sessions:** Mateusz's profile tab (#27) was replaced by Philip's
   `ProfilePage` (#28). Polish strings that nothing uses any more remain in `frontend/src/i18n/pl.js`
   ("Personal details", "Going to", "Been to", "Favourite places", …). Remove them.

## Stale or contradicting docs

5. **`API.md`** (root, Kamil) is the implementation plan of `src/` in Polish. It isn't the API: the HTTP
   API is in [api.md](api.md). Rename it, e.g. `src/README.md`.
6. **`backend/UI_CONTRACT.md`** lists endpoints "the API doesn't serve yet", but most of them now exist
   or have been dropped. [api.md](api.md) replaces it, so delete it.
7. **`frontend/README.md`** still lists `/search/{mode}`, `/mapboxes/{id}` and `GET|PUT /ui/settings`,
   which were removed in #26. It also says to remove `<InterfaceEditor>` when leaving dev, but that's
   handled by `DEV_TOOLS`. `frontend/vite.config.js` has a comment about a mock-data fallback that no
   longer exists.
8. **`backend/db/db.md`** describes Mateusz's SQLite scrapers. One of them (streets.gl) now exists in production form twice
    (item 3).

## Repo hygiene

9. **Root files that belong to `src/`:** `requirements.txt` (`requests`, flake8, mypy), `dane.txt`,
    `tests/`. `src/` has no CI: its tests, flake8 and mypy never run on PRs. **Decide:** move `src/` under
    `backend/` with uv and ruff, or give it a CI job.
10. **`backend/busyareas/_cache/osm.json`** (3.1 MB) is a build cache that's committed. Keep only the
    built GeoJSON.
11. **11 merged `vrouxel/*` branches** are still on the remote. Delete them with
    `git push origin --delete <branch>`.
12. **Local, ignored but present:** `apiKey.txt`, `backend/db/apiKey.txt` (the old leaked token),
    `events.db`, `sport.db`. Delete them locally.

## Backend correctness

13. **The translation step handles all 3000 events on every run.** Each dev ingest logs `translate: 3000
    of 3000 events` and uses ~14 min of CPU. `translate.pending()` should only return events whose text
    changed. Check how `events.i18n["for"]` is compared with `source_text()`. 3000 is also a hard cap:
    prod has more events than that.
14. **Memory on the dev box:** with `warszawa-sync` running, about 170 MB of 916 MB was free during an
    ingest. Prod will need the same headroom once it runs the sync. Watch it, or move to `t4g.small`.

## Security and privacy

15. **Rotate the leaked credentials:** the Warsaw API token in git history (`8efa955`) and Kamil's old IAM
    access key. Not done yet, on purpose: the owner decides when.
16. **CORS is `*`** (`cors_origins` default; no override on the boxes). Restrict it to the two website
    origins and `localhost:5173`.
17. **`GET /people/search`** works without a login and returns up to 10 public profiles per query.
    **Decide:** require a login.
18. **`jwt_secret` has an insecure default.** It's only used when no `JWT_SECRET_ARN` is set, which is
    correct on the boxes. Make the app refuse to start in `dev`/`prod` without it.

## Process

19. **Prod is behind dev.** Prod runs `a9e7a8e` and doesn't yet have profiles and friends, Kamil's tables
    and sync, the city layers, or the repo cleanup. Its next promotion runs migrations `0006`–`0008`,
    and starts `warszawa-sync` on prod for the first time.
20. **Several agents and sessions push to the same repo at night.** Twice, two migrations got the same
    number (`0006`). Before adding a migration, check `backend/alembic/versions/` on the latest `dev`.
