# backend/app/busyareas

The golden areas on the map: detailed outlines of the parts of Warsaw where people are most likely
to bump into each other and make new friends. They replace the old rectangular "high-traffic boxes".

| file | what |
|---|---|
| `busy_areas.geojson` | the data (committed). Served as `GET /busyareas`, copied to `frontend/public/mock/busy_areas.geojson` as the offline fallback |
| `../../scripts/build_busy_areas.py` | rebuilds it from OpenStreetMap (stdlib only) |
| `__init__.py` | `load()` for the API, plus the property contract |
| `../../scripts/_cache/osm.json` | raw Overpass download (gitignored) |

## How the outlines are made
1. **Pull from OpenStreetMap (Overpass):** bars, pubs, clubs, cafés, restaurants, cinemas, theatres,
   culture venues, markets, squares, train and metro stations, sights and pedestrian streets.
2. **Weight them** by how many people each puts on the street (a nightclub counts 3, a café 1, fast food 0.4,
   a pedestrian street 0.35 every 25 m). Pedestrian streets and sights only **boost** places that already
   have venues, so park alleys and cemetery paths don't light up on their own.
3. **Density surface:** a Gaussian kernel (σ = 110 m) on a 40 m grid.
4. **Outlines:** marching squares at two thresholds, giving `busy` (the area) and `very_busy` (its core).
   Then Douglas-Peucker simplification and Chaikin smoothing.
5. **Names:** the streets and plazas most of the venues inside are on (e.g. "Chmielna / Nowy Świat").

```bash
python3 backend/scripts/build_busy_areas.py            # uses the cache
python3 backend/scripts/build_busy_areas.py --refresh  # re-download OSM (~40 s)
python3 backend/scripts/build_busy_areas.py --stats    # density percentiles, to tune --busy / --very
```

Thresholds default to `--busy 18 --very 45` (about the city's top 2% and top 0.5% of social density).
Going lower merges the whole centre into one blob.

## Next
This is a static "where it's usually busy" layer. Once we have live signals (Google Popular Times,
check-ins, events starting now), use them to scale `score` by time of day, and to hide or show areas.

Data © OpenStreetMap contributors, ODbL.
