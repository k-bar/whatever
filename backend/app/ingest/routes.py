"""Tourist routes from Warsaw Open Data, stored in Kamil's tourist_routes shape.

Kamil owns the table (src/models.py, src/ingestor.py: ingest_tourist_routes); both his sync and
this hourly feed write the same rows, keyed on title. The API's raw traces and tourist_points are
kept as-is; GET /routes turns them into GeoJSON.
"""

from app.ingest.conditions import Feed, num
from app.models import TouristRoute


def parse_routes(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        traces, points = r.get("traces"), r.get("tourist_points")
        rows.append(
            dict(
                title=title,
                length_km=num(r.get("length")),
                description=r.get("description"),
                traces=traces if isinstance(traces, list) else [],
                tourist_points=points if isinstance(points, list) else [],
            )
        )
    return rows


def route_line(traces: list | None) -> list[list[float]]:
    """API traces are [lat, lng]; GeoJSON wants [lng, lat]. Bad pairs are dropped."""
    coords = []
    for t in traces or []:
        if isinstance(t, list) and len(t) == 2 and num(t[0]) is not None and num(t[1]) is not None:
            coords.append([num(t[1]), num(t[0])])
    return coords


def route_points(raw: list | None) -> list[dict]:
    points = []
    for p in raw or []:
        ll = p.get("latlng") if isinstance(p, dict) else None
        if isinstance(ll, dict) and num(ll.get("lat")) is not None and num(ll.get("lng")) is not None:
            points.append(
                {"id": p.get("id_point"), "name": p.get("name"), "lat": num(ll["lat"]), "lng": num(ll["lng"])}
            )
    return points


ROUTES = Feed(
    slug="warsaw_routes",
    name="Warsaw Open Data – tourist routes",
    action="get_sbt_trasy_turystyczne",
    parse=parse_routes,
    model=TouristRoute,
    key="title",
)
