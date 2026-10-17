"""Warsaw Open Data (dane.um.warszawa.pl): event calendar, sport classes, open school pitches.

Ported from Mateusz's fetch_data.py: same API calls and field parsing, but it returns
RawEvents instead of writing SQLite. Token: https://dane.um.warszawa.pl/en/key-api
"""

import hashlib
import html
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.ingest.base import Occurrence, RawEvent, SourceSpec

API = "https://dane.um.warszawa.pl/api/action/"
WARSAW = ZoneInfo("Europe/Warsaw")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PL_WEEKDAYS = {
    "Poniedziałek": "monday",
    "Wtorek": "tuesday",
    "Środa": "wednesday",
    "Czwartek": "thursday",
    "Piątek": "friday",
    "Sobota": "saturday",
    "Niedziela": "sunday",
}
RECURRING_WEEKS = 5  # weekly sport classes without explicit dates: generate this many weeks ahead


def fetch(action: str) -> list[dict]:
    if not settings.warsaw_api_token:
        raise RuntimeError("WARSAW_API_TOKEN is not set (https://dane.um.warszawa.pl/en/key-api)")
    with urllib.request.urlopen(api_request(action), timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return as_records(data)


def api_request(action: str) -> urllib.request.Request:
    """POST to the API, through the relay when one is configured (see config.py)."""
    if not settings.warsaw_relay_url:
        return urllib.request.Request(
            API + action, method="POST", headers={"Authorization": settings.warsaw_api_token}
        )
    return urllib.request.Request(
        settings.warsaw_relay_url,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.warsaw_relay_token}",
            "X-Relay-Target": API + action,
            "X-Relay-Authorization": settings.warsaw_api_token,
        },
    )


def as_records(data):
    """The API may return a list or wrap it (result / results / records)."""
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


def names(items) -> list[str]:
    return [i["name"] for i in items or [] if isinstance(i, dict) and i.get("name")]


def image_url(rec):
    img = rec.get("image") or {}
    path = ((img.get("small") or img.get("highlighted") or {}).get("path") or "").replace("\n", "")
    return path or None


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=WARSAW)


def first_value(v):
    if isinstance(v, list):
        return "; ".join(str(x) for x in v if x) or None
    return v or None


def first_address(rec) -> tuple[str | None, str | None, dict[str, str]]:
    """(venue name, "street, postcode city", contact) of the first usable address."""
    for a in rec.get("address") or []:
        if isinstance(a, dict) and (a.get("name") or a.get("street")):
            street = ", ".join(x for x in (a.get("street"), a.get("postCodeAndOffice")) if x) or None
            contact = {k: first_value(a.get(k)) for k in ("phone", "email", "www")}
            return a.get("name"), street, {k: v for k, v in contact.items() if v}
    return None, None, {}


# --- Event calendar ---------------------------------------------------------------------------


def parse_events(records: list[dict]) -> list[RawEvent]:
    out = []
    for rec in records:
        if not rec.get("url") or not rec.get("title"):
            continue
        occ = rec.get("occurrence") or rec.get("occurence") or []
        feats = ((rec.get("map") or {}).get("features")) or []
        lat = lng = district = street = None
        for f in feats:
            coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
            if coords[0] is not None:
                p = f.get("properties") or {}
                lng, lat = coords[0], coords[1]
                district = p.get("district")
                street = (
                    " ".join(
                        x
                        for x in (p.get("shortStreetName") or p.get("fullStreetName"), p.get("streetNumber"))
                        if x
                    )
                    or None
                )
                break
        venue, addr_street, contact = first_address(rec)
        out.append(
            RawEvent(
                source_slug="warsaw_events",
                external_key=rec["url"],
                title=rec["title"],
                kind="event",
                categories_raw=names(rec.get("category")),
                lead=rec.get("lead"),
                text_plain=strip_html(rec.get("text")),
                text_html=rec.get("text"),
                image_url=image_url(rec),
                url=rec["url"],
                language=rec.get("language"),
                district=(names(rec.get("localization")) or [district])[0],
                venue_name=venue,
                address=addr_street or street,
                contact=contact,
                lat=lat,
                lng=lng,
                occurrences=[
                    Occurrence(
                        starts_at=parse_dt(o["from"]),
                        ends_at=parse_dt(o.get("to")),
                        daily=bool(o.get("daily")),
                    )
                    for o in occ
                    if o.get("from")
                ],
                raw=rec,
            )
        )
    return out


# --- Sport classes ----------------------------------------------------------------------------


def class_occurrences(rec, today: date | None = None) -> list[Occurrence]:
    time = rec.get("time")
    if not time or not re.fullmatch(r"\d{1,2}:\d{2}", time):
        return []
    hh, mm = map(int, time.split(":"))
    if rec.get("date"):
        days = [date.fromisoformat(d) for d in rec["date"]]
    else:
        weekdays = {d.get("id") for d in rec.get("day") or [] if isinstance(d, dict)}
        today = today or date.today()
        days = [
            today + timedelta(days=i)
            for i in range(RECURRING_WEEKS * 7)
            if WEEKDAYS[(today + timedelta(days=i)).weekday()] in weekdays
        ]
    out = []
    for d in days:
        start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=WARSAW)
        out.append(Occurrence(starts_at=start, ends_at=start + timedelta(hours=1)))
    return out


def parse_sport_classes(records: list[dict]) -> list[RawEvent]:
    out = []
    for rec in records:
        if not rec.get("url") or not rec.get("title"):
            continue
        venue, street, contact = first_address(rec)
        out.append(
            RawEvent(
                source_slug="warsaw_sport",
                external_key=rec["url"],
                title=rec["title"],
                kind="class",
                categories_raw=names(rec.get("category") or rec.get("kategoria")),
                text_plain=strip_html(rec.get("text")),
                text_html=rec.get("text"),
                image_url=image_url(rec),
                url=rec["url"],
                language=rec.get("language"),
                district=(names(rec.get("localization")) or [None])[0],
                venue_name=venue,
                address=street or venue,
                contact=contact,
                occurrences=class_occurrences(rec),
                audience=names(rec.get("dedicated")),
                raw=rec,
            )
        )
    return out


# --- Open school pitches ----------------------------------------------------------------------


def parse_hours(s: str | None) -> str | None:
    """'Od 17:00 do 22:00' -> '17:00-22:00'. Anything else is kept as-is."""
    if not s:
        return None
    m = re.search(r"(\d{1,2}[:.]\d{2})\D+(\d{1,2}[:.]\d{2})", s)
    return f"{m[1].replace('.', ':')}-{m[2].replace('.', ':')}" if m else s.strip()


def parse_pitches(records: list[dict]) -> list[RawEvent]:
    out, seen = [], set()
    for rec in records:
        address = rec.get("Adres obiektu")
        if not address:
            continue
        key = hashlib.sha1(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if key in seen:  # the dataset contains exact duplicates
            continue
        seen.add(key)
        school = rec.get("Nazwa placówki oświatowej")
        obj_type = rec.get("Typ obiektu") or "boisko"
        equipment = [e.strip() for e in (rec.get("Boisk uniwersalne zawiera") or "").split("-") if e.strip()]
        hours = {en: parse_hours(rec.get(pl)) for pl, en in PL_WEEKDAYS.items()}
        notes = rec.get("Uwagi")
        out.append(
            RawEvent(
                source_slug="warsaw_pitches",
                external_key=key,
                title=f"{obj_type.capitalize()} – {school}" if school else obj_type.capitalize(),
                kind="place",
                categories_raw=["boisko", *equipment],
                text_plain="; ".join(
                    x
                    for x in (
                        f"Nawierzchnia: {rec['Rodzaj nawierzchni']}"
                        if rec.get("Rodzaj nawierzchni")
                        else None,
                        ", ".join(equipment) or None,
                        notes,
                    )
                    if x
                )
                or None,
                district=rec.get("Dzielnica"),
                venue_name=school,
                address=address,
                opening_hours={k: v for k, v in hours.items() if v},
                raw=rec,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="warsaw_events",
        name="Warsaw Open Data – event calendar",
        url="https://dane.um.warszawa.pl",
        fetch_records=lambda: fetch("get_bmm_kalendarz_wydarzen"),
        parse=parse_events,
    ),
    SourceSpec(
        slug="warsaw_sport",
        name="Warsaw Open Data – sport classes",
        url="https://dane.um.warszawa.pl",
        fetch_records=lambda: fetch("get_bmm_zajecia_sportowe"),
        parse=parse_sport_classes,
    ),
    SourceSpec(
        slug="warsaw_pitches",
        name="Warsaw Open Data – open school pitches",
        url="https://dane.um.warszawa.pl",
        fetch_records=lambda: fetch("get_be_otwarte_boiska"),
        parse=parse_pitches,
    ),
]
