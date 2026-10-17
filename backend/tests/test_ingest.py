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
