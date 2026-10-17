"""Mock "busy now" heat points for the UI's heat layer (stand-in for Google "Popular times").

Prints a GeoJSON FeatureCollection of weighted points, dense along the Vistula boulevards and
in Centrum, thinning outwards: {"geometry": {"type": "Point", ...}, "properties": {"weight": 0.8}}.
Frontend fallback copy: frontend/public/mock/busy.geojson (frontend/scripts/build_mock.py).
Once the API serves GET /busy, this becomes a model + migration, not a table created here.

Usage: uv run python scripts/mock_busy_now.py [--seed 7] > busy.geojson
"""

import argparse
import json
import random
from datetime import datetime

HOT = [  # (lng, lat, weight, spread) — Vistula + Centrum heavy
    (21.0400, 52.2400, 1.0, 0.004),
    (21.0360, 52.2300, 0.9, 0.005),
    (21.0200, 52.2300, 1.0, 0.004),
    (21.0120, 52.2200, 0.8, 0.004),
    (21.0180, 52.2240, 0.9, 0.003),
    (21.0060, 52.2320, 0.8, 0.005),
    (21.0160, 52.2490, 0.7, 0.004),
    (21.0350, 52.2530, 0.6, 0.004),
    (21.0440, 52.2460, 0.5, 0.003),
    (20.9960, 52.2130, 0.5, 0.005),
    (21.0270, 52.2140, 0.4, 0.004),
    (20.9850, 52.2320, 0.4, 0.005),
    (20.9800, 52.2690, 0.3, 0.005),
    (21.0450, 52.1960, 0.3, 0.005),
]


def generate(seed=None, hour=None):
    rnd = random.Random(seed)
    hour = datetime.now().hour if hour is None else hour
    evening = 0.6 + 0.4 * (1 if 17 <= hour <= 23 else 0.4)  # busier in the evening
    pts = []
    for lng, lat, w, spread in HOT:
        for _ in range(int(140 * w * evening)):
            pts.append(
                (
                    round(rnd.gauss(lng, spread), 5),
                    round(rnd.gauss(lat, spread * 0.65), 5),
                    round(max(0.15, min(1, rnd.gauss(w, 0.25))), 2),
                )
            )
    for _ in range(400):
        pts.append(
            (
                round(rnd.uniform(20.90, 21.18), 5),
                round(rnd.uniform(52.16, 52.31), 5),
                round(rnd.uniform(0.05, 0.25), 2),
            )
        )
    return pts


def to_geojson(pts):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [x, y]},
                "properties": {"weight": w},
            }
            for x, y, w in pts
        ],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    points = generate(a.seed)
    print(json.dumps(to_geojson(points)))
