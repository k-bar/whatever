"""Load fetcher output into Postgres.

python -m app.ingest.run                      # all sources
python -m app.ingest.run --source warsaw_events
python -m app.ingest.run --geocode-limit 0    # skip Nominatim lookups
"""

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import Point, shape
from sqlalchemy import delete, exists, select, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.categories import map_categories
from app.db import SessionLocal
from app.ingest.base import RawEvent, SourceSpec
from app.ingest.geocode import Geocoder
from app.ingest.sources import SOURCES
from app.models import Attendance, Event, JoinRequest, Occurrence, Source

BOUNDARY = shape(
    json.loads((Path(__file__).parent.parent / "data" / "warsaw_boundary.geojson").read_text())["geometry"]
)


def in_warsaw(lat: float, lng: float) -> bool:
    return BOUNDARY.contains(Point(lng, lat))


def get_or_create_source(db: Session, spec: SourceSpec) -> Source:
    src = db.scalar(select(Source).where(Source.slug == spec.slug))
    if src is None:
        src = Source(slug=spec.slug, name=spec.name, url=spec.url, is_reliable=spec.is_reliable)
        db.add(src)
        db.flush()
    return src


def upsert_event(db: Session, source: Source, raw: RawEvent, geocoder: Geocoder | None) -> int | None:
    """Insert or update one event and its occurrences. Returns event id, or None if dropped."""
    lat, lng = raw.lat, raw.lng
    if (lat is None or lng is None) and geocoder:
        query = Geocoder.query_for(raw.address, raw.venue_name)
        point = geocoder.lookup(query) if query else None
        if point:
            lat, lng = point
    if lat is not None and lng is not None and not in_warsaw(lat, lng):
        return None

    values = dict(
        source_id=source.id,
        external_key=raw.external_key,
        kind=raw.kind,
        title=raw.title,
        categories=map_categories(raw.categories_raw, raw.title),
        categories_raw=raw.categories_raw,
        lead=raw.lead,
        text_plain=raw.text_plain,
        text_html=raw.text_html,
        image_url=raw.image_url,
        url=raw.url,
        language=raw.language,
        district=raw.district,
        venue_name=raw.venue_name,
        address=raw.address,
        lat=lat,
        lng=lng,
        location=f"SRID=4326;POINT({lng} {lat})" if lat is not None else None,
        opening_hours=raw.opening_hours,
        contact=raw.contact,
        audience=raw.audience,
        capacity=raw.capacity,
        seats_left=raw.seats_left,
        raw=raw.raw,
        is_active=True,
    )
    stmt = insert(Event).values(**values)
    update_cols = {k: stmt.excluded[k] for k in values if k not in ("source_id", "external_key")}
    update_cols["updated_at"] = datetime.now(UTC)
    if lat is None:
        # keep coordinates from an earlier geocode if this run had no budget left
        for col in ("lat", "lng", "location"):
            update_cols.pop(col)
    event_id = db.scalar(
        stmt.on_conflict_do_update(index_elements=["source_id", "external_key"], set_=update_cols).returning(
            Event.id
        )
    )

    starts = set()
    for occ in raw.occurrences:
        starts.add(occ.starts_at)
        o = insert(Occurrence).values(
            event_id=event_id, starts_at=occ.starts_at, ends_at=occ.ends_at, daily=occ.daily
        )
        db.execute(
            o.on_conflict_do_update(
                index_elements=["event_id", "starts_at"],
                set_={"ends_at": o.excluded.ends_at, "daily": o.excluded.daily},
            )
        )
    # drop occurrences the source no longer lists, unless people already attend them
    db.execute(
        delete(Occurrence).where(
            Occurrence.event_id == event_id,
            Occurrence.starts_at.not_in(starts) if starts else true(),
            ~exists().where(Attendance.occurrence_id == Occurrence.id),
            ~exists().where(JoinRequest.occurrence_id == Occurrence.id),
        )
    )
    return event_id


def load(db: Session, spec: SourceSpec, raws: list[RawEvent], geocoder: Geocoder | None) -> int:
    source = get_or_create_source(db, spec)
    seen = []
    for raw in raws:
        event_id = upsert_event(db, source, raw, geocoder)
        if event_id is not None:
            seen.append(event_id)
    db.execute(
        update(Event)
        .where(Event.source_id == source.id, Event.id.not_in(seen or [0]))
        .values(is_active=False)
    )
    source.last_run_at = datetime.now(UTC)
    source.last_status = "ok"
    source.last_error = None
    source.item_count = len(seen)
    return len(seen)


def record_error(db: Session, spec: SourceSpec, err: str) -> None:
    source = get_or_create_source(db, spec)
    source.last_run_at = datetime.now(UTC)
    source.last_status = "error"
    source.last_error = err[-2000:]
    db.commit()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sorted(SOURCES), help="run only this source")
    ap.add_argument("--geocode-limit", type=int, default=200, help="max Nominatim calls per source")
    args = ap.parse_args(argv)

    failed = 0
    for slug in [args.source] if args.source else sorted(SOURCES):
        spec = SOURCES[slug]
        with SessionLocal() as db:
            try:
                raws = spec.fetch()
                geocoder = Geocoder(db, args.geocode_limit) if args.geocode_limit else None
                n = load(db, spec, raws, geocoder)
                db.commit()
                print(
                    f"{slug}: {len(raws)} fetched, {n} stored, {geocoder.calls if geocoder else 0} geocoded"
                )
            except Exception:
                db.rollback()
                failed += 1
                err = traceback.format_exc()
                print(f"{slug}: FAILED\n{err}", file=sys.stderr)
                record_error(db, spec, err)
    if not args.source:
        from app.ingest.conditions import run_feeds  # imports this module
        from app.ingest.routes import ROUTES

        failed += run_feeds([ROUTES])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
