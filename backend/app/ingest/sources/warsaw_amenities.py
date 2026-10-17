"""Warsaw Open Data amenities: public toilets and defibrillators (AED), as map places.

Ported from Kamil's postgre-aws ingestor (src/ingestor.py: ingest_toilets, ingest_defibrillators):
same endpoints and fields, but it returns RawEvents for the shared pipeline. Coordinates come
with the data, so nothing is geocoded. /places hides these unless asked: ?category=toilets / aed.
"""

import hashlib

from app.ingest.base import RawEvent, SourceSpec
from app.ingest.sources.warsaw_open_data import PL_WEEKDAYS, fetch, parse_hours


def toilet_hours(s: str | None) -> dict[str, str] | None:
    """'Poniedziałek: 06:00 - 22:00; ...; Niedziela: nieczynne' -> {"monday": "06:00-22:00", ...}"""
    hours = {}
    for part in (s or "").split(";"):
        day, _, value = part.partition(":")
        en, value = PL_WEEKDAYS.get(day.strip()), value.strip()
        if not en or not value or value.lower() == "nieczynne":
            continue
        hours[en] = "00:00-24:00" if value.lower() == "całodobowo" else parse_hours(value)
    return hours or None


def parse_toilets(records: list[dict]) -> list[RawEvent]:
    out = []
    for rec in records:
        p = rec.get("properties") or {}
        coords = (rec.get("geometry") or {}).get("coordinates") or []
        where = (p.get("lokalizacja") or "").strip()
        if len(coords) < 2 or not where:
            continue
        lng, lat = float(coords[0]), float(coords[1])
        facts = [
            p.get("typ"),
            {0: "bezpłatna", 1: "płatna"}.get(p.get("platnosc")),
            "dostosowana dla osób z niepełnosprawnościami" if p.get("dostepnosc") == 1 else None,
            "przewijak" if p.get("przewijak") == 1 else None,
            p.get("uwagi"),
        ]
        out.append(
            RawEvent(
                source_slug="warsaw_toilets",
                external_key=hashlib.sha1(f"{where}|{lng:.6f}|{lat:.6f}".encode()).hexdigest(),
                title=f"Toaleta – {where}",
                kind="place",
                categories_raw=["toaleta"],
                text_plain="; ".join(f for f in facts if f) or None,
                district=p.get("dzielnica"),
                venue_name=p.get("zarzadca"),
                address=where,
                lat=lat,
                lng=lng,
                opening_hours=toilet_hours(p.get("godziny")),
                raw=rec,
            )
        )
    return out


def parse_aeds(records: list[dict]) -> list[RawEvent]:
    out = []
    for rec in records:
        p = rec.get("properties") or {}
        coords = (rec.get("geometry") or {}).get("coordinates") or []
        if coords and isinstance(coords[0], list):  # [[lon, lat]]
            coords = coords[0]
        if len(coords) < 2 or not p.get("defibrillator_id"):
            continue
        street = " ".join(x for x in (p.get("location_street"), p.get("location_building")) if x)
        town = " ".join(x for x in (p.get("location_postcode"), p.get("location_city")) if x)
        name = p.get("location_object_name") or street or "AED"
        facts = [
            p.get("device_location"),
            p.get("location_description"),
            p.get("device_access_description"),
            f"dostęp: {p['device_public_access'].lower()}" if p.get("device_public_access") else None,
        ]
        out.append(
            RawEvent(
                source_slug="warsaw_aed",
                external_key=str(p["defibrillator_id"]),
                title=f"Defibrylator AED – {name}",
                kind="place",
                categories_raw=["defibrylator"],
                text_plain="; ".join(f for f in facts if f) or None,
                venue_name=p.get("location_object_name"),
                address=", ".join(x for x in (street, town) if x) or None,
                lat=float(coords[1]),
                lng=float(coords[0]),
                raw=rec,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="warsaw_toilets",
        name="Warsaw Open Data – public toilets",
        url="https://dane.um.warszawa.pl",
        fetch_records=lambda: fetch("get_m_toalety"),
        parse=parse_toilets,
    ),
    SourceSpec(
        slug="warsaw_aed",
        name="Warsaw Open Data – defibrillators (AED)",
        url="https://dane.um.warszawa.pl",
        fetch_records=lambda: fetch("get_scb_lokalizacja_defibrylatorow"),
        parse=parse_aeds,
    ),
]
