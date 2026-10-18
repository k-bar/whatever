import base64
import binascii
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, get_verified_user
from app.db import get_db
from app.friends import friend_ids
from app.models import Event, Occurrence, Source, User
from app.routers.events import feature
from app.schemas import FeatureCollection, GeoJSONFeature
from app.userevents import AUDIENCES, EVENT_TYPES, PUBLIC_AUDIENCES, SOURCE_SLUG
from app.userevents.models import UserEvent, UserEventPhoto
from app.userevents.service import extra_props, photo_url, publish

router = APIRouter(prefix="/userevents", tags=["userevents"])

MAX_PHOTO_BYTES = 3 * 1024 * 1024
IMAGE_MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"RIFF": "image/webp"}


class PhotoIn(BaseModel):
    data_url: str = Field(max_length=5_000_000)  # "data:image/jpeg;base64,..." (the app resizes first)


class PhotoOut(BaseModel):
    id: str
    url: str


class UserEventIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    subtitle: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    event_type: Literal[tuple(EVENT_TYPES)]  # type: ignore[valid-type]
    audience: Literal[AUDIENCES]  # type: ignore[valid-type]
    starts_at: datetime
    ends_at: datetime | None = None
    lat: float = Field(ge=52.0, le=52.5)
    lng: float = Field(ge=20.7, le=21.4)
    venue_name: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=300)
    photo_id: str | None = Field(None, max_length=32)
    invited_user_ids: list[int] = Field(default_factory=list, max_length=200)


class UserEventOut(BaseModel):
    id: int
    title: str
    subtitle: str | None
    description: str | None
    event_type: str
    category: str
    audience: str
    starts_at: datetime
    ends_at: datetime | None
    lat: float
    lng: float
    venue_name: str | None
    address: str | None
    image_url: str | None
    invited_user_ids: list[int]
    status: str
    event_id: int | None  # the public copy in /events (Syrenka Users), if any
    created_at: datetime


class CreatedOut(BaseModel):
    event: UserEventOut
    feature: GeoJSONFeature  # ready to drop onto the map


def event_out(ue: UserEvent) -> UserEventOut:
    return UserEventOut(
        **{f: getattr(ue, f) for f in UserEventOut.model_fields if f != "image_url"},
        image_url=photo_url(ue.photo_id),
    )


def private_feature(ue: UserEvent) -> GeoJSONFeature:
    """Pin for an event that isn't in the public feed: built straight from user_events."""
    props = {
        "event_id": f"ue-{ue.id}",
        "kind": "event",
        "title": ue.title,
        "categories": [ue.category],
        "lead": (ue.description or "")[:300] or None,
        "image_url": photo_url(ue.photo_id),
        "url": None,
        "district": None,
        "venue_name": ue.venue_name,
        "address": ue.address,
        "source": SOURCE_SLUG,
        "is_public_invite": False,
        "seats_left": None,
        "starts_at": ue.starts_at.isoformat(),
        "ends_at": ue.ends_at.isoformat() if ue.ends_at else None,
        "daily": False,
        "attendees": 1,
        "wanting_company": 0,
    } | extra_props(ue)
    return GeoJSONFeature(
        id=-ue.id, geometry={"type": "Point", "coordinates": [ue.lng, ue.lat]}, properties=props
    )


@router.post("/photos", response_model=PhotoOut, status_code=201)
def upload_photo(body: PhotoIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload the event photo first, then pass its id as photo_id when creating the event."""
    try:
        data = base64.b64decode(body.data_url.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "data_url must be a base64 data URL")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo is larger than 3 MB")
    content_type = next((t for magic, t in IMAGE_MAGIC.items() if data.startswith(magic)), None)
    if content_type is None or (content_type == "image/webp" and data[8:12] != b"WEBP"):
        raise HTTPException(415, "Only JPEG, PNG or WebP photos")
    photo = UserEventPhoto(id=uuid.uuid4().hex, uploader_id=user.id, content_type=content_type, data=data)
    db.add(photo)
    db.commit()
    return PhotoOut(id=photo.id, url=photo_url(photo.id))


@router.get("/photos/{photo_id}")
def get_photo(photo_id: str, db: Session = Depends(get_db)):
    photo = db.get(UserEventPhoto, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return Response(
        photo.data,
        media_type=photo.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("", response_model=CreatedOut, status_code=201)
def create_user_event(
    body: UserEventIn, user: User = Depends(get_verified_user), db: Session = Depends(get_db)
):
    """Create an event. Public audiences also go onto the Syrenka Users API, so everyone's map shows it."""
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(422, "ends_at is before starts_at")
    if body.photo_id:
        photo = db.get(UserEventPhoto, body.photo_id)
        if photo is None or photo.uploader_id != user.id:
            raise HTTPException(422, "Unknown photo_id")
    ue = UserEvent(
        **body.model_dump(),
        category=EVENT_TYPES[body.event_type],
        host_user_id=user.id,
        host=user,
        status="active",
    )
    db.add(ue)
    db.flush()
    event = publish(db, ue) if ue.audience in PUBLIC_AUDIENCES else None
    db.commit()
    if event is None:
        return CreatedOut(event=event_out(ue), feature=private_feature(ue))
    f = feature(event, event.occurrences[0], attendees=1, wanting=1)
    return CreatedOut(event=event_out(ue), feature=f)


@router.get("/mine", response_model=list[UserEventOut])
def my_user_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Everything I've created, newest first, with its status (active / cancelled)."""
    rows = db.scalars(
        select(UserEvent).where(UserEvent.host_user_id == user.id).order_by(UserEvent.created_at.desc())
    ).all()
    return [event_out(ue) for ue in rows]


@router.get("/private", response_model=FeatureCollection)
def private_user_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Non-public events on my map: ones I host, am invited to, or my friends host for their friends.
    Public ones come from GET /events."""
    friends = friend_ids(db, user.id)
    rows = db.scalars(
        select(UserEvent)
        .where(
            UserEvent.status == "active",
            UserEvent.audience.not_in(PUBLIC_AUDIENCES),
            or_(UserEvent.ends_at >= datetime.now(UTC), UserEvent.starts_at >= datetime.now(UTC)),
            or_(
                UserEvent.host_user_id == user.id,
                UserEvent.invited_user_ids.contains([user.id]),
                and_(UserEvent.audience == "friends", UserEvent.host_user_id.in_(friends)),
            ),
        )
        .options(selectinload(UserEvent.host))
        .order_by(UserEvent.starts_at)
    ).all()
    return FeatureCollection(features=[private_feature(ue) for ue in rows])


@router.get("/public", response_model=FeatureCollection)
def public_user_events(db: Session = Depends(get_db)):
    """The Syrenka Users API: upcoming public events created by users (they're also in GET /events)."""
    rows = db.execute(
        select(Event, Occurrence)
        .join(Occurrence, Occurrence.event_id == Event.id)
        .join(Source, Source.id == Event.source_id)
        .where(Source.slug == SOURCE_SLUG, Event.is_active, Occurrence.starts_at >= datetime.now(UTC))
        .options(selectinload(Event.source))
        .order_by(Occurrence.starts_at)
    ).all()
    return FeatureCollection(features=[feature(e, o) for e, o in rows])


@router.delete("/{user_event_id}", status_code=204)
def cancel_user_event(
    user_event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Host cancels: the event stays in the history but leaves every map."""
    ue = db.get(UserEvent, user_event_id)
    if ue is None or ue.host_user_id != user.id:
        raise HTTPException(404, "Event not found")
    if ue.status != "cancelled":
        ue.status = "cancelled"
        if ue.event is not None and ue.event.is_active:
            ue.event.is_active = False
            ue.event.source.item_count = max(0, (ue.event.source.item_count or 1) - 1)
        db.commit()
    return Response(status_code=204)
