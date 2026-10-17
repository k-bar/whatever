"""Ticketed cultural and entertainment events in Warsaw from kupbilecik.pl."""

import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, text

from app.db import engine
from app.ingest.base import Occurrence, RawEvent, SourceSpec

BASE = "https://www.kupbilecik.pl/pl/"
USER_AGENT = "Mozilla/5.0 (compatible; HackatonEventsBot/1.0)"
WARSAW = ZoneInfo("Europe/Warsaw")

LISTINGS: dict[str, str | None] = {
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

LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
EVENT_ID_RE = re.compile(r"/(?:event|imprezy)/(\d+)/")


def _clean(val: object) -> str | None:
    if not isinstance(val, str) or not val:
        return None
    text_val = html.unescape(val).strip()
    return text_val or None


def _split_dt(val: object) -> tuple[str | None, str | None]:
    if not isinstance(val, str) or not val:
        return None, None
    try:
        dt = datetime.fromisoformat(val)
    except ValueError:
        return val[:10], None
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _short_schema(val: object) -> str | None:
    return val.rsplit("/", 1)[-1] if isinstance(val, str) and val else None


def _iter_ld_items(page_html: str):
    for raw in LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for node in data.get("@graph", [data]):
            if not isinstance(node, dict):
                continue
            lists = [node] if node.get("@type") == "ItemList" else []
            main = node.get("mainEntity")
            if isinstance(main, dict) and main.get("@type") == "ItemList":
                lists.append(main)
            for lst in lists:
                for el in lst.get("itemListElement") or []:
                    if not isinstance(el, dict):
                        continue
                    item = el.get("item", el)
                    if isinstance(item, dict):
                        item = item.get("itemReviewed", item)
                    if isinstance(item, dict) and item.get("startDate") and item.get("url"):
                        yield item


def _to_row(item: dict, category: str | None) -> dict | None:
    url = item.get("url")
    if not isinstance(url, str):
        return None
    m = EVENT_ID_RE.search(url)
    if not m:
        return None
    place = item.get("location") or {}
    if isinstance(place, list):
        place = place[0] if place else {}
    addr = (place.get("address") if isinstance(place, dict) else None) or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    offer = item.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    date_s, time_s = _split_dt(item.get("startDate"))
    end_date, end_time = _split_dt(item.get("endDate"))
    raw_price = offer.get("price") if isinstance(offer, dict) else None
    if raw_price is None and isinstance(offer, dict):
        raw_price = offer.get("lowPrice")
    price = float(raw_price) if raw_price not in (None, "") else None
    return {
        "id": int(m.group(1)),
        "name": _clean(item.get("name")),
        "date": date_s,
        "time": time_s,
        "end_date": end_date,
        "end_time": end_time,
        "location": _clean(place.get("name")) if isinstance(place, dict) else None,
        "address": _clean(addr.get("streetAddress")) if isinstance(addr, dict) else None,
        "city": _clean(addr.get("addressLocality")) if isinstance(addr, dict) else None,
        "postcode": _clean(addr.get("postalCode")) if isinstance(addr, dict) else None,
        "region": _clean(addr.get("addressRegion")) if isinstance(addr, dict) else None,
        "category": category,
        "event_type": _clean(item.get("@type")),
        "price": price,
        "currency": _clean(offer.get("priceCurrency")) if isinstance(offer, dict) else None,
        "availability": _short_schema(offer.get("availability")) if isinstance(offer, dict) else None,
        "status": _short_schema(item.get("eventStatus")),
        "url": url,
        "image_url": item.get("image") if isinstance(item.get("image"), str) else None,
        "description": _clean(item.get("description")),
    }


def _load_from_db_table() -> list[dict]:
    """Read already-ingested Warsaw rows from kupbilecik_events if available."""
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("kupbilecik_events"):
                return []
            rows = conn.execute(
                text("SELECT * FROM kupbilecik_events WHERE LOWER(city) IN ('warszawa', 'warsaw')")
            ).mappings()
            return [dict(r) for r in rows]
    except Exception:
        return []


def fetch_records() -> list[dict]:
    by_id: dict[int, dict] = {}
    for path, cat in LISTINGS.items():
        req = urllib.request.Request(f"{BASE}{path}?page=1", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                page_html = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            break
        for item in _iter_ld_items(page_html):
            row = _to_row(item, cat)
            if row and row["id"] not in by_id:
                by_id[row["id"]] = row
    if by_id:
        return list(by_id.values())
    return _load_from_db_table()


def _parse_aware_dt(date_s: str | None, time_s: str | None) -> datetime | None:
    if not date_s:
        return None
    tm = time_s if time_s and re.fullmatch(r"\d{2}:\d{2}", time_s) else "19:00"
    try:
        return datetime.fromisoformat(f"{date_s}T{tm}:00").replace(tzinfo=WARSAW)
    except ValueError:
        return None


def parse(records: list[dict]) -> list[RawEvent]:
    out: list[RawEvent] = []
    seen_keys: set[str] = set()
    for r in records:
        city = (r.get("city") or "").strip().lower()
        if city not in ("warszawa", "warsaw"):
            continue
        title = (r.get("name") or "").strip()
        url = (r.get("url") or "").strip()
        starts_at = _parse_aware_dt(r.get("date"), r.get("time"))
        if not title or not url or starts_at is None or url in seen_keys:
            continue
        seen_keys.add(url)
        ends_at = _parse_aware_dt(r.get("end_date"), r.get("end_time"))
        if ends_at is not None and ends_at < starts_at:
            ends_at = None
        cats = [str(c) for c in (r.get("category"), r.get("event_type")) if c]
        addr_parts = [str(x).strip() for x in (r.get("address"), r.get("postcode")) if x]
        raw_copy = {k: str(v) if isinstance(v, datetime) else v for k, v in r.items()}
        out.append(
            RawEvent(
                source_slug="kupbilecik",
                external_key=url,
                title=title,
                kind="event",
                categories_raw=cats,
                text_plain=r.get("description"),
                image_url=r.get("image_url"),
                url=url,
                venue_name=r.get("location"),
                address=", ".join(addr_parts) or None,
                occurrences=[Occurrence(starts_at=starts_at, ends_at=ends_at)],
                raw=raw_copy,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="kupbilecik",
        name="KupBilecik.pl – ticketed events in Warsaw",
        url="https://www.kupbilecik.pl",
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=12,
    )
]
