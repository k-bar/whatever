from sqlalchemy import func, select

from app.ingest.base import Occurrence as RawOccurrence
from app.ingest.base import RawEvent
from app.ingest.run import load
from app.ingest.sources import SOURCES
from app.models import Attendance, Event, Occurrence, Source, User
from tests.conftest import fixture_records


def load_fixture(db, slug):
    spec = SOURCES[slug]
    n = load(db, spec, spec.parse(fixture_records(slug)), geocoder=None)
    db.commit()
    return n


def test_rerun_keeps_ids_stable(db):
    for slug in SOURCES:
        load_fixture(db, slug)
    first = dict(db.execute(select(Event.external_key, Event.id)).all())
    occ_count = db.scalar(select(func.count()).select_from(Occurrence))

    for slug in SOURCES:
        load_fixture(db, slug)
    assert dict(db.execute(select(Event.external_key, Event.id)).all()) == first
    assert db.scalar(select(func.count()).select_from(Occurrence)) == occ_count

    src = db.scalar(select(Source).where(Source.slug == "warsaw_events"))
    assert src.last_status == "ok" and src.item_count == len(fixture_records("warsaw_events"))


def raw(key, lat=52.23, lng=21.01, starts=("2030-01-01T18:00:00+01:00",)):
    return RawEvent(
        source_slug="warsaw_events",
        external_key=key,
        title=f"Koncert {key}",
        lat=lat,
        lng=lng,
        occurrences=[RawOccurrence(starts_at=s) for s in starts],
    )


def test_outside_warsaw_dropped_and_missing_marked_inactive(db):
    spec = SOURCES["warsaw_events"]
    load(db, spec, [raw("a"), raw("krakow", lat=50.06, lng=19.94)], None)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Event)) == 1
    ev = db.scalar(select(Event))
    assert ev.categories == ["music"]

    load(db, spec, [raw("b")], None)
    db.commit()
    assert db.scalar(select(Event.is_active).where(Event.external_key == "a")) is False


def test_occurrence_with_attendees_survives_removal(db):
    spec = SOURCES["warsaw_events"]
    load(db, spec, [raw("a", starts=("2030-01-01T18:00:00+01:00", "2030-01-02T18:00:00+01:00"))], None)
    user = User(email="x@example.com", password_hash="x", display_name="X", photos=[], interests=[], links={})
    db.add(user)
    db.flush()
    attended = db.scalars(select(Occurrence).order_by(Occurrence.starts_at)).first()
    db.add(Attendance(user_id=user.id, occurrence_id=attended.id))
    db.commit()

    load(db, spec, [raw("a", starts=("2030-01-03T18:00:00+01:00",))], None)
    db.commit()
    ids = set(db.scalars(select(Occurrence.id)))
    assert attended.id in ids  # kept: someone is going
    assert len(ids) == 2  # 01-02 dropped, 01-03 added



def test_past_occurrences_are_kept_when_the_source_stops_listing_them(db):
    spec = SOURCES["warsaw_events"]
    load(db, spec, [raw("a", starts=("2020-05-01T18:00:00+02:00", "2030-01-02T18:00:00+01:00"))], None)
    db.commit()

    # next run: the source no longer lists either date (the past one is over, the future one cancelled)
    load(db, spec, [raw("a", starts=("2030-01-03T18:00:00+01:00",))], None)
    db.commit()
    years = sorted(o.starts_at.year for o in db.scalars(select(Occurrence)))
    assert years == [2020, 2030]  # 2020 kept as history; cancelled 2030-01-02 dropped; 2030-01-03 added

def test_api_request_direct_and_via_relay(monkeypatch):
    from app.config import settings
    from app.ingest.sources import warsaw_open_data as w

    monkeypatch.setattr(settings, "warsaw_api_token", "city-key")
    monkeypatch.setattr(settings, "warsaw_relay_url", None)
    req = w.api_request("get_be_otwarte_boiska")
    assert req.full_url == w.API + "get_be_otwarte_boiska"
    assert req.get_header("Authorization") == "city-key"

    monkeypatch.setattr(settings, "warsaw_relay_url", "https://relay.example/")
    monkeypatch.setattr(settings, "warsaw_relay_token", "relay-key")
    req = w.api_request("get_be_otwarte_boiska")
    assert req.full_url == "https://relay.example/" and req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer relay-key"
    assert req.get_header("X-relay-target") == w.API + "get_be_otwarte_boiska"
    assert req.get_header("X-relay-authorization") == "city-key"


def test_token_secret_accepts_json(monkeypatch):
    import app.config as config

    monkeypatch.setattr(
        config, "read_secret", lambda arn: '{"token": "k", "relay_url": "https://r/", "relay_token": "t"}'
    )
    s = config.Settings(warsaw_api_token_secret_arn="arn")
    assert (s.warsaw_api_token, s.warsaw_relay_url, s.warsaw_relay_token) == ("k", "https://r/", "t")
    monkeypatch.setattr(config, "read_secret", lambda arn: "plain\n")
    assert config.Settings(warsaw_api_token_secret_arn="arn").warsaw_api_token == "plain"


def test_amenities_parse_coordinates_hours_and_categories():
    from app.categories import map_categories

    toilets = SOURCES["warsaw_toilets"].parse(fixture_records("warsaw_toilets"))
    assert len(toilets) == len(fixture_records("warsaw_toilets"))
    assert all(t.kind == "place" and 52 < t.lat < 53 and 20 < t.lng < 22 for t in toilets)
    assert toilets[0].opening_hours["monday"] == "00:00-24:00"  # "Całodobowo"
    closed_sunday = [t for t in toilets if t.opening_hours and "sunday" not in t.opening_hours]
    assert closed_sunday and all(":" in h for t in closed_sunday for h in t.opening_hours.values())

    aeds = SOURCES["warsaw_aed"].parse(fixture_records("warsaw_aed"))
    assert aeds and all(a.external_key.isdigit() and 52 < a.lat < 53 for a in aeds)
    assert map_categories(["defibrylator"], "Defibrylator AED – Muzeum Narodowe") == ["aed"]


def test_conditions_and_routes_parse():
    from app.ingest.conditions import parse_air, parse_weather
    from app.ingest.routes import parse_routes
    from app.ingest.sources.warsaw_open_data import as_records

    weather = parse_weather(fixture_records("warsaw_weather"))
    assert weather and weather[0]["measured_at"].tzinfo is not None and weather[0]["temp_air"] is not None

    air = parse_air(fixture_records("warsaw_air"))
    assert air and "PM10" in air[0]["params"] and air[0]["index_name"]

    routes = parse_routes(as_records(fixture_records("warsaw_routes")))
    assert routes and routes[0]["path"].startswith("SRID=4326;LINESTRING(20.")  # lng first
    assert routes[0]["points"] and {"id", "name", "lat", "lng"} <= routes[0]["points"][0].keys()


def test_osm_venues_parse():
    from datetime import datetime

    from app.categories import map_categories
    from app.ingest.sources.osm_venues import osm_hours
    from app.routers.events import is_open

    records = fixture_records("osm_venues")
    venues = SOURCES["osm_venues"].parse(records)
    assert len(venues) == len([r for r in records if (r.get("tags") or {}).get("name")])  # unnamed dropped
    assert all(v.kind == "place" and v.external_key.startswith(("node/", "way/")) for v in venues)
    assert all(52 < v.lat < 53 and 20 < v.lng < 22 for v in venues)  # ways use their center
    assert map_categories(["osm:nightclub"], "Gatsby Warsaw") == ["nightlife"]

    assert osm_hours("24/7")["sunday"] == "00:00-24:00"
    assert osm_hours("Su-Fr 09:00-16:00") == {
        d: "09:00-16:00" for d in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday"]
    }
    assert osm_hours("We-Su 12:00-17:00; Nov 11: 11:00-16:00")["wednesday"] == "12:00-17:00"
    assert osm_hours("Fr-Sa 19:00+") is None
    late = osm_hours("We-Th 19:00-01:00; Fr-Sa 19:00-04:00")["friday"]
    assert is_open(late, datetime(2026, 10, 17, 2, 30)) and not is_open(late, datetime(2026, 10, 17, 12))


def test_slow_sources_are_skipped_within_their_window(db):
    from app.ingest.run import load, recently_ok

    spec = SOURCES["osm_venues"]
    assert not recently_ok(db, spec)
    load(db, spec, spec.parse(fixture_records("osm_venues")), None)
    db.commit()
    assert recently_ok(db, spec) and not recently_ok(db, SOURCES["warsaw_events"])
