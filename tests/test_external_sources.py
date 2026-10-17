"""Unit and integration tests for kupbilecik.pl and OpenStreetMap sources."""

from pathlib import Path
from typing import Any, Iterator
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_database_url  # noqa: E402
from src.external_sources import (  # noqa: E402
    build_overpass_query,
    iter_kupbilecik_ld_items,
    parse_kupbilecik_item,
    parse_osm_element,
)
from src.ingestor import (  # noqa: E402
    ingest_kupbilecik_events,
    ingest_streets_gl_venues,
)
from src.models import (  # noqa: E402
    Base,
    KupbilecikEvent,
    StreetsGlVenue,
)
from src.scheduler import get_specs_for_group  # noqa: E402


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Provide a transactional PostgreSQL session that rolls back on exit."""
    engine = create_engine(get_database_url())
    Base.metadata.create_all(engine)
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


def test_kupbilecik_json_ld_parsing() -> None:
    """Verify extraction and normalization of JSON-LD event items."""
    sample_html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "itemListElement": [
        {
          "@type": "ListItem",
          "item": {
            "@type": "TheaterEvent",
            "name": "Spektakl &amp; Komedia",
            "url": "https://www.kupbilecik.pl/imprezy/123456/warszawa/test/",
            "startDate": "2026-11-15T19:30:00+01:00",
            "endDate": "2026-11-15T21:30:00+01:00",
            "eventStatus": "https://schema.org/EventScheduled",
            "location": {
              "@type": "Place",
              "name": "Teatr Capitol",
              "address": {
                "streetAddress": "Marszałkowska 115",
                "addressLocality": "Warszawa",
                "postalCode": "00-102",
                "addressRegion": "mazowieckie"
              }
            },
            "offers": {
              "@type": "Offer",
              "price": "120.50",
              "priceCurrency": "PLN",
              "availability": "https://schema.org/InStock"
            }
          }
        }
      ]
    }
    </script>
    </head></html>
    """
    items = list(iter_kupbilecik_ld_items(sample_html))
    assert len(items) == 1
    row = parse_kupbilecik_item(items[0], category="teatr")
    assert row is not None
    assert row["id"] == 123456
    assert row["name"] == "Spektakl & Komedia"
    assert row["date"] == "2026-11-15"
    assert row["time"] == "19:30"
    assert row["city"] == "Warszawa"
    assert row["category"] == "teatr"
    assert row["price"] == 120.50
    assert row["availability"] == "InStock"
    assert row["status"] == "EventScheduled"


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


def test_ingest_kupbilecik_and_streets_gl_upserts(db_session: Session) -> None:
    """Verify PostgreSQL upsert and COALESCE category preservation."""
    events = [
        {
            "id": 9998881,
            "name": "Koncert Testowy v1",
            "date": "2026-12-01",
            "time": "20:00",
            "city": "Warszawa",
            "category": "muzyka",
            "price": 99.0,
            "url": "https://www.kupbilecik.pl/imprezy/9998881/warszawa/test/",
        }
    ]
    assert ingest_kupbilecik_events(db_session, events) == 1

    # Re-ingest with updated name and category=None (as from 'search' listing)
    events_update = [
        {
            "id": 9998881,
            "name": "Koncert Testowy v2",
            "date": "2026-12-01",
            "time": "20:00",
            "city": "Warszawa",
            "category": None,
            "price": 110.0,
            "url": "https://www.kupbilecik.pl/imprezy/9998881/warszawa/test/",
        }
    ]
    assert ingest_kupbilecik_events(db_session, events_update) == 1
    ev = db_session.get(KupbilecikEvent, 9998881)
    assert ev is not None
    assert ev.name == "Koncert Testowy v2"
    assert ev.price == 110.0
    assert ev.category == "muzyka"

    venues = [
        {
            "id": "node/9998881",
            "name": "Kino Testowe v1",
            "category": "cinema",
            "city": "Warszawa",
            "lat": 52.23,
            "lon": 21.01,
            "tags": {"name": "Kino Testowe v1", "amenity": "cinema"},
        }
    ]
    assert ingest_streets_gl_venues(db_session, venues) == 1
    venues[0]["name"] = "Kino Testowe v2"
    assert ingest_streets_gl_venues(db_session, venues) == 1
    venue = db_session.get(StreetsGlVenue, "node/9998881")
    assert venue is not None
    assert venue.name == "Kino Testowe v2"

    ext_keys = [s.key for s in get_specs_for_group("external")]
    assert set(ext_keys) == {"kupbilecik", "streets_gl"}
