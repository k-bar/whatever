"""Tourist routes from Warsaw Open Data: one LineString per route plus its points of interest.

Ported from Kamil's postgre-aws ingestor (src/ingestor.py: ingest_tourist_routes). Static data,
so it rides along with the hourly ingest (app/ingest/run.py).
"""

from app.ingest.conditions import Feed, num
from app.models import TouristRoute


def parse_routes(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        title = (r.get("title") or "").strip()
        # the API lists traces as [lat, lng]; WKT wants lng lat
        coords = [
            (num(t[1]), num(t[0])) for t in r.get("traces") or [] if isinstance(t, list) and len(t) == 2
        ]
        coords = [(x, y) for x, y in coords if x is not None and y is not None]
        if not title or len(coords) < 2:
            continue
        points = []
        for p in r.get("tourist_points") or []:
            ll = p.get("latlng") or {}
            if num(ll.get("lat")) is not None and num(ll.get("lng")) is not None:
                points.append(
                    {
                        "id": p.get("id_point"),
                        "name": p.get("name"),
                        "lat": num(ll["lat"]),
                        "lng": num(ll["lng"]),
                    }
                )
        rows.append(
            dict(
                title=title,
                length_km=num(r.get("length")),
                description=r.get("description"),
                path="SRID=4326;LINESTRING(" + ", ".join(f"{x} {y}" for x, y in coords) + ")",
                points=points,
            )
        )
    return rows


ROUTES = Feed(
    slug="warsaw_routes",
    name="Warsaw Open Data – tourist routes",
    action="get_sbt_trasy_turystyczne",
    parse=parse_routes,
    model=TouristRoute,
    key="title",
)
