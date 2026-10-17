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
from pathlib import Path

API = "https://dane.um.warszawa.pl/api/action/"
HERE = Path(__file__).resolve().parent

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    url         TEXT UNIQUE,
    language    TEXT,
    text_html   TEXT,
    text_plain  TEXT,
    starts_at   TEXT,   -- najwcześniejsze occurrence.from
    ends_at     TEXT,   -- najpóźniejsze occurrence.to
    lat         REAL,   -- pierwsza lokalizacja z mapy
    lon         REAL,
    district    TEXT,
    raw_json    TEXT
);
CREATE TABLE IF NOT EXISTS event_occurrences (
    event_id    INTEGER REFERENCES events(id) ON DELETE CASCADE,
    starts_at   TEXT,
    ends_at     TEXT,
    daily       INTEGER
);
CREATE TABLE IF NOT EXISTS event_addresses (
    event_id    INTEGER REFERENCES events(id) ON DELETE CASCADE,
    name        TEXT,
    street      TEXT
);
CREATE TABLE IF NOT EXISTS event_locations (
    event_id      INTEGER REFERENCES events(id) ON DELETE CASCADE,
    lat           REAL,
    lon           REAL,
    district      TEXT,
    street        TEXT,
    street_number TEXT
);
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
    return "; ".join(i.get("name", "") for i in items or [] if isinstance(i, dict)) or None


def build_events(path, records):
    con = sqlite3.connect(path)
    con.executescript(EVENTS_SCHEMA)
    con.executescript("DELETE FROM event_occurrences; DELETE FROM event_addresses; "
                      "DELETE FROM event_locations; DELETE FROM events;")
    for rec in records:
        occ = rec.get("occurrence") or rec.get("occurence") or []
        feats = ((rec.get("map") or {}).get("features")) or []
        locs = []
        for f in feats:
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            p = f.get("properties") or {}
            locs.append((coords[1], coords[0], p.get("district"),
                         p.get("shortStreetName") or p.get("fullStreetName"),
                         p.get("streetNumber") or p.get("street number")))
        starts = [o.get("from") for o in occ if o.get("from")]
        ends = [o.get("to") for o in occ if o.get("to")]
        first = locs[0] if locs else (None, None, None)
        cur = con.execute(
            "INSERT OR REPLACE INTO events (title, url, language, text_html, text_plain, starts_at, ends_at,"
            " lat, lon, district, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rec.get("title"), rec.get("url"), rec.get("language"), rec.get("text"),
             strip_html(rec.get("text")), min(starts, default=None), max(ends, default=None),
             first[0], first[1], first[2], json.dumps(rec, ensure_ascii=False)))
        eid = cur.lastrowid
        con.executemany("INSERT INTO event_occurrences VALUES (?,?,?,?)",
                        [(eid, o.get("from"), o.get("to"), int(bool(o.get("daily")))) for o in occ])
        con.executemany("INSERT INTO event_addresses VALUES (?,?,?)",
                        [(eid, a.get("name"), a.get("street")) for a in rec.get("address") or []])
        con.executemany("INSERT INTO event_locations VALUES (?,?,?,?,?,?)", [(eid, *l) for l in locs])
    con.commit()
    con.close()


def build_sport(path, classes, pitches):
    con = sqlite3.connect(path)
    con.executescript(SPORT_SCHEMA)
    con.executescript("DELETE FROM sport_class_dates; DELETE FROM sport_class_addresses; "
                      "DELETE FROM sport_classes; DELETE FROM open_pitches;")
    for rec in classes:
        image = (((rec.get("image") or {}).get("small") or {}).get("path") or "").replace("\n", "") or None
        cur = con.execute(
            "INSERT OR REPLACE INTO sport_classes (title, url, language, time, categories, days, dedicated,"
            " districts, image_url, text_html, text_plain, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec.get("title"), rec.get("url"), rec.get("language"), rec.get("time"),
             names(rec.get("category") or rec.get("kategoria")), names(rec.get("day")),
             names(rec.get("dedicated")), names(rec.get("localization")), image, rec.get("text"),
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
