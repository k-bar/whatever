"""Busy areas: detailed outlines of where in Warsaw people are most likely to bump into each other.

GET /busyareas → GeoJSON FeatureCollection of Polygons (the golden areas on the map)
    properties: {"id": "busy-01", "name": "Chmielna / Nowy Świat", "level": "busy" | "very_busy",
                 "parent": "busy-01" (cores only), "score": 1489.5, "venues": 830, "area_km2": 2.36,
                 "mix": {"restaurants": 430, "cafés": 171, ...}, "why": "430 restaurants, ... in 2.36 km²"}
    A "very_busy" core sits inside its "busy" parent. Features are sorted busiest first.

The data is built offline from OpenStreetMap by build_busy_areas.py (see README.md) and committed as
busy_areas.geojson, so serving it is just a file read.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "busy_areas.geojson"


@lru_cache(maxsize=1)
def load() -> dict:
    """The busy-areas FeatureCollection, ready to return from GET /busyareas."""
    return json.loads(DATA.read_text(encoding="utf-8"))
