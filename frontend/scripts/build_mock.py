"""Build the frontend's offline mock data from the SQLite databases in backend/db.

Output (gitignored, regenerate with `npm run mock`):
    frontend/public/mock/features.geojson   events + venues + pitches, same props as GET /events
    frontend/public/mock/busy.geojson       mock "busy now" heat points (Google Popular Times stand-in)
    frontend/public/mock/sources.json       same shape as GET /sources

The GeoJSON property names follow backend/app/routers/events.py (feature()) so the UI
can switch to the real API by flipping VITE_API_URL without touching components.
"""

import json
import math
import random
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = ROOT / "backend" / "db"
OUT = HERE.parent / "public" / "mock"
OUT.mkdir(parents=True, exist_ok=True)
random.seed(7)
NOW = datetime.now()

# --- category mapping (mirrors backend/app/categories.py) --------------------------------------
LABEL_MAP = {
    "kultura": "culture", "historia": "culture", "sport": "sports", "czas wolny": "meetups",
    "edukacja": "education", "dla dzieci": "family", "biznes": "business", "zdrowie": "health",
    "społeczeństwo": "meetups", "bieganie": "running", "joga": "yoga", "taniec": "music",
    "fitness": "sports", "boisko": "sports",
}
KEYWORDS = [
    (re.compile(r"koncert|muzyk|jazz|recital|orkiestr", re.I), "music"),
    (re.compile(r"spektakl|teatr|premier|kabaret|stand.?up|komedi", re.I), "theatre"),
    (re.compile(r"\bfilm|kino|seans", re.I), "film"),
    (re.compile(r"wystaw|galeri|muzeum|ekspozycj", re.I), "exhibitions"),
    (re.compile(r"festiwal|festyn|piknik", re.I), "festivals"),
    (re.compile(r"jarmark|targ|kiermasz|bazar", re.I), "markets"),
    (re.compile(r"\bjog[aiy]|yoga", re.I), "yoga"),
    (re.compile(r"\bbieg|run\b|maraton", re.I), "running"),
    (re.compile(r"grzyb", re.I), "grzybki"),
    (re.compile(r"\bparty|impreza|\bdj\b|clubbing|nocne", re.I), "nightlife"),
]
VENUE_CAT = {
    "museum": "exhibitions", "gallery": "exhibitions", "exhibition_centre": "exhibitions",
    "arts_centre": "culture", "theatre": "theatre", "cinema": "film", "nightclub": "nightlife",
    "events_venue": "music", "stadium": "sports", "conference_centre": "business",
}


def categories(labels, title=""):
    out = []
    for label in labels:
        slug = LABEL_MAP.get(label.strip().lower())
        if slug and slug not in out:
            out.append(slug)
    for pat, slug in KEYWORDS:
        if pat.search(title or "") and slug not in out:
            out.append(slug)
    return out or ["other"]


def rows(db, sql):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


features = []
fid = 0


def add(lng, lat, props):
    global fid
    fid += 1
    features.append({"type": "Feature", "id": fid, "geometry": {"type": "Point", "coordinates": [lng, lat]},
                     "properties": props})


# --- 1. Warsaw open data events ------------------------------------------------------------------
events = rows(DB / "db" / "events.db",
              "SELECT * FROM events WHERE has_coordinates=1 AND is_finished=0 AND next_starts_at IS NOT NULL")
for e in events:
    cats = categories((e["categories"] or "").split("; "), e["title"])
    add(e["lon"], e["lat"], {
        "event_id": e["id"], "kind": "event", "title": e["title"], "categories": cats,
        "lead": e["lead"], "image_url": e["image_url"], "url": e["url"], "district": e["district"],
        "venue_name": e["place_name"], "address": e["full_address"], "source": "warsaw_open_data",
        "is_public_invite": False, "seats_left": None,
        "starts_at": re.sub(r"([+-]\d{2})$", r"\1:00", e["next_starts_at"]), "ends_at": None, "daily": bool(e["is_all_day"]),
        "attendees": random.choice([0, 0, 0, 1, 2, 3, 5]), "wanting_company": random.choice([0, 0, 1, 2]),
        "is_recurring": bool(e["is_recurring"]), "time_of_day": e["time_of_day"],
    })
n_open = len(events)

# --- 2. venues (OpenStreetMap via streets.gl) + ticketed events joined by venue name --------------
venues = rows(DB / "db" / "street_gl.db", "SELECT * FROM venues WHERE lat IS NOT NULL")
tickets = rows(DB / "kup_bilecik.db",
               "SELECT * FROM events WHERE city LIKE 'Warszawa%' AND date >= date('now') ORDER BY date, time")


def norm(s):
    return re.sub(r"[^a-ząćęłńóśźż0-9]+", " ", (s or "").lower()).strip()


by_name = {}
for v in venues:
    by_name.setdefault(norm(v["name"]), v)
    by_name.setdefault(norm("teatr " + (v["name"] or "")), v)

n_tickets = 0
for v in venues:
    key = norm(v["name"])
    upcoming = [t for t in tickets if key and (key in norm(t["location"]) or norm(t["location"]) in key)]
    upcoming = upcoming[:6]
    n_tickets += len(upcoming)
    tags = json.loads(v["tags_json"] or "{}")
    add(v["lon"], v["lat"], {
        "event_id": v["id"], "kind": "place", "title": v["name"], "categories": [VENUE_CAT.get(v["category"], "culture")],
        "venue_type": v["category"], "lead": tags.get("description") or tags.get("short_name"),
        "image_url": upcoming[0]["image_url"] if upcoming else None, "url": v["website"],
        "district": None, "venue_name": v["name"], "address": v["location"], "source": "streets_gl",
        "is_public_invite": False, "seats_left": None, "opening_hours": v["time"],
        "wheelchair": v["wheelchair"], "capacity": v["capacity"], "phone": v["phone"],
        "upcoming": [{
            "title": t["name"], "starts_at": f"{t['date']}T{t['time'] or '00:00'}", "price": t["price"],
            "currency": t["currency"], "availability": t["availability"], "image_url": t["image_url"], "url": t["url"],
        } for t in upcoming],
    })

# --- 3. open school pitches: no coordinates in the source, so place them inside their district ----
DISTRICTS = {  # approximate centroids (lat, lng)
    "Bemowo": (52.2544, 20.9080), "Białołęka": (52.3215, 20.9720), "Bielany": (52.2920, 20.9340),
    "Mokotów": (52.1930, 21.0450), "Ochota": (52.2120, 20.9780), "Praga-Południe": (52.2370, 21.0870),
    "Praga-Północ": (52.2560, 21.0360), "Rembertów": (52.2600, 21.1600), "Targówek": (52.2900, 21.0500),
    "Ursus": (52.1960, 20.8850), "Ursynów": (52.1400, 21.0400), "Wawer": (52.2000, 21.1600),
    "Wesoła": (52.2500, 21.2300), "Wilanów": (52.1600, 21.0900), "Wola": (52.2370, 20.9600),
    "Włochy": (52.1900, 20.9200), "Śródmieście": (52.2300, 21.0100), "Żoliborz": (52.2700, 20.9800),
}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
pitches = rows(DB / "db" / "sport.db", "SELECT * FROM open_pitches")
seen_addr = {}
for p in pitches:
    c = DISTRICTS.get(p["district"])
    if not c:
        continue
    key = (p["district"], p["address"])
    if key not in seen_addr:
        seen_addr[key] = (c[0] + random.uniform(-0.02, 0.02), c[1] + random.uniform(-0.03, 0.03))
    lat, lng = seen_addr[key]
    add(lng, lat, {
        "event_id": f"pitch/{p['id']}", "kind": "place", "title": f"{p['object_type'] or 'Boisko'} · {p['address']}",
        "categories": ["sports"], "venue_type": "pitch", "lead": p["school_name"], "image_url": None, "url": None,
        "district": p["district"], "venue_name": p["school_name"], "address": p["address"],
        "source": "warsaw_open_data", "is_public_invite": False, "seats_left": None,
        "opening_hours": {d: p[d] for d in DAYS if p[d]}, "surface": p["surface"],
        "equipment": [x for x in (p["equipment"] or "").split("-") if x], "approx_location": True,
    })

# --- 4. a few user "public invitations" so the social layer has something to show -----------------
INVITES = [
    ("Picnic on the Vistula boulevards", "festivals", 21.0330, 52.2395, "Bulwary Wiślane", 8),
    ("Sunset run around Pole Mokotowskie", "running", 20.9960, 52.2140, "Pole Mokotowskie", 4),
    ("Board games at my place (Praga)", "meetups", 21.0400, 52.2520, "Ząbkowska 12", 3),
    ("Language exchange: Polish / English / Ukrainian", "study_buddies", 21.0180, 52.2300, "Hala Koszyki", 6),
    ("Morning yoga in Łazienki", "yoga", 21.0350, 52.2150, "Łazienki Królewskie", 10),
    ("Grzybki trip to Kampinos, leaving 7am", "grzybki", 20.9200, 52.2920, "Metro Młociny", 4),
]
for i, (title, cat, lng, lat, venue, cap) in enumerate(INVITES):
    start = (NOW + timedelta(hours=random.randint(2, 70))).replace(minute=0, second=0, microsecond=0)
    add(lng, lat, {
        "event_id": f"invite/{i}", "kind": "event", "title": title, "categories": [cat], "lead": "Public invitation. Say hi and join.",
        "image_url": None, "url": None, "district": None, "venue_name": venue, "address": None, "source": "user",
        "is_public_invite": True, "seats_left": cap - random.randint(0, cap - 1), "capacity": cap,
        "starts_at": start.isoformat(timespec="minutes"), "ends_at": None, "daily": False,
        "attendees": random.randint(1, 3), "wanting_company": 1, "host": {"display_name": random.choice(["Ola", "Kamil", "Marta", "Tomek"])},
    })

(OUT / "features.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False))

# --- 5. mock "busy now" heat: dense along the Vistula and in Centrum, thinning outwards -----------
HOT = [  # (lng, lat, weight, spread)
    (21.0400, 52.2400, 1.0, 0.004),  # Bulwary Wiślane
    (21.0360, 52.2300, 0.9, 0.005),  # Powiśle / Kopernik
    (21.0200, 52.2300, 1.0, 0.004),  # Nowy Świat
    (21.0120, 52.2200, 0.8, 0.004),  # Plac Zbawiciela
    (21.0180, 52.2240, 0.9, 0.003),  # Hala Koszyki
    (21.0060, 52.2320, 0.8, 0.005),  # Centrum / Pałac Kultury
    (21.0160, 52.2490, 0.7, 0.004),  # Stare Miasto
    (21.0350, 52.2530, 0.6, 0.004),  # Praga Ząbkowska
    (21.0440, 52.2460, 0.5, 0.003),  # Stadion / plaża
    (20.9960, 52.2130, 0.5, 0.005),  # Pole Mokotowskie
    (21.0270, 52.2140, 0.4, 0.004),  # Łazienki
    (20.9850, 52.2320, 0.4, 0.005),  # Wola / Rondo Daszyńskiego
    (20.9800, 52.2690, 0.3, 0.005),  # Żoliborz / Plac Wilsona
    (21.0450, 52.1960, 0.3, 0.005),  # Mokotów
]
busy = []
for lng, lat, w, spread in HOT:
    for _ in range(int(140 * w)):
        busy.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [
            round(random.gauss(lng, spread), 5), round(random.gauss(lat, spread * 0.65), 5)]},
            "properties": {"weight": round(max(0.15, min(1, random.gauss(w, 0.25))), 2)}})
for _ in range(400):  # background noise across the whole city
    busy.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [
        round(random.uniform(20.90, 21.18), 5), round(random.uniform(52.16, 52.31), 5)]},
        "properties": {"weight": round(random.uniform(0.05, 0.25), 2)}})
(OUT / "busy.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": busy}))

sources = [
    {"slug": "warsaw_open_data", "name": "Warsaw Open Data (dane.um.warszawa.pl)", "url": "https://dane.um.warszawa.pl",
     "is_reliable": True, "last_run_at": NOW.isoformat(timespec="minutes"), "last_status": "ok", "item_count": n_open + len(seen_addr)},
    {"slug": "streets_gl", "name": "OpenStreetMap venues (streets.gl)", "url": "https://streets.gl", "is_reliable": True,
     "last_run_at": NOW.isoformat(timespec="minutes"), "last_status": "ok", "item_count": len(venues)},
    {"slug": "kupbilecik", "name": "kupbilecik.pl tickets", "url": "https://www.kupbilecik.pl", "is_reliable": True,
     "last_run_at": NOW.isoformat(timespec="minutes"), "last_status": "partial (403)", "item_count": n_tickets},
    {"slug": "user", "name": "Warszawa Live users", "url": None, "is_reliable": False, "last_run_at": None,
     "last_status": None, "item_count": len(INVITES)},
    {"slug": "google_busy", "name": "Google Popular Times (mock)", "url": None, "is_reliable": False, "last_run_at": None,
     "last_status": "mock data", "item_count": len(busy)},
]
(OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1))
print(f"features: {len(features)} ({n_open} events, {len(venues)} venues with {n_tickets} ticketed shows, "
      f"{len(seen_addr)} pitch sites, {len(INVITES)} invites); busy points: {len(busy)}")
