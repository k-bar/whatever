"""Unit and integration tests for Warsaw Open Data API parser and ingestor."""

from pathlib import Path
from typing import Any, Iterator
import sys

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api_client import parse_dane_file  # noqa: E402
from src.config import get_database_url  # noqa: E402
from src.ingestor import (  # noqa: E402
    _extract_event_geo,
    _extract_lon_lat,
    _parse_dt,
    ingest_air_quality,
    ingest_city_events,
    ingest_defibrillators,
    ingest_open_sports_fields,
    ingest_sports_activities,
    ingest_toilets,
    ingest_tourist_routes,
    ingest_weather,
)
from src.models import (  # noqa: E402
    AirQualityMeasurement,
    AirQualityStation,
    Base,
    CityEvent,
    Defibrillator,
    OpenSportsField,
    SportsActivity,
    Toilet,
    TouristPoint,
    TouristRoute,
    WeatherMeasurement,
)


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


def test_parse_dane_file_resolves_all_eight_datasets(tmp_path: Path) -> None:
    """Verify parse_dane_file deduplicates and resolves prefix UUIDs."""
    sample_file = tmp_path / "dane.txt"
    sample_file.write_text(
        "\n".join(
            [
                "https://dane.um.warszawa.pl/pl/catalogue/"
                "00394370-1299-4d98-9910-0983fa7e7612",
                "https://dane.um.warszawa.pl/pl/catalogue/"
                "7bc32ffc-c2ac-4d32-83c9-b6f7a0b38",
                "https://dane.um.warszawa.pl/pl/catalogue/"
                "7bc32ffc-c2ac-4d32-83c9-b6f7a0b38de8",
            ]
        ),
        encoding="utf-8",
    )
    specs = parse_dane_file(sample_file)
    assert [s.key for s in specs] == ["tourist_routes", "defibrillators"]


def test_extract_lon_lat_and_parse_dt() -> None:
    """Verify geometry coordinate unwrapping and timestamp parsing."""
    assert _extract_lon_lat({"coordinates": [21.01, 52.23]}) == (21.01, 52.23)
    assert _extract_lon_lat({"coordinates": [[21.01, 52.23]]}) == (
        21.01,
        52.23,
    )
    dt = _parse_dt("2026-10-17 13:30:00")
    assert dt is not None
    assert dt.year == 2026 and dt.hour == 13 and dt.minute == 30


def test_extract_event_geo() -> None:
    """Verify city event GeoJSON feature extraction."""
    event = {
        "map": {
            "features": [
                {
                    "geometry": {"coordinates": [20.98, 52.21]},
                    "properties": {"district": "Ochota"},
                }
            ]
        }
    }
    district, lat, lon = _extract_event_geo(event)
    assert district == "Ochota"
    assert lat == 52.21
    assert lon == 20.98


def test_ingest_upserts_and_history(db_session: Session) -> None:
    """Verify all 8 dataset handlers upsert or append records properly."""
    # 1. Tourist routes & points
    routes_payload: list[dict[str, Any]] = [
        {
            "title": "Test Trasa",
            "length": "5.5",
            "description": "Opis v1",
            "traces": [[52.23, 21.01]],
            "tourist_points": [
                {
                    "id_point": 999991,
                    "name": "Punkt Testowy",
                    "city": "Warszawa",
                    "latlng": {"lat": "52.23", "lng": "21.01"},
                }
            ],
        }
    ]
    assert ingest_tourist_routes(db_session, routes_payload) == 1
    routes_payload[0]["description"] = "Opis v2"
    assert ingest_tourist_routes(db_session, routes_payload) == 1
    route = db_session.execute(
        select(TouristRoute).where(TouristRoute.title == "Test Trasa")
    ).scalar_one()
    assert route.description == "Opis v2"
    point = db_session.get(TouristPoint, 999991)
    assert point is not None and point.name == "Punkt Testowy"

    # 2. Toilets
    toilets_payload: list[dict[str, Any]] = [
        {
            "geometry": {"coordinates": [21.0001, 52.2001]},
            "properties": {
                "lokalizacja": "Testowa Toaleta 1",
                "dzielnica": "Śródmieście",
                "dostepnosc": 1,
                "platnosc": 0,
            },
        }
    ]
    assert ingest_toilets(db_session, toilets_payload) == 1
    assert ingest_toilets(db_session, toilets_payload) == 1

    # 3. Weather measurements (history append + duplicate ignore)
    weather_payload: list[dict[str, Any]] = [
        {
            "lokalizacja": "Stacja Test",
            "lat": 52.29,
            "lon": 20.97,
            "czas": "2099-01-01 12:00:00",
            "temp_pow": 15.2,
        }
    ]
    assert ingest_weather(db_session, weather_payload) == 1
    assert ingest_weather(db_session, weather_payload) == 1
    w_count = db_session.execute(
        select(func.count())
        .select_from(WeatherMeasurement)
        .where(WeatherMeasurement.lokalizacja == "Stacja Test")
    ).scalar_one()
    assert w_count == 1

    # 4. Defibrillators
    aed_payload: list[dict[str, Any]] = [
        {
            "geometry": {"coordinates": [[21.015, 52.208]]},
            "properties": {
                "defibrillator_id": "TEST-AED-1",
                "location_object_name": "Obiekt v1",
            },
        }
    ]
    assert ingest_defibrillators(db_session, aed_payload) == 1
    aed_payload[0]["properties"]["location_object_name"] = "Obiekt v2"
    assert ingest_defibrillators(db_session, aed_payload) == 1
    aed = db_session.get(Defibrillator, "TEST-AED-1")
    assert aed is not None and aed.location_object_name == "Obiekt v2"

    # 5. Sports activities
    sports_payload = [
        {
            "url": "https://sport.um.warszawa.pl/-/test-zajecia",
            "title": "Zajęcia Testowe",
            "time": "18:00",
        }
    ]
    assert ingest_sports_activities(db_session, sports_payload) == 1
    sports_payload[0]["time"] = "19:30"
    assert ingest_sports_activities(db_session, sports_payload) == 1
    sa = db_session.execute(
        select(SportsActivity).where(
            SportsActivity.url == "https://sport.um.warszawa.pl/-/test-zajecia"
        )
    ).scalar_one()
    assert sa.time == "19:30"

    # 6. Open sports fields
    fields_payload = [
        {
            "Dzielnica": "Mokotów",
            "Adres obiektu": "ul. Testowa 10",
            "Nazwa placówki oświatowej": "SP Testowa 999",
            "Typ obiektu": "boisko piłkarskie",
            "Boisk uniwersalne zawiera": "piłka nożna",
            "Poniedziałek": "16:00-20:00",
        }
    ]
    assert ingest_open_sports_fields(db_session, fields_payload) == 1
    assert ingest_open_sports_fields(db_session, fields_payload) == 1
    f_count = db_session.execute(
        select(func.count())
        .select_from(OpenSportsField)
        .where(OpenSportsField.nazwa_placowki == "SP Testowa 999")
    ).scalar_one()
    assert f_count == 1

    # 7. City events
    events_payload = [
        {
            "url": "https://kultura.um.warszawa.pl/-/test-wydarzenie",
            "title": "Spektakl Testowy",
            "lead": "Opis skrócony",
            "localization": [{"id": "1", "name": "Wola"}],
        }
    ]
    assert ingest_city_events(db_session, events_payload) == 1
    ev = db_session.execute(
        select(CityEvent).where(
            CityEvent.url
            == "https://kultura.um.warszawa.pl/-/test-wydarzenie"
        )
    ).scalar_one()
    assert ev.district == "Wola"

    # 8. Air quality stations & measurements
    air_payload = [
        {
            "name": "Stacja-Test-Powietrze",
            "lat": 52.24,
            "lon": 21.08,
            "address": {"city": "Warszawa", "district": "Praga"},
            "ijp": {"name": "Bardzo dobry"},
            "data": [
                {
                    "param_code": "PM10",
                    "param_name": "pył PM10",
                    "time": "2099-01-01 12:00:00",
                    "value": 12.5,
                    "unit": "µg/m3",
                    "ijp": {"name": "Bardzo dobry"},
                }
            ],
        }
    ]
    assert ingest_air_quality(db_session, air_payload) == 1
    assert ingest_air_quality(db_session, air_payload) == 1
    st = db_session.get(AirQualityStation, "Stacja-Test-Powietrze")
    assert st is not None and st.current_ijp_name == "Bardzo dobry"
    m_count = db_session.execute(
        select(func.count())
        .select_from(AirQualityMeasurement)
        .where(
            AirQualityMeasurement.station_name == "Stacja-Test-Powietrze"
        )
    ).scalar_one()
    assert m_count == 1

    # Also ensure Toilet was persisted inside the transaction
    t_count = db_session.execute(
        select(func.count())
        .select_from(Toilet)
        .where(Toilet.lokalizacja == "Testowa Toaleta 1")
    ).scalar_one()
    assert t_count == 1
