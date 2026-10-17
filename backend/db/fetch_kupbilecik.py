"""Scrapes events from www.kupbilecik.pl and saves them to SQLite (kup_bilecik.db).

Listing pages (search + categories) embed schema.org JSON-LD with every event:
name, start/end date, venue and address. Each event id is one show (one date
in one place), so the table has one row per show.

The search listing stops paginating at page 500 (later pages repeat it), so
category listings are crawled too and rows are deduplicated by event id.

Usage:
    python fetch_kupbilecik.py                 # full crawl
    python fetch_kupbilecik.py --max-pages 5   # quick test
    python fetch_kupbilecik.py --delay 1.0     # slower, more polite
"""

import argparse
import html
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://www.kupbilecik.pl/pl/"
HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "kup_bilecik.db"
USER_AGENT = "Mozilla/5.0 (compatible; HackatonEventsBot/1.0)"

# listing path -> category label
LISTINGS = {
    "search": None,
    "theatre": "teatr",
    "concerts": "muzyka",
    "cabarets": "kabaret",
    "standup": "stand-up",
    "impro": "impro",
    "sport": "sport",
    "kids": "dzieci",
    "festivals": "festiwal",
    "other": "inne",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY,  -- event id from the URL
    name          TEXT NOT NULL,
    date          TEXT,                 -- YYYY-MM-DD
    time          TEXT,                 -- HH:MM
    end_date      TEXT,
    end_time      TEXT,
    location      TEXT,                 -- venue name
    address       TEXT,                 -- street
    city          TEXT,
    postcode      TEXT,
    region        TEXT,                 -- voivodeship
    category      TEXT,                 -- listing category, e.g. "teatr"
    event_type    TEXT,                 -- schema.org type, e.g. "TheaterEvent"
    price         REAL,
    currency      TEXT,
    availability  TEXT,                 -- InStock / SoldOut / ...
    status        TEXT,                 -- EventScheduled / EventCancelled / ...
    url           TEXT UNIQUE,
    image_url     TEXT,
    description   TEXT,
    scraped_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_events_city ON events(city);
"""

LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)
EVENT_ID_RE = re.compile(r"/event/(\d+)/")


def fetch(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                print(f"  ! {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))


def iter_list_items(page_html):
    """Yields event dicts from every ItemList in the page's JSON-LD."""
    for raw in LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in data.get("@graph", [data]):
            lists = [node] if node.get("@type") == "ItemList" else []
            main = node.get("mainEntity")
            if isinstance(main, dict) and main.get("@type") == "ItemList":
                lists.append(main)
            for lst in lists:
                for el in lst.get("itemListElement", []):
                    item = el.get("item", el)
                    # the homepage wraps events in a Review
                    item = item.get("itemReviewed", item)
                    if item.get("startDate") and item.get("url"):
                        yield item


def split_dt(value):
    if not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value[:10], None
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def short_schema(value):
    return value.rsplit("/", 1)[-1] if value else None


def clean(text):
    return html.unescape(text).strip() if text else None


def to_row(item, category, scraped_at):
    m = EVENT_ID_RE.search(item["url"])
    if not m:
        return None
    place = item.get("location") or {}
    if isinstance(place, list):
        place = place[0] if place else {}
    addr = place.get("address") or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    offer = item.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    date, tm = split_dt(item.get("startDate"))
    end_date, end_time = split_dt(item.get("endDate"))
    price = offer.get("price") if offer.get("price") is not None else offer.get("lowPrice")
    return {
        "id": int(m.group(1)),
        "name": clean(item.get("name")),
        "date": date,
        "time": tm,
        "end_date": end_date,
        "end_time": end_time,
        "location": clean(place.get("name")),
        "address": clean(addr.get("streetAddress")),
        "city": clean(addr.get("addressLocality")),
        "postcode": addr.get("postalCode"),
        "region": clean(addr.get("addressRegion")),
        "category": category,
        "event_type": item.get("@type"),
        "price": float(price) if price not in (None, "") else None,
        "currency": offer.get("priceCurrency"),
        "availability": short_schema(offer.get("availability")),
        "status": short_schema(item.get("eventStatus")),
        "url": item["url"],
        "image_url": item.get("image") if isinstance(item.get("image"), str) else None,
        "description": clean(item.get("description")),
        "scraped_at": scraped_at,
    }


def upsert(conn, row):
    cols = list(row)
    # keep a category found earlier if this listing (search) has none
    updates = ", ".join(
        f"{c}=COALESCE(excluded.{c}, events.{c})" if c == "category" else f"{c}=excluded.{c}"
        for c in cols if c != "id"
    )
    conn.execute(
        f"INSERT INTO events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        [row[c] for c in cols],
    )


def crawl_listing(conn, path, category, seen, max_pages, delay, scraped_at):
    new_total = 0
    prev_ids = None
    for page in range(1, max_pages + 1):
        page_html = fetch(f"{BASE}{path}?page={page}")
        if page_html is None:
            break
        rows = [r for r in (to_row(i, category, scraped_at) for i in iter_list_items(page_html)) if r]
        ids = {r["id"] for r in rows}
        # past the last page the site repeats the final page
        if not ids or ids == prev_ids:
            break
        prev_ids = ids
        for r in rows:
            if r["id"] not in seen:
                new_total += 1
            seen.add(r["id"])
            upsert(conn, r)
        conn.commit()
        print(f"  {path} page {page}: {len(rows)} events, {len(seen)} unique total")
        time.sleep(delay)
    return new_total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--max-pages", type=int, default=1000, help="pages per listing")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--listings", nargs="*", default=list(LISTINGS), choices=list(LISTINGS))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    scraped_at = datetime.now().isoformat(timespec="seconds")
    seen = set()
    for path in args.listings:
        print(f"[{path}]")
        new = crawl_listing(conn, path, LISTINGS[path], seen, args.max_pages, args.delay, scraped_at)
        print(f"[{path}] +{new} new events")
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    print(f"Done: {len(seen)} events scraped, {total} rows in {args.db}")


if __name__ == "__main__":
    main()
