# backend/mock

Mock data for things we don't have a live API for yet. Everything here writes to the
**`dev` schema** of Postgres (never `public`), so it is safe to run against the shared DB.

- `busy_now.py` – stand-in for Google Maps "Popular times / busy now". Generates realistic
  weighted points (dense along the Wisła boulevards and in Centrum, thinning outwards) into
  `dev.busy_now(lng, lat, weight, generated_at)` and prints the GeoJSON the frontend heat layer
  expects: `{"type":"FeatureCollection","features":[{"geometry":{"type":"Point","coordinates":[lng,lat]},"properties":{"weight":0.8}}]}`

Frontend fallback copy: `frontend/public/mock/busy.geojson` (built by `frontend/scripts/build_mock.py`).
Serve it from `GET /busy` once the API exists.
