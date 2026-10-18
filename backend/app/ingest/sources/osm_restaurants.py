"""OpenStreetMap restaurants, cafes, bars, pubs, biergartens and food courts in Warsaw, as map places.

Ported from Kamil's restaurants ingestor (src/external_sources.py): same Overpass query
and tag mapping, returning RawEvents (kind="place") for the shared pipeline.
Data © OpenStreetMap contributors (ODbL). Refreshed once a day.
"""

from app.ingest.base import RawEvent, SourceSpec
from app.ingest.overpass import overpass
from app.ingest.sources.osm_venues import osm_hours

RESTAURANT_AMENITIES = (
    "restaurant",
    "cafe",
    "bar",
    "pub",
    "biergarten",
    "food_court",
)
QUERY = (
    "[out:json][timeout:180];"
    'area["name"="Warszawa"]["boundary"="administrative"]->.a;'
    f'(nwr["amenity"~"^({"|".join(RESTAURANT_AMENITIES)})$"](area.a););'
    "out center tags;"
)


def fetch_records() -> list[dict]:
    return overpass(QUERY)


def parse(records: list[dict]) -> list[RawEvent]:
    out = []
    for el in records:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        amenity = tags.get("amenity")
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        if (
            not name
            or amenity not in RESTAURANT_AMENITIES
            or lat is None
            or lng is None
            or not el.get("type")
        ):
            continue
        lat_f, lng_f = float(lat), float(lng)
        if not (52.0 < lat_f < 52.5 and 20.7 < lng_f < 21.4):
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
        cuisine = (tags.get("cuisine") or "").replace(";", ", ").strip()
        lead_parts = [p for p in (amenity.replace("_", " ").title(), cuisine) if p]
        out.append(
            RawEvent(
                source_slug="osm_restaurants",
                external_key=osm_id,
                title=name,
                kind="place",
                categories_raw=[f"osm:{amenity}"],
                lead=" · ".join(lead_parts) if lead_parts else None,
                text_plain=tags.get("description"),
                url=contact["www"] or f"https://www.openstreetmap.org/{osm_id}",
                venue_name=name,
                address=", ".join(x for x in (street, town) if x) or None,
                lat=lat_f,
                lng=lng_f,
                contact={k: v for k, v in contact.items() if v},
                opening_hours=osm_hours(tags.get("opening_hours")),
                capacity=int(tags["capacity"]) if str(tags.get("capacity", "")).isdigit() else None,
                raw=el,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="osm_restaurants",
        name="OpenStreetMap – restaurants, cafes & bars (© OpenStreetMap contributors)",
        url="https://www.openstreetmap.org",
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=24,
    )
]
