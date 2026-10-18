"""Unit and integration tests for OSM, Songkick and Waw4Free sources."""

import json
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock
import sys

import pytest
import requests
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import create_db_engine  # noqa: E402
from src.external_sources import (  # noqa: E402
    build_overpass_query,
    build_restaurants_overpass_query,
    fetch_waw4free_events,
    parse_osm_element,
    parse_restaurant_element,
    parse_songkick_html,
    parse_waw4free_html,
)
from src.ingestor import (  # noqa: E402
    DatabaseIngestor,
    ingest_entertainment_events,
    ingest_restaurants,
    ingest_streets_gl_venues,
)
from src.models import (  # noqa: E402
    EntertainmentEvent,
    Restaurant,
    StreetsGlVenue,
)
from src.scheduler import get_specs_for_group  # noqa: E402


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Provide a transactional PostgreSQL session that rolls back on exit."""
    engine = create_db_engine()
    DatabaseIngestor(engine=engine).init_schema()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_streets_gl_osm_parsing() -> None:
    """Verify Overpass query builder and OSM element transformation."""
    query = build_overpass_query("Warszawa")
    assert 'area["name"="Warszawa"]' in query
    assert "theatre" in query

    element: dict[str, Any] = {
        "type": "way",
        "id": 987654,
        "center": {"lat": 52.24351, "lon": 21.00123},
        "tags": {
            "name": "Teatr Wielki",
            "amenity": "theatre",
            "addr:street": "Plac Teatralny",
            "addr:housenumber": "1",
            "addr:postcode": "00-950",
            "addr:city": "Warszawa",
            "opening_hours": "Mo-Su 10:00-19:00",
            "wheelchair": "yes",
        },
    }
    row = parse_osm_element(element)
    assert row is not None
    assert row["id"] == "way/987654"
    assert row["name"] == "Teatr Wielki"
    assert row["category"] == "theatre"
    assert row["location"] == "Plac Teatralny 1, 00-950 Warszawa"
    assert row["lat"] == 52.24351
    assert row["lon"] == 21.00123
    assert row["streets_gl_url"] == (
        "https://streets.gl/#52.24351,21.00123,45.00,0.00,500.00"
    )


def test_ingest_streets_gl_upserts(db_session: Session) -> None:
    """Verify PostgreSQL upsert for streets_gl_venues."""
    venues = [
        {
            "id": "node/9998881",
            "name": "Kino Testowe v1",
            "category": "cinema",
            "city": "Warszawa",
            "lat": 52.23,
            "lon": 21.01,
            "tags": {"amenity": "cinema", "name": "Kino Testowe v1"},
        }
    ]
    assert ingest_streets_gl_venues(db_session, venues) == 1
    venue = db_session.get(StreetsGlVenue, "node/9998881")
    assert venue is not None
    assert venue.name == "Kino Testowe v1"
    assert venue.category == "cinema"

    ext_keys = [s.key for s in get_specs_for_group("external")]
    assert {"streets_gl", "restaurants", "entertainment_events"} <= set(
        ext_keys
    )


def test_restaurant_osm_parsing() -> None:
    """Verify Overpass restaurants query and element transformation."""
    query = build_restaurants_overpass_query("Warszawa")
    assert "restaurant|cafe|bar|pub|biergarten|food_court" in query

    element: dict[str, Any] = {
        "type": "node",
        "id": 123,
        "lat": 52.2297,
        "lon": 21.0122,
        "tags": {
            "name": "Bistro Testowe",
            "amenity": "restaurant",
            "cuisine": "polish",
            "addr:street": "Marszałkowska",
            "addr:housenumber": "10",
            "outdoor_seating": "yes",
            "diet:vegan": "limited",
        },
    }
    row = parse_restaurant_element(element)
    assert row is not None
    assert row["id"] == "node/123"
    assert row["amenity"] == "restaurant"
    assert row["cuisine"] == "polish"
    assert row["location"] == "Marszałkowska 10, Warszawa"
    assert row["diet_vegan"] == "limited"
    assert parse_restaurant_element({"type": "node", "id": 1}) is None
    unnamed = {"type": "node", "id": 2, "lat": 52.2, "lon": 21.0,
               "tags": {"amenity": "cafe"}}
    assert parse_restaurant_element(unnamed) is None


def test_songkick_parsing_filters_warsaw() -> None:
    """Verify Songkick JSON-LD parsing keeps only Warsaw events."""
    warsaw = {
        "@type": "MusicEvent",
        "name": "Band @ Klub Proxima",
        "url": "https://www.songkick.com/concerts/4242-band?utm_source=x",
        "startDate": "2099-10-17T20:00:00",
        "location": {
            "name": "Klub Proxima",
            "address": {"streetAddress": "Żwirki i Wigury 99a",
                        "addressLocality": "Warsaw"},
            "geo": {"latitude": 52.21264, "longitude": 20.98722},
        },
        "performer": [{"@type": "MusicGroup", "name": "Band"}],
    }
    stockholm = {
        **warsaw,
        "url": "https://www.songkick.com/concerts/1-x",
        "location": {"address": {"addressLocality": "Stockholm"},
                     "geo": {"latitude": 59.33, "longitude": 18.05}},
    }
    html = "".join(
        f'<script type="application/ld+json">{json.dumps(x)}</script>'
        for x in ([warsaw, stockholm],)
    )
    rows = parse_songkick_html(html)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "songkick:4242"
    assert row["url"] == "https://www.songkick.com/concerts/4242-band"
    assert row["performers"] == ["Band"]
    assert row["venue_name"] == "Klub Proxima"


def test_waw4free_parsing() -> None:
    """Verify Waw4Free card parsing (dates, district, categories)."""
    html = (
        '<div class="box"><div class="box-image" '
        "style=\"background-image: url('/upload/x.webp');\"></div>"
        '<div class="box-text"><div class="box-title">'
        '<a href="wydarzenie-777-koncert-testowy">Koncert &amp; Test</a>'
        '</div><div class="box-category"><div class="b-c-koncerty">'
        '<a href="warszawa-darmowe-koncerty">koncert</a></div></div>'
        '<div class="box-data"><a href="warszawa-wydarzenia-2099-10-23">'
        '23.10.2099</a>, 18:00, <a href="warszawa-za-darmo-wola">Wola</a>'
        "</div></div></div>"
    )
    rows = parse_waw4free_html(html, default_category="koncerty")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "waw4free:777"
    assert row["title"] == "Koncert & Test"
    assert row["start_date"] == "2099-10-23T18:00:00"
    assert row["district"] == "Wola"
    assert row["lat"] is not None
    assert row["url"] == "https://waw4free.pl/wydarzenie-777-koncert-testowy"
    assert row["image_url"] == "https://waw4free.pl/upload/x.webp"


def test_waw4free_fetch_continues_after_http_error() -> None:
    """A failed listing page must not abort the remaining categories."""
    ok_html = (
        '<div class="box"><div class="box-title">'
        '<a href="wydarzenie-1-a">A</a></div>'
        '<div class="box-data"><a href="warszawa-wydarzenia-2099-01-01">'
        "x</a></div></div>"
    )
    calls: list[str] = []

    def fake_get(url: str, **_: Any) -> Any:
        calls.append(url)
        resp = MagicMock()
        if len(calls) == 1:
            resp.raise_for_status.side_effect = requests.HTTPError("boom")
        else:
            resp.raise_for_status.return_value = None
            resp.text = ok_html
        return resp

    session: Any = MagicMock()
    session.get.side_effect = fake_get
    rows = fetch_waw4free_events(session=session)
    assert len(calls) > 1
    assert [r["id"] for r in rows] == ["waw4free:1"]


def test_ingest_restaurants_and_events_upserts(db_session: Session) -> None:
    """Verify PostgreSQL upsert for restaurants and entertainment_events."""
    restaurants = [
        {"id": "node/99988877", "name": "Kawiarnia v1", "amenity": "cafe",
         "lat": 52.23, "lon": 21.01, "tags": {"amenity": "cafe"}},
    ]
    assert ingest_restaurants(db_session, restaurants) == 1
    restaurants[0]["name"] = "Kawiarnia v2"
    assert ingest_restaurants(db_session, restaurants) == 1
    rest = db_session.get(Restaurant, "node/99988877")
    assert rest is not None and rest.name == "Kawiarnia v2"

    events = [
        {"id": "songkick:99999991", "source": "songkick",
         "title": "Koncert v1", "url": "https://example.test/sk/99999991",
         "start_date": "2099-10-17T20:00:00", "performers": ["X"],
         "raw_data": {"a": 1}},
    ]
    assert ingest_entertainment_events(db_session, events) == 1
    events[0]["title"] = "Koncert v2"
    assert ingest_entertainment_events(db_session, events) == 1
    ev = db_session.get(EntertainmentEvent, "songkick:99999991")
    assert ev is not None and ev.title == "Koncert v2"
    assert ev.performers == ["X"]
