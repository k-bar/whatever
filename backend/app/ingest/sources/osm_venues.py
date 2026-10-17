"""OpenStreetMap venues in Warsaw (theatres, cinemas, clubs, museums, stadiums...), as map places.

Ported from Kamil's postgre-aws ingestor (src/external_sources.py: streets.gl venues): same
Overpass query and tag mapping, but it returns RawEvents for the shared pipeline.
Data © OpenStreetMap contributors (ODbL). Venues change slowly: refreshed once a day.
"""

import json
import re
import urllib.parse
import urllib.request

from app.config import settings
from app.ingest.base import RawEvent, SourceSpec

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
VENUE_TAGS = {
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
QUERY = (
    "[out:json][timeout:180];"
    'area["name"="Warszawa"]["boundary"="administrative"]->.a;('
    + "".join(f'nwr["{k}"~"^({"|".join(v)})$"](area.a);' for k, v in VENUE_TAGS.items())
    + ");out center tags;"
)
OSM_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
EN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fetch_records() -> list[dict]:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    last_error: Exception | None = None
    for url in OVERPASS_URLS:  # mirrors share the load; try the next one if busy
        req = urllib.request.Request(url, data=body, headers={"User-Agent": settings.nominatim_user_agent})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.loads(r.read().decode("utf-8")).get("elements", [])
        except OSError as e:
            last_error = e
    raise RuntimeError(f"all Overpass mirrors failed: {last_error}")


def osm_hours(s: str | None) -> dict[str, str] | None:
    """Common OSM opening_hours ('Mo-Fr 10:00-18:00; Sa 10:00-14:00', '24/7') -> per-day dict.

    Anything fancier (dates, holidays, open ends) is skipped; the raw string stays in `raw`.
    """
    if not s:
        return None
    if s.strip() == "24/7":
        return dict.fromkeys(EN_DAYS, "00:00-24:00")
    hours = {}
    for rule in s.split(";"):
        m = re.fullmatch(r"\s*([A-Z][a-z](?:[-,][A-Z][a-z])*)\s+(\d{2}:\d{2}-\d{2}:\d{2})\s*", rule)
        if not m:
            continue
        for part in m[1].split(","):
            first, _, last = part.partition("-")
            if first not in OSM_DAYS or (last and last not in OSM_DAYS):
                continue
            i, j = OSM_DAYS.index(first), OSM_DAYS.index(last or first)
            for k in range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]:  # Su-Fr wraps
                hours[EN_DAYS[k]] = m[2]
    return hours or None


def venue_type(tags: dict) -> str | None:
    for key, values in VENUE_TAGS.items():
        if tags.get(key) in values:
            return tags[key]
    return None


def parse(records: list[dict]) -> list[RawEvent]:
    out = []
    for el in records:
        tags = el.get("tags") or {}
        name, kind = (tags.get("name") or "").strip(), venue_type(tags)
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        if not name or not kind or lat is None or lng is None or not el.get("type"):
            continue
        osm_id = f"{el['type']}/{el['id']}"
        street = " ".join(
            x for x in (tags.get("addr:street") or tags.get("addr:place"), tags.get("addr:housenumber")) if x
        )
        town = " ".join(x for x in (tags.get("addr:postcode"), tags.get("addr:city")) if x)
        contact = {
            "www": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "email": tags.get("email") or tags.get("contact:email"),
        }
        out.append(
            RawEvent(
                source_slug="osm_venues",
                external_key=osm_id,
                title=name,
                kind="place",
                categories_raw=[f"osm:{kind}"],
                text_plain=tags.get("description"),
                url=contact["www"] or f"https://www.openstreetmap.org/{osm_id}",
                venue_name=name,
                address=", ".join(x for x in (street, town) if x) or None,
                lat=float(lat),
                lng=float(lng),
                contact={k: v for k, v in contact.items() if v},
                opening_hours=osm_hours(tags.get("opening_hours")),
                capacity=int(tags["capacity"]) if str(tags.get("capacity", "")).isdigit() else None,
                raw=el,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="osm_venues",
        name="OpenStreetMap – venues (© OpenStreetMap contributors)",
        url="https://www.openstreetmap.org",
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=24,
    )
]
