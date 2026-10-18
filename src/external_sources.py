"""External sources: OSM (streets.gl, restaurants), Songkick, Waw4Free."""

from datetime import date, datetime, timedelta, timezone
import html as html_lib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Any, Optional

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_USER_AGENT = "WarszawaLiveIngestor/1.0 (+https://syrenka.me)"

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

RESTAURANT_AMENITIES: tuple[str, ...] = (
    "restaurant",
    "cafe",
    "bar",
    "pub",
    "biergarten",
    "food_court",
)

SONGKICK_WARSAW_URL = (
    "https://www.songkick.com/metro-areas/31787-poland-warsaw"
)
WAW4FREE_BASE_URL = "https://waw4free.pl"

WAW4FREE_LISTINGS: tuple[tuple[str, str], ...] = (
    ("warszawa-darmowe-koncerty", "koncerty"),
    ("warszawa-darmowe-imprezy", "imprezy"),
    ("warszawa-darmowe-standup", "stand-up"),
    ("warszawa-darmowe-teatr", "teatr"),
    ("warszawa-darmowe-filmy", "film"),
    ("warszawa-darmowe-wystawy", "wystawy"),
    ("warszawa-darmowe-targi", "targi"),
    ("warszawa-darmowe-warsztaty", "warsztaty"),
    ("warszawa-darmowe-spotkania", "spotkania"),
    ("warszawa-darmowe-sport", "sport"),
)

WARSAW_DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "Bemowo": (52.2388, 20.9133),
    "Białołęka": (52.3247, 20.9794),
    "Bielany": (52.2906, 20.9352),
    "Mokotów": (52.1939, 21.0350),
    "Ochota": (52.2125, 20.9760),
    "Praga-Południe": (52.2367, 21.0772),
    "Praga-Północ": (52.2572, 21.0369),
    "Rembertów": (52.2597, 21.1619),
    "Śródmieście": (52.2319, 21.0067),
    "Targówek": (52.2836, 21.0539),
    "Ursus": (52.1950, 20.8853),
    "Ursynów": (52.1489, 21.0436),
    "Wawer": (52.1922, 21.1683),
    "Wesoła": (52.2489, 21.2292),
    "Wilanów": (52.1642, 21.0897),
    "Włochy": (52.1917, 20.9469),
    "Wola": (52.2369, 20.9686),
    "Żoliborz": (52.2683, 20.9800),
}


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


def build_restaurants_overpass_query(city: str = "Warszawa") -> str:
    """Build Overpass QL query for restaurants and food/drink venues."""
    joined = "|".join(RESTAURANT_AMENITIES)
    return (
        "[out:json][timeout:180];"
        f'area["name"="{city}"]["boundary"="administrative"]->.a;'
        f'(nwr["amenity"~"^({joined})$"](area.a););'
        "out center tags;"
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


def parse_restaurant_element(el: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Transform raw Overpass API element into Restaurant row dict."""
    raw_tags = el.get("tags")
    tags: dict[str, Any] = raw_tags if isinstance(raw_tags, dict) else {}
    raw_name = tags.get("name")
    name = str(raw_name).strip() if raw_name else ""
    amenity = tags.get("amenity")
    if not name or amenity not in RESTAURANT_AMENITIES:
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
    if lat is None or lon is None:
        return None

    street = tags.get("addr:street") or tags.get("addr:place")
    number = tags.get("addr:housenumber")
    postcode = tags.get("addr:postcode")
    city = tags.get("addr:city") or "Warszawa"
    line1 = " ".join(str(p) for p in (street, number) if p)
    line2 = " ".join(str(p) for p in (postcode, city) if p)
    location = ", ".join(p for p in (line1, line2) if p) or None

    osm_id = f"{el_type}/{el_id}"
    return {
        "id": osm_id,
        "name": name,
        "amenity": str(amenity),
        "cuisine": (
            str(tags["cuisine"]).strip() if tags.get("cuisine") else None
        ),
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
        "outdoor_seating": tags.get("outdoor_seating"),
        "diet_vegan": tags.get("diet:vegan"),
        "diet_vegetarian": tags.get("diet:vegetarian"),
        "wheelchair": tags.get("wheelchair"),
        "osm_url": f"https://www.openstreetmap.org/{osm_id}",
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


def fetch_restaurants(
    city: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 240,
) -> list[dict[str, Any]]:
    """Fetch Warsaw restaurants, cafes, bars, and pubs from Overpass API."""
    target_city: str = city or os.getenv("RESTAURANTS_CITY") or "Warszawa"
    http = session or requests.Session()
    query = build_restaurants_overpass_query(target_city)

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
                    parsed = parse_restaurant_element(el)
                    if parsed is not None:
                        rows.append(parsed)
            if rows:
                return rows
        except requests.RequestException as exc:
            logging.warning(
                "Overpass mirror %s failed for restaurants: %s", endpoint, exc
            )

    return []


_LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)
_SONGKICK_ID_RE = re.compile(r"/(?:concerts|festivals/[^/]+/id)/(\d+)")


def parse_songkick_event(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Transform a Songkick JSON-LD MusicEvent dict into an event row dict."""
    if item.get("@type") != "MusicEvent":
        return None
    raw_url = str(item.get("url") or "").strip()
    clean_url = raw_url.split("?")[0]
    name = str(item.get("name") or "").strip()
    start_date = str(item.get("startDate") or "").strip()
    if not clean_url or not name or not start_date:
        return None

    loc = item.get("location")
    loc_dict = loc if isinstance(loc, dict) else {}
    addr = loc_dict.get("address")
    addr_dict = addr if isinstance(addr, dict) else {}
    geo = loc_dict.get("geo")
    geo_dict = geo if isinstance(geo, dict) else {}

    raw_lat = geo_dict.get("latitude")
    raw_lon = geo_dict.get("longitude")
    lat = float(raw_lat) if raw_lat is not None else None
    lon = float(raw_lon) if raw_lon is not None else None
    locality = str(addr_dict.get("addressLocality") or "").strip()

    in_warsaw_bbox = (
        lat is not None
        and lon is not None
        and 52.0 < lat < 52.5
        and 20.7 < lon < 21.4
    )
    is_warsaw_city = locality.lower() in {"warsaw", "warszawa"}
    if not (in_warsaw_bbox or is_warsaw_city):
        return None

    m = _SONGKICK_ID_RE.search(clean_url)
    ext_id = f"songkick:{m.group(1)}" if m else f"songkick:{clean_url}"

    venue_name = str(loc_dict.get("name") or "").strip() or None
    street = str(addr_dict.get("streetAddress") or "").strip()
    postal = str(addr_dict.get("postalCode") or "").strip()
    addr_parts = [p for p in (street, postal, "Warszawa") if p]
    address = ", ".join(addr_parts) if street else None

    raw_performers = item.get("performer")
    performers: list[str] = []
    if isinstance(raw_performers, list):
        for p in raw_performers:
            if isinstance(p, dict) and p.get("name"):
                performers.append(str(p["name"]).strip())

    end_date = str(item.get("endDate") or "").strip() or None
    image_url = str(item.get("image") or "").strip() or None
    description = str(item.get("description") or "").strip() or None

    return {
        "id": ext_id,
        "source": "songkick",
        "title": name,
        "category": "concert",
        "start_date": start_date,
        "end_date": end_date,
        "venue_name": venue_name,
        "address": address,
        "district": None,
        "city": "Warszawa",
        "lat": lat,
        "lon": lon,
        "url": clean_url,
        "image_url": image_url,
        "description": description,
        "performers": performers,
        "is_free": "no",
        "raw_data": item,
    }


def parse_songkick_html(html: str) -> list[dict[str, Any]]:
    """Extract Warsaw MusicEvent records from Songkick metro-area HTML."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    for block in _LD_JSON_RE.findall(html):
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for entry in items:
            if isinstance(entry, dict):
                parsed = parse_songkick_event(entry)
                if parsed is not None:
                    rows_by_id[parsed["id"]] = parsed
    return list(rows_by_id.values())


def fetch_songkick_events(
    max_pages: int = 5,
    session: Optional[requests.Session] = None,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetch Warsaw concerts across multiple Songkick pages."""
    http = session or requests.Session()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for page in range(1, max_pages + 1):
        url = (
            SONGKICK_WARSAW_URL
            if page == 1
            else f"{SONGKICK_WARSAW_URL}?page={page}"
        )
        try:
            resp = http.get(
                url,
                headers={"User-Agent": OVERPASS_USER_AGENT},
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logging.warning("Songkick page %d failed: %s", page, exc)
            continue

        page_rows = parse_songkick_html(resp.text)
        if not page_rows:
            break
        before_count = len(rows_by_id)
        for row in page_rows:
            rows_by_id[row["id"]] = row
        if len(rows_by_id) == before_count:
            break

    return list(rows_by_id.values())


_WAW4FREE_BOX_RE = re.compile(
    r'<div class="box(?:\s+[^"]*)?">(.*?)'
    r'(?=<div class="box(?:\s+[^"]*)?">'
    r'|<div class="pagination|<div id="footer|$)',
    re.S,
)
_WAW4FREE_LINK_RE = re.compile(
    r'<div class="box-title">\s*<a[^>]*'
    r'href="(wydarzenie-(\d+)-[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
_WAW4FREE_IMG_RE = re.compile(r"background-image:\s*url\('([^']+)'\)")
_WAW4FREE_CAT_RE = re.compile(
    r'<div class="b-c-[^"]+">\s*<a[^>]*>(.*?)</a>', re.S
)
_WAW4FREE_DATA_RE = re.compile(r'<div class="box-data">(.*?)</div>', re.S)
_WAW4FREE_ISO_DATE_RE = re.compile(r"warszawa-wydarzenia-(\d{4}-\d{2}-\d{2})")
_WAW4FREE_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_WAW4FREE_DISTRICT_RE = re.compile(
    r'href="warszawa-za-darmo-[^"]+"[^>]*>([^<]+)</a>'
)


def parse_waw4free_html(
    html: str,
    default_category: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    """Parse Warsaw free entertainment events from waw4free.pl HTML."""
    today = reference_date or datetime.now(timezone.utc).date()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for chunk in _WAW4FREE_BOX_RE.findall(html):
        link_m = _WAW4FREE_LINK_RE.search(chunk)
        if not link_m:
            continue
        rel_href, event_num, raw_title = (
            link_m.group(1),
            link_m.group(2),
            link_m.group(3),
        )
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        if not title:
            continue

        data_m = _WAW4FREE_DATA_RE.search(chunk)
        data_html = data_m.group(1) if data_m else ""

        iso_dates = _WAW4FREE_ISO_DATE_RE.findall(data_html)
        has_today = "w-warszawie-za-darmo-dzisiaj" in data_html
        has_tomorrow = "w-warszawie-za-darmo-jutro" in data_html

        start_day: Optional[str] = None
        end_day: Optional[str] = None
        if has_today:
            start_day = today.isoformat()
            if iso_dates:
                end_day = iso_dates[-1]
        elif has_tomorrow:
            start_day = (today + timedelta(days=1)).isoformat()
            if iso_dates:
                end_day = iso_dates[-1]
        elif iso_dates:
            start_day = iso_dates[0]
            if len(iso_dates) > 1:
                end_day = iso_dates[-1]

        if not start_day:
            continue

        time_m = _WAW4FREE_TIME_RE.search(data_html)
        if time_m:
            hhmm = time_m.group(1)
            if len(hhmm) == 4:
                hhmm = f"0{hhmm}"
            start_date = f"{start_day}T{hhmm}:00"
        else:
            start_date = start_day

        cats = [
            html_lib.unescape(c.strip())
            for c in _WAW4FREE_CAT_RE.findall(chunk)
            if c.strip()
        ]
        if default_category and default_category not in cats:
            cats.insert(0, default_category)
        category = cats[0] if cats else (default_category or "rozrywka")

        dist_m = _WAW4FREE_DISTRICT_RE.search(data_html)
        district = (
            html_lib.unescape(dist_m.group(1)).strip() if dist_m else None
        )
        coords = WARSAW_DISTRICT_COORDS.get(district or "")
        lat = coords[0] if coords else None
        lon = coords[1] if coords else None

        img_m = _WAW4FREE_IMG_RE.search(chunk)
        img_path = img_m.group(1).strip() if img_m else None
        image_url = (
            f"{WAW4FREE_BASE_URL}{img_path}"
            if img_path and img_path.startswith("/")
            else img_path
        )
        full_url = f"{WAW4FREE_BASE_URL}/{rel_href.lstrip('/')}"
        ext_id = f"waw4free:{event_num}"

        rows_by_id[ext_id] = {
            "id": ext_id,
            "source": "waw4free",
            "title": title,
            "category": category,
            "start_date": start_date,
            "end_date": end_day,
            "venue_name": None,
            "address": f"{district}, Warszawa" if district else "Warszawa",
            "district": district,
            "city": "Warszawa",
            "lat": lat,
            "lon": lon,
            "url": full_url,
            "image_url": image_url,
            "description": None,
            "performers": [],
            "is_free": "yes",
            "raw_data": {
                "id": ext_id,
                "title": title,
                "categories": cats,
                "start_date": start_date,
                "end_date": end_day,
                "district": district,
                "url": full_url,
                "image_url": image_url,
            },
        }

    return list(rows_by_id.values())


def fetch_waw4free_events(
    session: Optional[requests.Session] = None,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetch Warsaw entertainment events across Waw4Free category pages."""
    http = session or requests.Session()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for slug, cat_label in WAW4FREE_LISTINGS:
        url = f"{WAW4FREE_BASE_URL}/{slug}"
        try:
            resp = http.get(
                url,
                headers={"User-Agent": OVERPASS_USER_AGENT},
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logging.warning("Waw4Free listing %s failed: %s", slug, exc)
            continue

        for row in parse_waw4free_html(resp.text, default_category=cat_label):
            existing = rows_by_id.get(row["id"])
            if existing is not None:
                raw_existing = existing.get("raw_data") or {}
                raw_new = row.get("raw_data") or {}
                merged_cats = list(
                    dict.fromkeys(
                        [
                            *(raw_existing.get("categories") or []),
                            *(raw_new.get("categories") or []),
                        ]
                    )
                )
                raw_existing["categories"] = merged_cats
            else:
                rows_by_id[row["id"]] = row

    return list(rows_by_id.values())


def fetch_entertainment_events(
    session: Optional[requests.Session] = None,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetch Warsaw concerts and entertainment events (Songkick + Waw4Free)."""
    http = session or requests.Session()
    songkick_rows = fetch_songkick_events(session=http, timeout=timeout)
    waw4free_rows = fetch_waw4free_events(session=http, timeout=timeout)
    return [*songkick_rows, *waw4free_rows]
