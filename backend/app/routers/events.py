import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, defer, selectinload

from app import translate, userevents
from app.categories import AMENITIES, CATEGORIES
from app.db import get_db
from app.models import Attendance, Event, Occurrence, Source, User
from app.schemas import (
    Category,
    EventOut,
    FeatureCollection,
    GeoJSONFeature,
    OccurrenceOut,
    PublicUser,
    SourceOut,
)
from app.timeutil import WARSAW

router = APIRouter(tags=["events"])
MAX_FEATURES = 2000


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        west, south, east, north = map(float, bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be 'west,south,east,north' (lng,lat,lng,lat)")
    return west, south, east, north


def attendance_counts():
    return (
        select(
            Attendance.occurrence_id,
            func.count().label("attendees"),
            func.count().filter(Attendance.wants_company).label("wanting_company"),
        )
        .group_by(Attendance.occurrence_id)
        .subquery()
    )


LANG = Query(None, pattern="^(pl|en)$", description="title and lead in this language when translated")

# map lists never send the full text or the source's raw record: don't load them for thousands of rows
# (raw is still read, lazily, for the few Syrenka-users pins that carry their extras in it)
LIGHT = (selectinload(Event.source), defer(Event.raw), defer(Event.text_html), defer(Event.text_plain))


def localize(props: dict, event: Event, lang: str | None) -> None:
    """?lang=pl|en: title and description in that language (offline model, app/translate.py); original alongside."""
    i18n = event.i18n or {}
    if not lang or lang not in i18n or i18n.get("for") != translate.source_text(event):
        return  # not translated yet, or the text changed since: serve the original
    props["original"] = {"lang": i18n["orig"], "title": event.title, "lead": event.lead}
    props["translated"] = i18n["orig"] != lang
    props["title"] = i18n[lang]["title"]
    if event.lead:
        props["lead"] = i18n[lang]["lead"]


def feature(
    event: Event,
    occ: Occurrence | None,
    attendees: int = 0,
    wanting: int = 0,
    distance_m: float | None = None,
    lang: str | None = None,
) -> GeoJSONFeature:
    props = {
        "event_id": event.id,
        "kind": event.kind,
        "title": event.title,
        "categories": event.categories,
        "lead": event.lead,
        "image_url": event.image_url,
        "url": event.url,
        "district": event.district,
        "venue_name": event.venue_name,
        "address": event.address,
        "source": event.source.slug,
        "is_public_invite": event.is_public_invite,
        "seats_left": event.seats_left,
    }
    if occ is not None:
        props |= {
            "occurrence_id": occ.id,
            "starts_at": occ.starts_at.isoformat(),
            "ends_at": occ.ends_at.isoformat() if occ.ends_at else None,
            "daily": occ.daily,
            "attendees": attendees,
            "wanting_company": wanting,
        }
    if event.opening_hours is not None:
        props["opening_hours"] = event.opening_hours
    if event.source.slug == userevents.SOURCE_SLUG and event.raw:
        props |= event.raw  # subtitle, audience, event_type, host (see app/userevents)
    if distance_m is not None:
        props["distance_m"] = round(distance_m)
    localize(props, event, lang)
    geometry = {"type": "Point", "coordinates": [event.lng, event.lat]} if event.lat is not None else None
    return GeoJSONFeature(id=occ.id if occ is not None else event.id, geometry=geometry, properties=props)


def event_filters(stmt, bbox, category, kind, q, include_unlocated):
    stmt = stmt.where(Event.is_active)
    if bbox:
        stmt = stmt.where(func.ST_Intersects(Event.location, func.ST_MakeEnvelope(*bbox, 4326)))
    elif not include_unlocated:
        stmt = stmt.where(Event.location.is_not(None))
    if category:
        stmt = stmt.where(Event.categories.overlap(category))
    if kind:
        stmt = stmt.where(Event.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Event.title.ilike(like), Event.venue_name.ilike(like), Event.lead.ilike(like)))
    return stmt


@router.get("/events", response_model=FeatureCollection)
def list_events(
    bbox: str | None = Query(None, description="west,south,east,north, e.g. 20.85,52.10,21.27,52.37"),
    from_: datetime | None = Query(None, alias="from", description="default: now"),
    to: datetime | None = Query(None, description="default: from + 30 days"),
    category: list[str] | None = Query(None, description="repeatable: ?category=music&category=film"),
    kind: str | None = Query(None, pattern="^(event|class)$"),
    q: str | None = Query(None, max_length=100),
    include_unlocated: bool = Query(False, description="also return events with geometry=null"),
    limit: int = Query(500, ge=1, le=MAX_FEATURES),
    lang: str | None = LANG,
    db: Session = Depends(get_db),
):
    """Map data: one GeoJSON feature per occurrence that overlaps [from, to]."""
    start = from_ or datetime.now(UTC)
    end = to or start + timedelta(days=30)
    counts = attendance_counts()
    stmt = (
        select(
            Event,
            Occurrence,
            func.coalesce(counts.c.attendees, 0),
            func.coalesce(counts.c.wanting_company, 0),
        )
        .join(Occurrence, Occurrence.event_id == Event.id)
        .outerjoin(counts, counts.c.occurrence_id == Occurrence.id)
        .where(Occurrence.starts_at <= end, func.coalesce(Occurrence.ends_at, Occurrence.starts_at) >= start)
        .options(*LIGHT)
        .order_by(Occurrence.starts_at)
        .limit(limit)
    )
    stmt = event_filters(stmt, parse_bbox(bbox), category, kind, q, include_unlocated)
    rows = db.execute(stmt).all()
    return FeatureCollection(features=[feature(e, o, a, w, lang=lang) for e, o, a, w in rows])


@router.get("/events/now", response_model=FeatureCollection)
def events_now(
    lat: float = Query(..., ge=52.0, le=52.5),
    lng: float = Query(..., ge=20.7, le=21.4),
    radius_m: int = Query(3000, ge=100, le=30000),
    hours: int = Query(3, ge=1, le=12),
    lang: str | None = LANG,
    db: Session = Depends(get_db),
):
    """'Right now': occurrences starting within the next few hours, nearest first."""
    now = datetime.now(UTC)
    here = func.ST_GeogFromText(f"SRID=4326;POINT({lng} {lat})")
    distance = func.ST_Distance(Event.location, here)
    counts = attendance_counts()
    stmt = (
        select(
            Event,
            Occurrence,
            func.coalesce(counts.c.attendees, 0),
            func.coalesce(counts.c.wanting_company, 0),
            distance,
        )
        .join(Occurrence, Occurrence.event_id == Event.id)
        .outerjoin(counts, counts.c.occurrence_id == Occurrence.id)
        .where(
            Event.is_active,
            Occurrence.starts_at.between(now, now + timedelta(hours=hours)),
            func.ST_DWithin(Event.location, here, radius_m),
        )
        .options(*LIGHT)
        .order_by(distance)
        .limit(200)
    )
    rows = db.execute(stmt).all()
    return FeatureCollection(features=[feature(e, o, a, w, d, lang=lang) for e, o, a, w, d in rows])


def is_open(hours: str | None, at: datetime) -> bool:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", hours or "")
    if not m:
        return False
    h1, m1, h2, m2 = map(int, m.groups())
    minutes, start, end = at.hour * 60 + at.minute, h1 * 60 + m1, h2 * 60 + m2
    if end <= start:  # past midnight, e.g. a club open 19:00-04:00
        return minutes >= start or minutes < end
    return start <= minutes < end


@router.get("/places", response_model=FeatureCollection)
def list_places(
    bbox: str | None = None,
    district: str | None = None,
    category: list[str] | None = Query(
        None, description="repeatable; amenities only when asked: toilets, aed, transit"
    ),
    q: str | None = Query(None, max_length=100),
    open_now: bool = False,
    include_unlocated: bool = True,
    lang: str | None = LANG,
    db: Session = Depends(get_db),
):
    """Places with opening hours instead of dates (open school pitches, toilets, defibrillators)."""
    stmt = event_filters(select(Event), parse_bbox(bbox), category, "place", q, include_unlocated)
    if not category:
        stmt = stmt.where(~Event.categories.overlap(sorted(AMENITIES)))
    stmt = stmt.options(*LIGHT).order_by(Event.district, Event.title)
    if district:
        stmt = stmt.where(Event.district.ilike(district))
    places = db.scalars(stmt).all()
    if open_now:
        now = datetime.now(WARSAW)
        day = now.strftime("%A").lower()
        places = [p for p in places if is_open((p.opening_hours or {}).get(day), now)]
    return FeatureCollection(features=[feature(p, None, lang=lang) for p in places])


def event_out(db: Session, event: Event, upcoming_only: bool = True) -> EventOut:
    occs = [
        o for o in event.occurrences if not upcoming_only or (o.ends_at or o.starts_at) >= datetime.now(UTC)
    ]
    counts = dict.fromkeys([o.id for o in occs], (0, 0))
    if occs:
        rows = db.execute(
            select(Attendance.occurrence_id, func.count(), func.count().filter(Attendance.wants_company))
            .where(Attendance.occurrence_id.in_(counts))
            .group_by(Attendance.occurrence_id)
        ).all()
        counts |= {oid: (a, w) for oid, a, w in rows}
    host = db.get(User, event.host_user_id) if event.host_user_id else None
    data = {f: getattr(event, f) for f in EventOut.model_fields if f not in ("source", "host", "occurrences")}
    return EventOut(
        **data,
        source=event.source.slug,
        host=PublicUser.model_validate(host) if host else None,
        occurrences=[
            OccurrenceOut(
                id=o.id,
                starts_at=o.starts_at,
                ends_at=o.ends_at,
                daily=o.daily,
                attendees=counts[o.id][0],
                wanting_company=counts[o.id][1],
            )
            for o in occs
        ],
    )


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, past: bool = False, db: Session = Depends(get_db)):
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.source), selectinload(Event.occurrences))
    )
    if event is None:
        raise HTTPException(404, "Event not found")
    return event_out(db, event, upcoming_only=not past)


@router.get("/categories", response_model=list[Category])
def list_categories():
    return [Category(slug=s, label=label) for s, label in CATEGORIES.items()]


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    """'APIs I'm plugged in to': every source, its event count and last run."""
    return db.scalars(select(Source).order_by(Source.is_reliable.desc(), Source.item_count.desc())).all()
