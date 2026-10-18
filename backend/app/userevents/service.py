"""User events as a library: who may see one, and putting a public one onto the Syrenka Users API.
Used by the userevents router, profiles, chats and the demo data (app/mocksocial.py)."""

from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.friends import are_friends
from app.models import Attendance, Event, Occurrence, Source, User
from app.userevents import PUBLIC_AUDIENCES, SOURCE_NAME, SOURCE_SLUG
from app.userevents.models import UserEvent


def photo_url(photo_id: str | None) -> str | None:
    return f"/userevents/photos/{photo_id}" if photo_id else None


def extra_props(ue: UserEvent) -> dict:
    """What a user-event pin carries on top of a normal /events feature (also stored in Event.raw)."""
    return {
        "user_event_id": ue.id,
        "subtitle": ue.subtitle,
        "audience": ue.audience,
        "event_type": ue.event_type,
        "host": {"id": ue.host.id, "display_name": ue.host.display_name},
    }


def syrenka_source(db: Session) -> Source:
    source = db.scalar(select(Source).where(Source.slug == SOURCE_SLUG))
    if source is None:
        source = Source(slug=SOURCE_SLUG, name=SOURCE_NAME, url=None, is_reliable=False, item_count=0)
        db.add(source)
        db.flush()
    return source


def publish(db: Session, ue: UserEvent) -> Event:
    """Put a public user event onto the Syrenka Users API (= the events table, source syrenka-users)."""
    source = syrenka_source(db)
    event = Event(
        source=source,
        external_key=f"user-event-{ue.id}",
        kind="event",
        title=ue.title,
        categories=[ue.category],
        categories_raw=[ue.event_type],
        lead=(ue.description or "")[:300] or None,
        text_plain=ue.description,
        image_url=photo_url(ue.photo_id),
        venue_name=ue.venue_name,
        address=ue.address,
        lat=ue.lat,
        lng=ue.lng,
        location=f"SRID=4326;POINT({ue.lng} {ue.lat})",
        audience=[],
        contact={},
        raw=extra_props(ue),
        host_user_id=ue.host_user_id,
        is_public_invite=True,
        occurrences=[Occurrence(starts_at=ue.starts_at, ends_at=ue.ends_at)],
    )
    db.add(event)
    db.flush()
    db.add(Attendance(user_id=ue.host_user_id, occurrence_id=event.occurrences[0].id, wants_company=True))
    source.item_count = (source.item_count or 0) + 1
    source.last_run_at = datetime.now(UTC)
    source.last_status = "ok"
    ue.event_id = event.id
    return event


def can_see(db: Session, user: User | None, ue: UserEvent, friends: Collection[int] | None = None) -> bool:
    """Who may see (and chat about) a user event: anyone for public ones; otherwise the host,
    invited people, and for audience "friends" the host's friends. Checking many events for one
    user? Pass their friend_ids() as `friends` instead of a query per event."""
    if ue.audience in PUBLIC_AUDIENCES:
        return True
    if user is None:
        return False
    if user.id == ue.host_user_id or user.id in (ue.invited_user_ids or []):
        return True
    if ue.audience != "friends":
        return False
    return ue.host_user_id in friends if friends is not None else are_friends(db, user.id, ue.host_user_id)
