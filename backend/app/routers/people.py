"""People on the map: "share my area".

Someone who switches on "Share my area" shows up for everyone as a pulsing pin, roughly where they are
(rounded to ~100 m, never the exact spot), meaning "I'm around, come and hang out". A shared area goes
stale after AREA_TTL without an update (the app re-sends it while it's open), except for the demo
people from app/mocksocial.py, who are always out.

    GET /people/sharing   everyone sharing their area, with the event they're hosting next
    GET /me/area          my switch + last area
    PUT /me/area          {"share": true, "lat": 52.23, "lng": 21.01}  (share: false hides me at once)
    GET /people/avatar.svg  the Syrenka favicon, used as the demo people's profile picture
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_optional_user
from app.db import get_db
from app.models import User
from app.routers.profiles import friend_ids
from app.userevents.models import UserEvent

router = APIRouter(tags=["people"])

AREA_TTL = timedelta(hours=6)
AVATAR = (Path(__file__).parent.parent / "data" / "avatar.svg").read_bytes()


class AreaIn(BaseModel):
    share: bool
    lat: float | None = Field(None, ge=52.0, le=52.5)
    lng: float | None = Field(None, ge=20.7, le=21.4)


class AreaOut(BaseModel):
    share: bool
    lat: float | None
    lng: float | None
    at: datetime | None


class HostingOut(BaseModel):
    user_event_id: int
    event_id: int | None  # its pin in /events (Syrenka Users)
    title: str
    starts_at: datetime
    venue_name: str | None
    lat: float
    lng: float


class SharingPerson(BaseModel):
    id: int
    username: str
    display_name: str
    photos: list[str]
    interests: list[str]
    lat: float
    lng: float
    at: datetime | None
    is_friend: bool
    is_self: bool
    hosting: HostingOut | None


def rounded(v: float) -> float:
    return round(v, 3)  # ~110 m north-south, ~70 m east-west in Warsaw


@router.get("/people/sharing", response_model=list[SharingPerson])
def sharing(viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    people = db.scalars(
        select(User)
        .where(User.share_area, User.area_lat.is_not(None), User.area_lng.is_not(None))
        .where(or_(User.is_mock, User.area_at >= now - AREA_TTL))
        .order_by(User.id)
        .limit(500)
    ).all()
    if not people:
        return []
    ids = [p.id for p in people]
    friends = set(friend_ids(db, viewer.id)) if viewer else set()
    nxt = {}
    for ue in db.scalars(
        select(UserEvent)
        .where(
            UserEvent.host_user_id.in_(ids),
            UserEvent.status == "active",
            UserEvent.audience.in_(("public", "public_confirm")),
            func.coalesce(UserEvent.ends_at, UserEvent.starts_at) >= now,
        )
        .order_by(UserEvent.starts_at)
    ):
        nxt.setdefault(ue.host_user_id, ue)
    out = []
    for p in people:
        ue = nxt.get(p.id)
        out.append(
            SharingPerson(
                id=p.id,
                username=p.username,
                display_name=p.display_name,
                photos=p.photos or [],
                interests=p.interests or [],
                lat=p.area_lat,
                lng=p.area_lng,
                at=p.area_at,
                is_friend=p.id in friends,
                is_self=viewer is not None and viewer.id == p.id,
                hosting=HostingOut(
                    user_event_id=ue.id,
                    event_id=ue.event_id,
                    title=ue.title,
                    starts_at=ue.starts_at,
                    venue_name=ue.venue_name,
                    lat=ue.lat,
                    lng=ue.lng,
                )
                if ue
                else None,
            )
        )
    return out


def area_out(u: User) -> AreaOut:
    return AreaOut(share=u.share_area, lat=u.area_lat, lng=u.area_lng, at=u.area_at)


@router.get("/me/area", response_model=AreaOut)
def my_area(me: User = Depends(get_current_user)):
    return area_out(me)


@router.put("/me/area", response_model=AreaOut)
def set_my_area(body: AreaIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.share:
        if body.lat is None or body.lng is None:
            if me.area_lat is None:
                raise HTTPException(422, "Where are you? Send lat and lng with share: true")
        else:
            me.area_lat, me.area_lng = rounded(body.lat), rounded(body.lng)
        me.area_at = datetime.now(UTC)
    me.share_area = body.share
    db.commit()
    return area_out(me)


@router.get("/people/avatar.svg", include_in_schema=False)
def avatar():
    return Response(AVATAR, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
