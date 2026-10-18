"""Metro stations and bus stations in Warsaw from OpenStreetMap, as map places (the pin box's
"Metro & bus stations" layer). Only the stations, not the thousands of stops: metro stations
(railway=station + station=subway, ~40) and bus stations / terminals (amenity=bus_station, ~30).
Data © OpenStreetMap contributors (ODbL). Stations change rarely: refreshed once a week.
"""

from app.ingest.base import RawEvent, SourceSpec
from app.ingest.overpass import overpass

QUERY = (
    "[out:json][timeout:180];"
    'area["name"="Warszawa"]["boundary"="administrative"]->.a;('
    'nwr["railway"="station"]["station"="subway"](area.a);'
    'nwr["amenity"="bus_station"](area.a);'
    ");out center tags;"
)


def fetch_records() -> list[dict]:
    return overpass(QUERY)


def metro_line(ref: str | None) -> str | None:
    """Warsaw's station refs: A.. on line M1, C.. on line M2."""
    return {"A": "M1", "C": "M2"}.get((ref or "")[:1].upper())


def parse(records: list[dict]) -> list[RawEvent]:
    out = []
    for el in records:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        metro = tags.get("station") == "subway"
        if not name or lat is None or lng is None or not el.get("type"):
            continue
        if not metro and tags.get("amenity") != "bus_station":
            continue
        osm_id = f"{el['type']}/{el['id']}"
        line = metro_line(tags.get("ref")) if metro else None
        out.append(
            RawEvent(
                source_slug="osm_transit",
                external_key=osm_id,
                title=f"Metro {name}" if metro and not name.lower().startswith("metro") else name,
                kind="place",
                categories_raw=["osm:subway_station" if metro else "osm:bus_station"],
                lead=" · ".join(x for x in ("Metro" if metro else "Bus station", line) if x),
                url=f"https://www.openstreetmap.org/{osm_id}",
                venue_name=name,
                lat=float(lat),
                lng=float(lng),
                raw=el,
            )
        )
    return out


SPECS = [
    SourceSpec(
        slug="osm_transit",
        name="OpenStreetMap – metro and bus stations (© OpenStreetMap contributors)",
        url="https://www.openstreetmap.org",
        fetch_records=fetch_records,
        parse=parse,
        refresh_hours=24 * 7,
    )
]
