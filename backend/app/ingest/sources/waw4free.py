"""Warsaw entertainment events, concerts, parties and free events from waw4free.pl.

Iterates across Waw4Free Warsaw category pages, continuing past any single-page HTTP
error so a failed listing never drops the remaining categories.
"""

import html as html_lib
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.ingest.base import Occurrence, RawEvent, SourceSpec

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
WAW4FREE_BASE_URL = "https://waw4free.pl"

WAW4FREE_LISTINGS = (
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

BOX_RE = re.compile(
    r'<div class="box(?:\s+[^"]*)?">(.*?)(?=<div class="box(?:\s+[^"]*)?">|<div class="pagination|<div id="footer|$)',
    re.S,
)
LINK_RE = re.compile(r'<div class="box-title">\s*<a[^>]*href="(wydarzenie-(\d+)-[^"]+)"[^>]*>(.*?)</a>', re.S)
IMG_RE = re.compile(r"background-image:\s*url\('([^']+)'\)")
CAT_RE = re.compile(r'<div class="b-c-[^"]+">\s*<a[^>]*>(.*?)</a>', re.S)
DATA_RE = re.compile(r'<div class="box-data">(.*?)</div>', re.S)
ISO_DATE_RE = re.compile(r"warszawa-wydarzenia-(\d{4}-\d{2}-\d{2})")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
DISTRICT_RE = re.compile(r'href="warszawa-za-darmo-[^"]+"[^>]*>([^<]+)</a>')


def _extract_cards_from_html(html: str, default_category: str) -> list[dict]:
    today = datetime.now(WARSAW_TZ).date()
    cards: list[dict] = []
    for chunk in BOX_RE.findall(html):
        link_m = LINK_RE.search(chunk)
        if not link_m:
            continue
        rel_href, event_id, raw_title = link_m.group(1), link_m.group(2), link_m.group(3)
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        if not title:
            continue

        data_m = DATA_RE.search(chunk)
        data_html = data_m.group(1) if data_m else ""
        iso_dates = ISO_DATE_RE.findall(data_html)

        start_day: str | None = None
        end_day: str | None = None
        if "w-warszawie-za-darmo-dzisiaj" in data_html:
            start_day = today.isoformat()
            if iso_dates:
                end_day = iso_dates[-1]
        elif "w-warszawie-za-darmo-jutro" in data_html:
            start_day = (today + timedelta(days=1)).isoformat()
            if iso_dates:
                end_day = iso_dates[-1]
        elif iso_dates:
            start_day = iso_dates[0]
            if len(iso_dates) > 1:
                end_day = iso_dates[-1]
        if not start_day:
            continue

        time_m = TIME_RE.search(data_html)
        hhmm = time_m.group(1) if time_m else "18:00"
        if len(hhmm) == 4:
            hhmm = f"0{hhmm}"

        cats = [html_lib.unescape(c.strip()) for c in CAT_RE.findall(chunk) if c.strip()]
        if default_category and default_category not in cats:
            cats.insert(0, default_category)

        dist_m = DISTRICT_RE.search(data_html)
        district = html_lib.unescape(dist_m.group(1)).strip() if dist_m else None

        img_m = IMG_RE.search(chunk)
        img_path = img_m.group(1).strip() if img_m else None
        image_url = f"{WAW4FREE_BASE_URL}{img_path}" if img_path and img_path.startswith("/") else img_path

        cards.append(
            {
                "id": event_id,
                "title": title,
                "url": f"{WAW4FREE_BASE_URL}/{rel_href.lstrip('/')}",
                "image_url": image_url,
                "categories": cats,
                "start_date": f"{start_day}T{hhmm}:00",
                "end_date": end_day,
                "district": district,
            }
        )
    return cards


def fetch_records() -> list[dict]:
    by_id: dict[str, dict] = {}
    headers = {"User-Agent": settings.nominatim_user_agent}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        for slug, cat_label in WAW4FREE_LISTINGS:
            try:
                resp = client.get(f"{WAW4FREE_BASE_URL}/{slug}")
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            for card in _extract_cards_from_html(resp.text, default_category=cat_label):
                existing = by_id.get(card["id"])
                if existing is not None:
                    existing["categories"] = list(
                        dict.fromkeys([*existing.get("categories", []), *card.get("categories", [])])
                    )
                else:
                    by_id[card["id"]] = card
    return list(by_id.values())


def _parse_dt(val: str | None, default_hour: int = 18) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
    except ValueError:
        return None
    if "T" not in val and " " not in val:
        dt = datetime.combine(dt.date(), time(default_hour, 0))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=WARSAW_TZ)


def parse(records: list[dict]) -> list[RawEvent]:
    seen: set[str] = set()
    out: list[RawEvent] = []
    for rec in records:
        ext_key = str(rec.get("id") or "").strip()
        title = str(rec.get("title") or "").strip()
        starts_at = _parse_dt(rec.get("start_date"), default_hour=18)
        if not ext_key or not title or starts_at is None or ext_key in seen:
            continue
        seen.add(ext_key)

        ends_at = _parse_dt(rec.get("end_date"), default_hour=22)
        if ends_at is not None and ends_at < starts_at:
            ends_at = None

        district = (rec.get("district") or "").strip() or None
        coords = WARSAW_DISTRICT_COORDS.get(district or "")
        lat = coords[0] if coords else None
        lng = coords[1] if coords else None

        cats_raw = [f"waw4free:{c.lower()}" for c in (rec.get("categories") or []) if isinstance(c, str)]

        out.append(
            RawEvent(
                source_slug="waw4free",
                external_key=ext_key,
                title=title,
                kind="event",
                categories_raw=cats_raw or ["waw4free:rozrywka"],
                lead="Wstęp wolny",
                image_url=rec.get("image_url"),
                url=rec.get("url"),
                language="pl",
                district=district,
                address=f"{district}, Warszawa" if district else "Warszawa",
                lat=lat,
                lng=lng,
                occurrences=[Occurrence(starts_at=starts_at, ends_at=ends_at)],
                raw=rec,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="waw4free",
        name="Waw4Free – darmowe wydarzenia i koncerty w Warszawie",
        url=WAW4FREE_BASE_URL,
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=4,
    )
]
