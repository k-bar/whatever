# UI contract: endpoints the frontend calls that the API doesn't serve yet

Collected from Philip's stubs (frontend/src/data/api.js is the caller). Until each one exists,
the UI falls back to client-side logic (no mock data). Implement them as routers
under `app/routers/`, tables via models + Alembic.

## Available now (new map layers)

- `GET /places` now also returns about 450 OpenStreetMap venues (theatres, cinemas, clubs, museums,
  stadiums...), `source: "osm_venues"`, with categories (`theatre`, `film`, `nightlife`, `exhibitions`, ...)
  and `opening_hours` where OSM has them. `open_now=true` handles hours past midnight.
- `GET /places?category=toilets` / `?category=aed`: public toilets (695) and defibrillators (710) as Point
  features, same shape as other places (`opening_hours` for toilets). Plain `/places` leaves them out.
- `GET /conditions` → `{"weather": FeatureCollection, "air": FeatureCollection}`, latest reading per station,
  refreshed every 10 min. Weather props: `temp_air`, `temp_road`, `humidity`, `wind_speed`, `wind_dir`,
  `precipitation`, `measured_at`. Air props: `index` (Polish AQ index, e.g. "Dobry"), `recommendation`,
  `params` (`{"PM10": {"value", "unit", "index", "time"}, ...}`), `measured_at`.
- `GET /routes` → FeatureCollection of LineStrings (tourist routes): `title`, `length_km`, `description`,
  `points` (`[{"id", "name", "lat", "lng"}]`).

## `backend/mapboxes/__init__.py` (removed)

```
Map boxes: the small info card that opens when a pin is clicked.

GET /mapboxes/{event_id} → {"title", "subtitle", "badges": [...], "image", "blocks": [...]}
Block types the UI renders (src/components/MapBox.jsx):
    {"type": "facts",   "items": [{"icon": "clock|pin|map|repeat|users|access|phone", "text": "..."}]}
    {"type": "posters", "items": [{"title", "starts_at", "price", "currency", "availability", "image_url", "url"}]}
    {"type": "social",  "attendees": 3, "wanting": 1, "seats": 2, "capacity": 6, "host": "Ola", "cta": "Ask to join"}
    {"type": "live",    "text": "busy right now", "level": "hot|calm"}
    {"type": "hours",   "text": "Mo-Su 10:00-20:00"}
    {"type": "pitch",   "equipment": [...], "surface": "...", "today": "Od 17:00 do 22:00", "hours": {...}}
    {"type": "text",    "text": "...", "muted": false}
The frontend's src/mapboxes/curate.js produces the same shape locally until this is wired up.
```

## `backend/mapboxes/curate.py` (removed)

```
Curate the most important info for one feature (see package docstring for the block shapes).

def curate(event: Event, *, now: datetime, busy: float | None) -> dict
    - venue with upcoming ticketed events  -> posters block first
    - open pitch                           -> pitch block (which pitches, open today?)
    - park                                 -> "picnics happening now" from public invites nearby
    - nightclub                            -> live busy-now block
    - any event                            -> facts (when / where) + social (going / wants company)
TODO(backend)
```

## `backend/search/__init__.py` (removed)

```
Search endpoints behind the search bar's mode dropdown (Search / Events / Assistant).

The frontend calls GET /search/<mode>?q=... (src/data/api.js → runSearch) and expects:
    {"results": [GeoJSON Feature, ...], "answer": "optional text (assistant only)"}
Until these are wired into app/main.py the frontend filters client-side.
```

## `backend/search/search.py` (removed)

```
GET /search/search?q=  — places, venues, districts, events: everything, ranked.

Expected response: {"results": [GeoJSON Feature, ...]}  (same features as GET /events + /places)
TODO(backend): full-text over title / venue_name / lead / district, bbox optional.
```

## `backend/search/events.py` (removed)

```
GET /search/events?q=  — only things with a date (kind == "event"), soonest first.

Expected response: {"results": [GeoJSON Feature, ...]}
TODO(backend): same as search.py but filtered to occurrences in [now, now+30d].
```

## `backend/search/assistant.py` (removed)

```
GET /search/assistant?q=  — natural-language question, answered with the data.

Expected response: {"answer": "text shown in the results panel", "results": [GeoJSON Feature, ...]}
TODO(backend): LLM call with the matching features as context; keep `results` so the map
can still highlight what the answer talks about.
```

