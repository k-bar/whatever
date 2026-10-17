"""Mock "busy now" heat points → Postgres `dev` schema (+ GeoJSON on stdout).

Usage:
    python busy_now.py                       # print GeoJSON only
    DATABASE_URL=postgresql://... python busy_now.py --db   # also upsert into dev.busy_now
Only the standard library is required unless --db is used (then psycopg).
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone

HOT = [  # (lng, lat, weight, spread) — Vistula + Centrum heavy
    (21.0400, 52.2400, 1.0, 0.004), (21.0360, 52.2300, 0.9, 0.005), (21.0200, 52.2300, 1.0, 0.004),
    (21.0120, 52.2200, 0.8, 0.004), (21.0180, 52.2240, 0.9, 0.003), (21.0060, 52.2320, 0.8, 0.005),
    (21.0160, 52.2490, 0.7, 0.004), (21.0350, 52.2530, 0.6, 0.004), (21.0440, 52.2460, 0.5, 0.003),
    (20.9960, 52.2130, 0.5, 0.005), (21.0270, 52.2140, 0.4, 0.004), (20.9850, 52.2320, 0.4, 0.005),
    (20.9800, 52.2690, 0.3, 0.005), (21.0450, 52.1960, 0.3, 0.005),
]


def generate(seed=None, hour=None):
    rnd = random.Random(seed)
    hour = datetime.now().hour if hour is None else hour
    evening = 0.6 + 0.4 * (1 if 17 <= hour <= 23 else 0.4)  # busier in the evening
    pts = []
    for lng, lat, w, spread in HOT:
        for _ in range(int(140 * w * evening)):
            pts.append((round(rnd.gauss(lng, spread), 5), round(rnd.gauss(lat, spread * 0.65), 5),
                        round(max(0.15, min(1, rnd.gauss(w, 0.25))), 2)))
    for _ in range(400):
        pts.append((round(rnd.uniform(20.90, 21.18), 5), round(rnd.uniform(52.16, 52.31), 5), round(rnd.uniform(0.05, 0.25), 2)))
    return pts


def to_geojson(pts):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": {"weight": w}} for x, y, w in pts]}


def write_db(pts, url):
    import psycopg  # noqa: PLC0415

    with psycopg.connect(url) as con, con.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS dev")
        cur.execute("""CREATE TABLE IF NOT EXISTS dev.busy_now (
            id SERIAL PRIMARY KEY, lng DOUBLE PRECISION, lat DOUBLE PRECISION, weight REAL, generated_at TIMESTAMPTZ)""")
        cur.execute("TRUNCATE dev.busy_now")
        now = datetime.now(timezone.utc)
        cur.executemany("INSERT INTO dev.busy_now (lng, lat, weight, generated_at) VALUES (%s, %s, %s, %s)",
                        [(x, y, w, now) for x, y, w in pts])
    print(f"dev.busy_now: {len(pts)} rows", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="also write to the dev schema (DATABASE_URL)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    points = generate(a.seed)
    if a.db:
        url = os.environ.get("DATABASE_URL") or sys.exit("DATABASE_URL not set")
        write_db(points, url)
    print(json.dumps(to_geojson(points)))
