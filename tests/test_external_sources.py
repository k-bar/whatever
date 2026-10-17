"""Unit and integration tests for OpenStreetMap (streets.gl) source."""

from pathlib import Path
from typing import Any, Iterator
import sys

import pytest
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import create_db_engine  # noqa: E402
from src.external_sources import (  # noqa: E402
    build_overpass_query,
    parse_osm_element,
)
from src.ingestor import (  # noqa: E402
    DatabaseIngestor,
    ingest_streets_gl_venues,
)
from src.models import StreetsGlVenue  # noqa: E402
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
    assert set(ext_keys) == {"streets_gl"}
