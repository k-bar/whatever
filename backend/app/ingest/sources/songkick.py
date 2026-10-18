"""Warsaw concerts and live music from Songkick (JSON-LD MusicEvent).

Fetches multiple pages of Songkick's Warsaw metro-area listings
(https://www.songkick.com/metro-areas/31787-poland-warsaw?page=1..N) and extracts
schema.org MusicEvent records with built-in venue coordinates.
"""

import json
import re
from datetime import datetime, time

import httpx

from app.config import settings
from app.ingest.base import Occurrence, RawEvent, SourceSpec
from app.timeutil import WARSAW

SONGKICK_METRO_URL = "https://www.songkick.com/metro-areas/31787-poland-warsaw"
MAX_PAGES = 5

LD_JSON_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
EVENT_ID_RE = re.compile(r"/(?:concerts|festivals/[^/]+/id)/(\d+)")


def _parse_iso_dt(raw: str | None, default_hour: int = 19) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if "T" not in text and " " not in text:
        dt = datetime.combine(dt.date(), time(default_hour, 0))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=WARSAW)


def fetch_records() -> list[dict]:
    records_by_url: dict[str, dict] = {}
    headers = {"User-Agent": settings.nominatim_user_agent}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        for page in range(1, MAX_PAGES + 1):
            url = SONGKICK_METRO_URL if page == 1 else f"{SONGKICK_METRO_URL}?page={page}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            before = len(records_by_url)
            for block in LD_JSON_RE.findall(resp.text):
                try:
                    data = json.loads(block)
                except json.JSONDecodeError:
                    continue
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "MusicEvent" and item.get("url"):
                        clean_url = str(item["url"]).split("?")[0]
                        records_by_url[clean_url] = item
            if len(records_by_url) == before:
                break
    return list(records_by_url.values())


def parse(records: list[dict]) -> list[RawEvent]:
    seen: set[str] = set()
    out: list[RawEvent] = []
    for item in records:
        if item.get("@type") != "MusicEvent":
            continue
        raw_url = str(item.get("url") or "").strip()
        clean_url = raw_url.split("?")[0]
        title = str(item.get("name") or "").strip()
        starts_at = _parse_iso_dt(item.get("startDate"), default_hour=19)
        if not clean_url or not title or starts_at is None:
            continue

        loc = item.get("location") if isinstance(item.get("location"), dict) else {}
        addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
        geo = loc.get("geo") if isinstance(loc.get("geo"), dict) else {}

        raw_lat, raw_lng = geo.get("latitude"), geo.get("longitude")
        lat = float(raw_lat) if raw_lat is not None else None
        lng = float(raw_lng) if raw_lng is not None else None
        if lat is None or lng is None or not (52.0 < lat < 52.5 and 20.7 < lng < 21.4):
            continue

        m = EVENT_ID_RE.search(clean_url)
        ext_key = m.group(1) if m else clean_url
        if ext_key in seen:
            continue
        seen.add(ext_key)

        ends_at = _parse_iso_dt(item.get("endDate"), default_hour=23)
        if ends_at is not None and ends_at < starts_at:
            ends_at = None

        venue_name = (loc.get("name") or "").strip() or None
        street = (addr.get("streetAddress") or "").strip()
        postal = (addr.get("postalCode") or "").strip()
        address = ", ".join(p for p in (street, postal, "Warszawa") if p) if street else None

        performers = [
            str(p["name"]).strip()
            for p in (item.get("performer") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        lead = f"Wykonawcy: {', '.join(performers)}" if performers else None

        out.append(
            RawEvent(
                source_slug="songkick",
                external_key=ext_key,
                title=title,
                kind="event",
                categories_raw=["songkick:concert"],
                lead=lead,
                text_plain=(item.get("description") or "").strip() or None,
                image_url=(item.get("image") or "").strip() or None,
                url=clean_url,
                venue_name=venue_name,
                address=address,
                lat=lat,
                lng=lng,
                occurrences=[Occurrence(starts_at=starts_at, ends_at=ends_at)],
                raw=item,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="songkick",
        name="Songkick – Warsaw concerts & live music",
        url=SONGKICK_METRO_URL,
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=6,
    )
]
