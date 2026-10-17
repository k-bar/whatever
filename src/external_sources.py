"""External data source clients: kupbilecik.pl (JSON-LD) and OpenStreetMap."""

from datetime import datetime
import html
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Iterator, Optional

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
KUPBILECIK_BASE_URL = "https://www.kupbilecik.pl/pl/"
USER_AGENT = "Mozilla/5.0 (compatible; HackatonEventsBot/1.0)"
OVERPASS_USER_AGENT = "WarszawaLiveIngestor/1.0 (https://syrenka.me)"

VENUE_TAGS: dict[str, list[str]] = {
    "amenity": [
        "theatre",
        "cinema",
        "arts_centre",
        "concert_hall",
        "music_venue",
        "events_venue",
        "nightclub",
        "conference_centre",
        "exhibition_centre",
    ],
    "leisure": ["stadium"],
    "tourism": ["museum", "gallery"],
}

KUPBILECIK_LISTINGS: dict[str, Optional[str]] = {
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

LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)
EVENT_ID_RE = re.compile(r"/(?:event|imprezy)/(\d+)/")


def build_overpass_query(city: str = "Warszawa") -> str:
    """Build Overpass QL query for event venues in the given city."""
    parts: list[str] = []
    for key, values in VENUE_TAGS.items():
        joined = "|".join(values)
        parts.append(f'nwr["{key}"~"^({joined})$"](area.a);')
    return (
        "[out:json][timeout:180];"
        f'area["name"="{city}"]["boundary"="administrative"]->.a;'
        f"({''.join(parts)});out center tags;"
    )


def resolve_venue_category(tags: dict[str, Any]) -> Optional[str]:
    """Extract primary venue category from OSM tags."""
    for key, values in VENUE_TAGS.items():
        val = tags.get(key)
        if isinstance(val, str) and val in values:
            return val
    return None


def parse_osm_element(
    el: dict[str, Any], include_unnamed: bool = False
) -> Optional[dict[str, Any]]:
    """Transform raw Overpass API element into StreetsGlVenue row dict."""
    raw_tags = el.get("tags")
    tags: dict[str, Any] = raw_tags if isinstance(raw_tags, dict) else {}
    name = tags.get("name")
    if not include_unnamed and not name:
        return None

    el_type = el.get("type")
    el_id = el.get("id")
    if not el_type or el_id is None:
        return None

    center = el.get("center")
    center_dict = center if isinstance(center, dict) else {}
    raw_lat = (
        el.get("lat") if el.get("lat") is not None else center_dict.get("lat")
    )
    raw_lon = (
        el.get("lon") if el.get("lon") is not None else center_dict.get("lon")
    )
    lat = float(raw_lat) if raw_lat is not None else None
    lon = float(raw_lon) if raw_lon is not None else None

    street = tags.get("addr:street") or tags.get("addr:place")
    number = tags.get("addr:housenumber")
    postcode = tags.get("addr:postcode")
    city = tags.get("addr:city")
    line1 = " ".join(str(p) for p in (street, number) if p)
    line2 = " ".join(str(p) for p in (postcode, city) if p)
    location = ", ".join(p for p in (line1, line2) if p) or None

    osm_id = f"{el_type}/{el_id}"
    streets_gl_url = (
        f"https://streets.gl/#{lat:.5f},{lon:.5f},45.00,0.00,500.00"
        if lat is not None and lon is not None
        else None
    )

    return {
        "id": osm_id,
        "name": str(name).strip() if name else None,
        "category": resolve_venue_category(tags),
        "location": location,
        "street": str(street).strip() if street else None,
        "housenumber": str(number).strip() if number else None,
        "postcode": str(postcode).strip() if postcode else None,
        "city": str(city).strip() if city else None,
        "lat": lat,
        "lon": lon,
        "opening_hours": tags.get("opening_hours"),
        "website": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "email": tags.get("email") or tags.get("contact:email"),
        "wheelchair": tags.get("wheelchair"),
        "capacity": str(tags["capacity"]) if tags.get("capacity") else None,
        "osm_url": f"https://www.openstreetmap.org/{osm_id}",
        "streets_gl_url": streets_gl_url,
        "tags": tags,
    }


OVERPASS_URLS: tuple[str, ...] = (
    OVERPASS_URL,
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def _load_streets_gl_sqlite_fallback() -> list[dict[str, Any]]:
    """Load streets.gl venues from local SQLite file or git snapshot."""
    sqlite_bytes: Optional[bytes] = None
    env_path = os.getenv("STREETS_GL_SQLITE_PATH")
    candidate = (
        Path(env_path)
        if env_path
        else Path(__file__).resolve().parent.parent
        / "backend"
        / "db"
        / "db"
        / "street_gl.db"
    )
    if candidate.exists():
        sqlite_bytes = candidate.read_bytes()
    else:
        repo_dir = Path(__file__).resolve().parent.parent
        res = subprocess.run(
            ["git", "show", "dd235df:backend/db/street_gl.db"],
            cwd=repo_dir,
            capture_output=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            sqlite_bytes = res.stdout

    if not sqlite_bytes:
        return []

    rows: list[dict[str, Any]] = []
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tmp.write(sqlite_bytes)
        tmp.flush()
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute("SELECT * FROM venues"):
                item = dict(r)
                tags_raw = item.get("tags_json")
                tags: dict[str, Any] = {}
                if isinstance(tags_raw, str) and tags_raw:
                    try:
                        parsed_tags = json.loads(tags_raw)
                        if isinstance(parsed_tags, dict):
                            tags = parsed_tags
                    except json.JSONDecodeError:
                        tags = {}
                item["opening_hours"] = item.get("time")
                item["tags"] = tags
                rows.append(item)
        finally:
            conn.close()
    logging.info(
        "Loaded %d streets.gl venues from SQLite snapshot fallback", len(rows)
    )
    return rows


def fetch_streets_gl_venues(
    city: Optional[str] = None,
    include_unnamed: bool = False,
    session: Optional[requests.Session] = None,
    timeout: int = 240,
) -> list[dict[str, Any]]:
    """Fetch event venues from OpenStreetMap Overpass API with fallback."""
    target_city: str = city or os.getenv("STREETS_GL_CITY") or "Warszawa"
    http = session or requests.Session()
    query = build_overpass_query(target_city)

    for endpoint in OVERPASS_URLS:
        try:
            response = http.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": OVERPASS_USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            elements = (
                payload.get("elements", [])
                if isinstance(payload, dict)
                else []
            )
            rows: list[dict[str, Any]] = []
            for el in elements:
                if isinstance(el, dict):
                    parsed = parse_osm_element(
                        el, include_unnamed=include_unnamed
                    )
                    if parsed is not None:
                        rows.append(parsed)
            if rows:
                return rows
        except requests.RequestException as exc:
            logging.warning("Overpass mirror %s failed: %s", endpoint, exc)

    return _load_streets_gl_sqlite_fallback()


def _split_dt(value: Any) -> tuple[Optional[str], Optional[str]]:
    """Split ISO datetime string into (YYYY-MM-DD, HH:MM)."""
    if not value or not isinstance(value, str):
        return None, None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value[:10], None
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _short_schema(value: Any) -> Optional[str]:
    """Strip schema.org URL prefix (e.g. 'https://schema.org/InStock')."""
    if not value or not isinstance(value, str):
        return None
    return value.rsplit("/", 1)[-1]


def _clean_text(text: Any) -> Optional[str]:
    """Unescape HTML entities and strip whitespace."""
    if not text or not isinstance(text, str):
        return None
    cleaned = html.unescape(text).strip()
    return cleaned if cleaned else None


def iter_kupbilecik_ld_items(page_html: str) -> Iterator[dict[str, Any]]:
    """Yield raw event dicts from JSON-LD ItemList blocks in HTML."""
    for raw in LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        nodes = data.get("@graph", [data])
        if not isinstance(nodes, list):
            nodes = [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            lists: list[dict[str, Any]] = (
                [node] if node.get("@type") == "ItemList" else []
            )
            main = node.get("mainEntity")
            if isinstance(main, dict) and main.get("@type") == "ItemList":
                lists.append(main)
            for lst in lists:
                elements = lst.get("itemListElement", [])
                if not isinstance(elements, list):
                    continue
                for el in elements:
                    if not isinstance(el, dict):
                        continue
                    item = el.get("item", el)
                    if isinstance(item, dict):
                        reviewed = item.get("itemReviewed")
                        if isinstance(reviewed, dict):
                            item = reviewed
                        if item.get("startDate") and item.get("url"):
                            yield item


def parse_kupbilecik_item(
    item: dict[str, Any], category: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Transform a JSON-LD event object into a KupbilecikEvent row dict."""
    url = item.get("url")
    if not isinstance(url, str):
        return None
    match = EVENT_ID_RE.search(url)
    if not match:
        return None

    name = _clean_text(item.get("name"))
    if not name:
        return None

    place: Any = item.get("location") or {}
    if isinstance(place, list):
        place = place[0] if place else {}
    if not isinstance(place, dict):
        place = {}

    addr: Any = place.get("address") or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    if not isinstance(addr, dict):
        addr = {}

    offer: Any = item.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    if not isinstance(offer, dict):
        offer = {}

    date_str, time_str = _split_dt(item.get("startDate"))
    end_date, end_time = _split_dt(item.get("endDate"))
    raw_price = (
        offer.get("price")
        if offer.get("price") is not None
        else offer.get("lowPrice")
    )
    price: Optional[float] = None
    if raw_price not in (None, ""):
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            price = None

    image = item.get("image")
    image_url = image if isinstance(image, str) else None

    return {
        "id": int(match.group(1)),
        "name": name,
        "date": date_str,
        "time": time_str,
        "end_date": end_date,
        "end_time": end_time,
        "location": _clean_text(place.get("name")),
        "address": _clean_text(addr.get("streetAddress")),
        "city": _clean_text(addr.get("addressLocality")),
        "postcode": _clean_text(addr.get("postalCode")),
        "region": _clean_text(addr.get("addressRegion")),
        "category": category,
        "event_type": _clean_text(item.get("@type")),
        "price": price,
        "currency": _clean_text(offer.get("priceCurrency")),
        "availability": _short_schema(offer.get("availability")),
        "status": _short_schema(item.get("eventStatus")),
        "url": url,
        "image_url": image_url,
        "description": _clean_text(item.get("description")),
    }


def _load_kupbilecik_sqlite_fallback() -> list[dict[str, Any]]:
    """Load KupBilecik events from local SQLite file or git snapshot."""
    sqlite_bytes: Optional[bytes] = None
    env_path = os.getenv("KUPBILECIK_SQLITE_PATH")
    candidate = (
        Path(env_path)
        if env_path
        else Path(__file__).resolve().parent.parent
        / "backend"
        / "db"
        / "db"
        / "kup_bilecik.db"
    )
    if candidate.exists():
        sqlite_bytes = candidate.read_bytes()
    else:
        repo_dir = Path(__file__).resolve().parent.parent
        res = subprocess.run(
            ["git", "show", "dd235df:backend/db/kup_bilecik.db"],
            cwd=repo_dir,
            capture_output=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            sqlite_bytes = res.stdout

    if not sqlite_bytes:
        return []

    rows: list[dict[str, Any]] = []
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tmp.write(sqlite_bytes)
        tmp.flush()
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute("SELECT * FROM events"):
                rows.append(dict(r))
        finally:
            conn.close()
    logging.info(
        "Loaded %d KupBilecik events from SQLite snapshot fallback", len(rows)
    )
    return rows


def fetch_kupbilecik_events(
    max_pages: Optional[int] = None,
    delay: Optional[float] = None,
    listings: Optional[list[str]] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Scrape JSON-LD listings from kupbilecik.pl with SQLite fallback."""
    pages_limit = (
        max_pages
        if max_pages is not None
        else int(os.getenv("KUPBILECIK_MAX_PAGES", "2"))
    )
    sleep_delay = (
        delay
        if delay is not None
        else float(os.getenv("KUPBILECIK_DELAY", "0.5"))
    )
    active_listings = (
        listings if listings is not None else list(KUPBILECIK_LISTINGS.keys())
    )
    http = session or requests.Session()
    events_by_id: dict[int, dict[str, Any]] = {}

    for path in active_listings:
        category = KUPBILECIK_LISTINGS.get(path)
        prev_ids: Optional[set[int]] = None
        for page in range(1, pages_limit + 1):
            url = f"{KUPBILECIK_BASE_URL}{path}?page={page}"
            try:
                resp = http.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                )
                if resp.status_code in (403, 429):
                    logging.warning(
                        "KupBilecik rate-limited (%d) at %s; got %d events",
                        resp.status_code,
                        url,
                        len(events_by_id),
                    )
                    if events_by_id:
                        return list(events_by_id.values())
                    return _load_kupbilecik_sqlite_fallback()
                resp.raise_for_status()
            except requests.RequestException as exc:
                logging.warning(
                    "KupBilecik request failed at %s: %s", url, exc
                )
                break

            rows = [
                r
                for r in (
                    parse_kupbilecik_item(item, category=category)
                    for item in iter_kupbilecik_ld_items(resp.text)
                )
                if r is not None
            ]
            page_ids = {int(r["id"]) for r in rows}
            if not page_ids or page_ids == prev_ids:
                break
            prev_ids = page_ids

            for row in rows:
                eid = int(row["id"])
                existing = events_by_id.get(eid)
                if existing is not None and row.get("category") is None:
                    row["category"] = existing.get("category")
                events_by_id[eid] = row

            if sleep_delay > 0:
                time.sleep(sleep_delay)

    return list(events_by_id.values())
