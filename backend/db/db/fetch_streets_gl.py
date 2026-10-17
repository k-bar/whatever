"""Fetches event venues from OpenStreetMap and saves them to SQLite (street_gl.db).

streets.gl is a 3D renderer of OpenStreetMap and has no events of its own, so
this pulls the OSM data it displays: places where events happen (theatres,
cinemas, concert halls, clubs, museums, galleries, stadiums, ...) through the
Overpass API. OSM has no event dates; "time" is the venue's opening_hours.

Usage:
    python fetch_streets_gl.py                    # Warszawa
    python fetch_streets_gl.py --city "Kraków"
"""

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

OVERPASS = "https://overpass-api.de/api/interpreter"
HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "street_gl.db"
USER_AGENT = "HackatonEventsBot/1.0"

# OSM key -> values that mark an event venue
VENUE_TAGS = {
    "amenity": ["theatre", "cinema", "arts_centre", "concert_hall", "music_venue",
                "events_venue", "nightclub", "conference_centre", "exhibition_centre"],
    "leisure": ["stadium"],
    "tourism": ["museum", "gallery"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS venues (
    id             TEXT PRIMARY KEY,  -- "node/123", "way/456", "relation/789"
    name           TEXT,
    category       TEXT,              -- theatre / cinema / museum / ...
    location       TEXT,              -- "Chmielna 33, 00-021 Warszawa"
    street         TEXT,
    housenumber    TEXT,
    postcode       TEXT,
    city           TEXT,
    lat            REAL,
    lon            REAL,
    time           TEXT,              -- OSM opening_hours, e.g. "Tu-Su 10:00-18:00"
    website        TEXT,
    phone          TEXT,
    email          TEXT,
    wheelchair     TEXT,
    capacity       TEXT,
    osm_url        TEXT,
    streets_gl_url TEXT,              -- the venue in the streets.gl 3D map
    tags_json      TEXT,              -- all OSM tags
    fetched_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_venues_category ON venues(category);
"""


def build_query(city):
    parts = []
    for key, values in VENUE_TAGS.items():
        parts.append(f'nwr["{key}"~"^({"|".join(values)})$"](area.a);')
    return (
        "[out:json][timeout:180];"
        f'area["name"="{city}"]["boundary"="administrative"]->.a;'
        f"({''.join(parts)});out center tags;"
    )


def fetch(city):
    data = urllib.parse.urlencode({"data": build_query(city)}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.load(resp)["elements"]


def category(tags):
    for key, values in VENUE_TAGS.items():
        if tags.get(key) in values:
            return tags[key]
    return None


def to_row(el, fetched_at):
    tags = el.get("tags", {})
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    street = tags.get("addr:street") or tags.get("addr:place")
    number = tags.get("addr:housenumber")
    postcode = tags.get("addr:postcode")
    city = tags.get("addr:city")
    line1 = " ".join(p for p in (street, number) if p)
    line2 = " ".join(p for p in (postcode, city) if p)
    osm_id = f"{el['type']}/{el['id']}"
    return {
        "id": osm_id,
        "name": tags.get("name"),
        "category": category(tags),
        "location": ", ".join(p for p in (line1, line2) if p) or None,
        "street": street,
        "housenumber": number,
        "postcode": postcode,
        "city": city,
        "lat": lat,
        "lon": lon,
        "time": tags.get("opening_hours"),
        "website": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "email": tags.get("email") or tags.get("contact:email"),
        "wheelchair": tags.get("wheelchair"),
        "capacity": tags.get("capacity"),
        "osm_url": f"https://www.openstreetmap.org/{osm_id}",
        "streets_gl_url": f"https://streets.gl/#{lat:.5f},{lon:.5f},45.00,0.00,500.00" if lat else None,
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "fetched_at": fetched_at,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--city", default="Warszawa")
    ap.add_argument("--include-unnamed", action="store_true")
    args = ap.parse_args()

    fetched_at = datetime.now().isoformat(timespec="seconds")
    rows = [to_row(el, fetched_at) for el in fetch(args.city)]
    if not args.include_unnamed:
        rows = [r for r in rows if r["name"]]

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    cols = list(rows[0]) if rows else []
    conn.executemany(
        f"INSERT OR REPLACE INTO venues ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [[r[c] for c in cols] for r in rows],
    )
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    conn.close()
    print(f"Done: {len(rows)} venues from {args.city}, {total} rows in {args.db}")


if __name__ == "__main__":
    main()
