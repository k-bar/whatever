"""Pobiera dane z API dane.um.warszawa.pl i zapisuje je do SQLite.

    events.db  <- Kalendarz wydarzeń      (kategoria "Wydarzenia")
    sport.db   <- Zajęcia sportowe + Otwarte boiska (kategoria "Sport")

Token API: https://dane.um.warszawa.pl/en/key-api
Użycie:
    python fetch_data.py --token TWOJ_TOKEN
    (albo zmienna środowiskowa WARSAW_API_TOKEN)
    python fetch_data.py --schema-only   # tylko puste tabele
"""

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://dane.um.warszawa.pl/api/action/"
HERE = Path(__file__).resolve().parent

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    url         TEXT UNIQUE,
    language    TEXT,
    categories  TEXT,   -- nazwy rozdzielone "; "
    lead        TEXT,
    image_url   TEXT,
    text_html   TEXT,
    text_plain  TEXT,
    kiedy       TEXT,   -- np. "29.01.2027 19:00–21:00"; najbliższe terminy
    gdzie       TEXT,   -- np. "OCH-Teatr, ul. Grójecka 65, Ochota"
    data        TEXT,   -- data najbliższego terminu, YYYY-MM-DD
    czas        TEXT,   -- godziny najbliższego terminu, np. "19:00–21:00" albo "cały dzień"
    starts_at   TEXT,   -- najwcześniejsze occurrence.from
    ends_at     TEXT,   -- najpóźniejsze occurrence.to
    next_starts_at TEXT, -- najbliższy termin, który jeszcze się nie skończył
    place_name  TEXT,
    street      TEXT,
    postcode    TEXT,
    lat         REAL,   -- pierwsza lokalizacja z mapy
    lon         REAL,
    district    TEXT,
    -- miejsce
    full_address      TEXT,    -- "ul. Lucerny 13, 04-687 Warszawa"
    map_street        TEXT,    -- pełna nazwa ulicy z mapy, np. "ulica Targowa"
    map_street_number TEXT,
    place_phone       TEXT,
    place_email       TEXT,
    place_www         TEXT,
    location_count    INTEGER, -- liczba punktów na mapie
    all_districts     TEXT,    -- dzielnice wszystkich punktów
    has_coordinates   INTEGER,
    is_online         INTEGER,
    -- czas
    start_date        TEXT,    -- pierwszy termin (YYYY-MM-DD)
    start_time        TEXT,    -- HH:MM
    end_date          TEXT,    -- ostatni termin
    end_time          TEXT,
    next_date         TEXT,    -- najbliższy (jeszcze trwający) termin
    next_start_time   TEXT,
    next_end_time     TEXT,
    duration_min      INTEGER, -- długość najbliższego terminu w minutach
    occurrence_count  INTEGER,
    is_recurring      INTEGER, -- więcej niż jeden termin
    is_multi_day      INTEGER, -- najbliższy termin trwa kilka dni
    is_all_day        INTEGER,
    weekdays          TEXT,    -- dni tygodnia terminów, np. "wtorek; czwartek"
    time_of_day       TEXT,    -- rano / popołudnie / wieczór / cały dzień
    is_finished       INTEGER, -- wszystkie terminy już minęły (w chwili pobrania)
    raw_json    TEXT
);
CREATE TABLE IF NOT EXISTS event_occurrences (
    event_id    INTEGER REFERENCES events(id) ON DELETE CASCADE,
    starts_at   TEXT,
    ends_at     TEXT,
    daily       INTEGER,
    date        TEXT,   -- YYYY-MM-DD
    start_time  TEXT,   -- HH:MM
    end_date    TEXT,
    end_time    TEXT,
    all_day     INTEGER
);
CREATE TABLE IF NOT EXISTS event_addresses (
    event_id    INTEGER REFERENCES events(id) ON DELETE CASCADE,
    name        TEXT,
    street      TEXT,
    postcode    TEXT,
    title       TEXT,   -- tytuł wydarzenia
    data        TEXT,   -- jak events.data
    czas        TEXT    -- jak events.czas
);
CREATE TABLE IF NOT EXISTS event_locations (
    event_id      INTEGER REFERENCES events(id) ON DELETE CASCADE,
    lat           REAL,
    lon           REAL,
    district      TEXT,
    street        TEXT,
    street_number TEXT
);
CREATE VIEW IF NOT EXISTS event_schedule AS   -- jeden wiersz = jeden termin
    SELECT o.event_id, e.title, o.date, o.start_time, o.end_date, o.end_time, o.all_day,
           o.starts_at, o.ends_at, e.gdzie, e.place_name, e.district, e.lat, e.lon,
           e.categories, e.url
    FROM event_occurrences o JOIN events e ON e.id = o.event_id;
CREATE INDEX IF NOT EXISTS ix_occ_event ON event_occurrences(event_id);
CREATE INDEX IF NOT EXISTS ix_occ_start ON event_occurrences(starts_at);
CREATE INDEX IF NOT EXISTS ix_loc_event ON event_locations(event_id);
"""

SPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS sport_classes (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    url         TEXT UNIQUE,
    language    TEXT,
    time        TEXT,
    categories  TEXT,   -- nazwy rozdzielone "; "
    days        TEXT,
    dedicated   TEXT,   -- adresaci (Kobiety, Seniorzy, ...)
    districts   TEXT,
    image_url   TEXT,
    text_html   TEXT,
    text_plain  TEXT,
    raw_json    TEXT
);
CREATE TABLE IF NOT EXISTS sport_class_dates (
    class_id    INTEGER REFERENCES sport_classes(id) ON DELETE CASCADE,
    date        TEXT
);
CREATE TABLE IF NOT EXISTS sport_class_addresses (
    class_id    INTEGER REFERENCES sport_classes(id) ON DELETE CASCADE,
    name        TEXT,
    street      TEXT
);
CREATE TABLE IF NOT EXISTS open_pitches (
    id              INTEGER PRIMARY KEY,
    district        TEXT,
    address         TEXT,
    school_name     TEXT,
    object_type     TEXT,
    equipment       TEXT,
    surface         TEXT,
    has_stands      TEXT,
    has_ball_nets   TEXT,
    monday          TEXT,
    tuesday         TEXT,
    wednesday       TEXT,
    thursday        TEXT,
    friday          TEXT,
    saturday        TEXT,
    sunday          TEXT,
    notes           TEXT,
    updated_at      TEXT,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS ix_dates_class ON sport_class_dates(class_id);
CREATE INDEX IF NOT EXISTS ix_dates_date ON sport_class_dates(date);
"""

PITCH_COLUMNS = {
    "district": "Dzielnica",
    "address": "Adres obiektu",
    "school_name": "Nazwa placówki oświatowej",
    "object_type": "Typ obiektu",
    "equipment": "Boisk uniwersalne zawiera",
    "surface": "Rodzaj nawierzchni",
    "has_stands": "Obiekt wyposażony w trybuny",
    "has_ball_nets": "Obiekt wyposażony w piłkochwyty",
    "monday": "Poniedziałek",
    "tuesday": "Wtorek",
    "wednesday": "Środa",
    "thursday": "Czwartek",
    "friday": "Piątek",
    "saturday": "Sobota",
    "sunday": "Niedziela",
    "notes": "Uwagi",
    "updated_at": "Data aktualizacji",
}


def fetch(action, token):
    req = urllib.request.Request(API + action, method="POST", headers={"Authorization": token})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return as_records(data)


def as_records(data):
    """API może zwrócić listę albo ją opakować (result / results / records)."""
    while isinstance(data, dict):
        for key in ("result", "results", "records", "data", "items"):
            if key in data:
                data = data[key]
                break
        else:
            return [data]
    return data or []


def strip_html(s):
    if not s:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def names(items):
    return "; ".join(i["name"] for i in items or [] if isinstance(i, dict) and i.get("name")) or None


def image_url(rec):
    img = rec.get("image") or {}
    path = ((img.get("small") or img.get("highlighted") or {}).get("path") or "").replace("\n", "")
    return path or None


def fmt_date(s):
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}"


def is_all_day(o):
    return (o.get("from") or "")[11:16] == "00:00" and (o.get("to") or "")[11:16] == "23:59"


def fmt_occurrence(o):
    f, t = o.get("from") or "", o.get("to") or ""
    if not f:
        return None
    if not t or t[:10] == f[:10]:
        if is_all_day(o):
            return f"{fmt_date(f)} (cały dzień)"
        return f"{fmt_date(f)} {f[11:16]}–{t[11:16]}" if t else f"{fmt_date(f)} {f[11:16]}"
    if is_all_day(o):
        return f"{fmt_date(f)} – {fmt_date(t)}"
    return f"{fmt_date(f)} {f[11:16]} – {fmt_date(t)} {t[11:16]}"


def kiedy(occ, now):
    """Najbliższe (jeszcze trwające) terminy; gdy wszystkie minęły, pierwsze terminy."""
    occ = sorted((o for o in occ if o.get("from")), key=lambda o: o["from"])
    pick = [o for o in occ if (o.get("to") or o["from"]) >= now] or occ
    text = "; ".join(fmt_occurrence(o) for o in pick[:3])
    if len(pick) > 3:
        text += f" i {len(pick) - 3} więcej"
    return text or None, (pick[0]["from"] if pick else None)


WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def parse_ts(s):
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M") if s and len(s) >= 16 else None


def first_value(v):
    if isinstance(v, list):
        return "; ".join(str(x) for x in v if x) or None
    return v or None


def time_fields(occ, now):
    occ = sorted((o for o in occ if o.get("from")), key=lambda o: o["from"])
    upcoming = [o for o in occ if (o.get("to") or o["from"]) >= now]
    nxt = (upcoming or occ or [{}])[0]
    f, t = nxt.get("from") or "", nxt.get("to") or ""
    start, end = parse_ts(f), parse_ts(t)
    days = {parse_ts(o["from"]).weekday() for o in occ if parse_ts(o["from"])}
    if not f:
        tod = None
    elif is_all_day(nxt):
        tod = "cały dzień"
    else:
        tod = "rano" if f[11:13] < "12" else "popołudnie" if f[11:13] < "17" else "wieczór"
    last_to = max((o.get("to") or o["from"] for o in occ), default="")
    if not f:
        czas = None
    elif is_all_day(nxt):
        czas = "cały dzień"
    else:
        czas = f"{f[11:16]}–{t[11:16]}" if t else f[11:16]
    return {
        "data": f[:10] or None,
        "czas": czas,
        "start_date": occ[0]["from"][:10] if occ else None,
        "start_time": occ[0]["from"][11:16] if occ else None,
        "end_date": last_to[:10] or None,
        "end_time": last_to[11:16] or None,
        "next_date": f[:10] or None,
        "next_start_time": f[11:16] or None,
        "next_end_time": t[11:16] or None,
        "duration_min": int((end - start).total_seconds() // 60) if start and end else None,
        "occurrence_count": len(occ),
        "is_recurring": int(len(occ) > 1),
        "is_multi_day": int(bool(t) and t[:10] != f[:10]),
        "is_all_day": int(bool(f) and is_all_day(nxt)),
        "weekdays": "; ".join(WEEKDAYS[d] for d in sorted(days)) or None,
        "time_of_day": tod,
        "is_finished": int(bool(occ) and not upcoming),
    }


def gdzie(address, locs, district):
    name = address.get("name")
    street = address.get("street")
    if not street and locs and locs[0][3]:
        street = " ".join(x for x in locs[0][3:5] if x)
    parts = [name, street]
    if district and not any(district in (p or "") for p in parts):
        parts.append(district)
    return ", ".join(p for p in parts if p) or None


def build_events(path, records):
    con = sqlite3.connect(path)
    con.executescript("DROP VIEW IF EXISTS event_schedule; DROP TABLE IF EXISTS event_occurrences; "
                      "DROP TABLE IF EXISTS event_addresses; DROP TABLE IF EXISTS event_locations; "
                      "DROP TABLE IF EXISTS events;")
    con.executescript(EVENTS_SCHEMA)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    for rec in records:
        occ = rec.get("occurrence") or rec.get("occurence") or []
        feats = ((rec.get("map") or {}).get("features")) or []
        locs, full_streets = [], []
        for f in feats:
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            p = f.get("properties") or {}
            locs.append((coords[1], coords[0], p.get("district"),
                         p.get("shortStreetName") or p.get("fullStreetName"),
                         p.get("streetNumber") or p.get("street number")))
            full_streets.append(p.get("fullStreetName"))
        starts = [o.get("from") for o in occ if o.get("from")]
        ends = [o.get("to") for o in occ if o.get("to")]
        first = locs[0] if locs else (None, None, None, None, None)
        district = names(rec.get("localization")) or first[2]
        addresses = [a for a in rec.get("address") or [] if isinstance(a, dict)]
        addr = addresses[0] if addresses else {}
        when, next_start = kiedy(occ, now)
        where = gdzie(addr, locs, district)
        street = addr.get("street") or (" ".join(x for x in first[3:5] if x) or None)
        row = {
            "title": rec.get("title"), "url": rec.get("url"), "language": rec.get("language"),
            "categories": names(rec.get("category")), "lead": rec.get("lead"), "image_url": image_url(rec),
            "text_html": rec.get("text"), "text_plain": strip_html(rec.get("text")),
            "kiedy": when, "gdzie": where,
            "starts_at": min(starts, default=None), "ends_at": max(ends, default=None),
            "next_starts_at": next_start,
            "place_name": addr.get("name"), "street": addr.get("street"),
            "postcode": addr.get("postCodeAndOffice"),
            "lat": first[0], "lon": first[1], "district": district,
            "full_address": ", ".join(x for x in (street, addr.get("postCodeAndOffice")) if x) or None,
            "map_street": full_streets[0] if full_streets else None, "map_street_number": first[4],
            "place_phone": first_value(addr.get("phone")), "place_email": first_value(addr.get("email")),
            "place_www": first_value(addr.get("www")),
            "location_count": len(locs),
            "all_districts": "; ".join(dict.fromkeys(l[2] for l in locs if l[2])) or district,
            "has_coordinates": int(first[0] is not None),
            "is_online": int("online" in " ".join(filter(None, (where, rec.get("title")))).lower()),
            **time_fields(occ, now),
            "raw_json": json.dumps(rec, ensure_ascii=False),
        }
        cur = con.execute(f"INSERT OR REPLACE INTO events ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                          tuple(row.values()))
        eid = cur.lastrowid
        con.executemany(
            "INSERT INTO event_occurrences VALUES (?,?,?,?,?,?,?,?,?)",
            [(eid, o.get("from"), o.get("to"), int(bool(o.get("daily"))),
              (o.get("from") or "")[:10] or None, (o.get("from") or "")[11:16] or None,
              (o.get("to") or "")[:10] or None, (o.get("to") or "")[11:16] or None, int(is_all_day(o)))
             for o in occ])
        con.executemany("INSERT INTO event_addresses VALUES (?,?,?,?,?,?,?)",
                        [(eid, a.get("name"), a.get("street"), a.get("postCodeAndOffice"),
                          row["title"], row["data"], row["czas"]) for a in addresses])
        con.executemany("INSERT INTO event_locations VALUES (?,?,?,?,?,?)", [(eid, *l) for l in locs])
    con.commit()
    con.close()


def build_sport(path, classes, pitches):
    con = sqlite3.connect(path)
    con.executescript(SPORT_SCHEMA)
    con.executescript("DELETE FROM sport_class_dates; DELETE FROM sport_class_addresses; "
                      "DELETE FROM sport_classes; DELETE FROM open_pitches;")
    for rec in classes:
        cur = con.execute(
            "INSERT OR REPLACE INTO sport_classes (title, url, language, time, categories, days, dedicated,"
            " districts, image_url, text_html, text_plain, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec.get("title"), rec.get("url"), rec.get("language"), rec.get("time"),
             names(rec.get("category") or rec.get("kategoria")), names(rec.get("day")),
             names(rec.get("dedicated")), names(rec.get("localization")), image_url(rec), rec.get("text"),
             strip_html(rec.get("text")), json.dumps(rec, ensure_ascii=False)))
        cid = cur.lastrowid
        con.executemany("INSERT INTO sport_class_dates VALUES (?,?)", [(cid, d) for d in rec.get("date") or []])
        con.executemany("INSERT INTO sport_class_addresses VALUES (?,?,?)",
                        [(cid, a.get("name"), a.get("street")) for a in rec.get("address") or []])
    cols = list(PITCH_COLUMNS)
    con.executemany(
        f"INSERT INTO open_pitches ({', '.join(cols)}, raw_json) VALUES ({', '.join('?' * (len(cols) + 1))})",
        [tuple(p.get(PITCH_COLUMNS[c]) for c in cols) + (json.dumps(p, ensure_ascii=False),) for p in pitches])
    con.commit()
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("WARSAW_API_TOKEN"))
    ap.add_argument("--schema-only", action="store_true")
    args = ap.parse_args()

    if args.schema_only:
        build_events(HERE / "events.db", [])
        build_sport(HERE / "sport.db", [], [])
        print("Utworzono puste events.db i sport.db")
        return
    if not args.token:
        sys.exit("Brak tokenu: podaj --token albo ustaw WARSAW_API_TOKEN (https://dane.um.warszawa.pl/en/key-api)")

    events = fetch("get_bmm_kalendarz_wydarzen", args.token)
    classes = fetch("get_bmm_zajecia_sportowe", args.token)
    pitches = fetch("get_be_otwarte_boiska", args.token)
    build_events(HERE / "events.db", events)
    build_sport(HERE / "sport.db", classes, pitches)
    print(f"events.db: {len(events)} wydarzeń")
    print(f"sport.db:  {len(classes)} zajęć sportowych, {len(pitches)} otwartych boisk")


if __name__ == "__main__":
    main()
