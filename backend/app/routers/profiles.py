"""Profiles ("mini Facebook"): @usernames, friends, and the events someone is going to, has been to
and is hosting. Stats (friends · been to · hosted) are public; the event lists are for the person
themself and their friends.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import usernames
from app.auth import get_current_user, get_optional_user
from app.db import get_db
from app.models import Attendance, Event, Friendship, Occurrence, User
from app.schemas import (
    FriendDecisionIn,
    FriendRequestIn,
    FriendRequestOut,
    ProfileEvent,
    ProfileOut,
    ProfileStats,
    PublicUser,
    UsernameCheck,
)
from app.userevents.models import UserEvent
from app.userevents.router import photo_url

router = APIRouter(tags=["profiles"])


def pair(db: Session, a: int, b: int) -> Friendship | None:
    return db.scalar(
        select(Friendship).where(
            func.least(Friendship.requester_id, Friendship.addressee_id) == min(a, b),
            func.greatest(Friendship.requester_id, Friendship.addressee_id) == max(a, b),
        )
    )


def relation(db: Session, viewer: User | None, user: User) -> str:
    if viewer is None:
        return "none"
    if viewer.id == user.id:
        return "self"
    f = pair(db, viewer.id, user.id)
    if f is None:
        return "none"
    if f.status == "accepted":
        return "friends"
    return "request_sent" if f.requester_id == viewer.id else "request_received"


def friend_ids(db: Session, user_id: int) -> list[int]:
    rows = db.execute(
        select(Friendship.requester_id, Friendship.addressee_id).where(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
        )
    ).all()
    return [b if a == user_id else a for a, b in rows]


ENDED = func.coalesce(Occurrence.ends_at, Occurrence.starts_at)


def stats(db: Session, user_id: int) -> ProfileStats:
    now = datetime.now(UTC)
    been = db.scalar(
        select(func.count())
        .select_from(Attendance)
        .join(Occurrence, Occurrence.id == Attendance.occurrence_id)
        .where(Attendance.user_id == user_id, ENDED < now)
    )
    hosted = db.scalar(
        select(func.count())
        .select_from(UserEvent)
        .where(UserEvent.host_user_id == user_id, UserEvent.status == "active")
    )
    return ProfileStats(friends=len(friend_ids(db, user_id)), been_to=been or 0, hosted=hosted or 0)


def profile_out(db: Session, viewer: User | None, user: User) -> ProfileOut:
    rel = relation(db, viewer, user)
    return ProfileOut(
        **PublicUser.model_validate(user).model_dump(),
        stats=stats(db, user.id),
        relation=rel,
        can_see_events=rel in ("self", "friends"),
    )


# --- profile pages ------------------------------------------------------------------------------


@router.get("/users/{user_id}/profile", response_model=ProfileOut)
def profile_by_id(
    user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return profile_out(db, viewer, user)


@router.get("/profiles/{username}", response_model=ProfileOut)
def profile_by_username(
    username: str, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    user = db.scalar(select(User).where(User.username == usernames.normalize(username)))
    if user is None:
        raise HTTPException(404, "User not found")
    return profile_out(db, viewer, user)


@router.get("/usernames/{username}/available", response_model=UsernameCheck)
def username_available(
    username: str, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    """Live check for the @username field. Your own current username counts as available."""
    name = usernames.normalize(username)
    if why := usernames.problem(name):
        return UsernameCheck(username=name, available=False, reason=why)
    if usernames.is_taken(db, name, except_user_id=viewer.id if viewer else None):
        return UsernameCheck(username=name, available=False, reason="Username taken")
    return UsernameCheck(username=name, available=True)


@router.get("/people/search", response_model=list[PublicUser])
def search_people(
    q: str = Query(min_length=2, max_length=40),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Find people to add: @username prefix first, then display names."""
    term = usernames.normalize(q)
    like = f"%{q.strip()}%"
    stmt = (
        select(User)
        .where(or_(User.username.startswith(term, autoescape=True), User.display_name.ilike(like)))
        .order_by(User.username.startswith(term, autoescape=True).desc(), User.username)
        .limit(10)
    )
    if viewer is not None:
        stmt = stmt.where(User.id != viewer.id)
    return db.scalars(stmt).all()


# --- going / been to / hosting --------------------------------------------------------------------


@router.get("/users/{user_id}/events", response_model=list[ProfileEvent])
def profile_events(
    user_id: int,
    scope: Literal["going", "been", "hosting"],
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if relation(db, viewer, user) not in ("self", "friends"):
        raise HTTPException(403, "Only friends can see this")
    now = datetime.now(UTC)

    if scope == "hosting":  # upcoming events this person created
        rows = db.scalars(
            select(UserEvent)
            .where(
                UserEvent.host_user_id == user_id,
                UserEvent.status == "active",
                func.coalesce(UserEvent.ends_at, UserEvent.starts_at) >= now,
            )
            .order_by(UserEvent.starts_at)
            .limit(100)
        ).all()
        return [
            ProfileEvent(
                event_id=ue.event_id,
                occurrence_id=None,
                user_event_id=ue.id,
                title=ue.title,
                starts_at=ue.starts_at,
                ends_at=ue.ends_at,
                venue_name=ue.venue_name,
                image_url=photo_url(ue.photo_id),
                category=ue.category,
                lat=ue.lat,
                lng=ue.lng,
            )
            for ue in rows
        ]

    upcoming = scope == "going"
    rows = db.execute(
        select(Event, Occurrence)
        .join(Occurrence, Occurrence.event_id == Event.id)
        .join(Attendance, and_(Attendance.occurrence_id == Occurrence.id, Attendance.user_id == user_id))
        .where(ENDED >= now if upcoming else ENDED < now)
        # events you host are listed under "hosting", not again under "going" (they still count as been to)
        .where(or_(Event.host_user_id.is_(None), Event.host_user_id != user_id) if upcoming else True)
        .order_by(Occurrence.starts_at if upcoming else Occurrence.starts_at.desc())
        .limit(100)
    ).all()
    return [
        ProfileEvent(
            event_id=e.id,
            occurrence_id=o.id,
            user_event_id=None,
            title=e.title,
            starts_at=o.starts_at,
            ends_at=o.ends_at,
            venue_name=e.venue_name,
            image_url=e.image_url,
            category=(e.categories or [None])[0],
            lat=e.lat,
            lng=e.lng,
        )
        for e, o in rows
    ]


# --- friends ----------------------------------------------------------------------------------------


def request_out(f: Friendship, me: User) -> FriendRequestOut:
    incoming = f.addressee_id == me.id
    other = f.requester if incoming else f.addressee
    return FriendRequestOut(
        id=f.id,
        direction="incoming" if incoming else "outgoing",
        status=f.status,
        user=PublicUser.model_validate(other),
        created_at=f.created_at,
    )


@router.post("/friends/requests", response_model=FriendRequestOut, status_code=201)
def send_friend_request(
    body: FriendRequestIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Ask @username to be friends. If they already asked you, this accepts it."""
    other = db.scalar(select(User).where(User.username == usernames.normalize(body.username)))
    if other is None:
        raise HTTPException(404, "User not found")
    if other.id == me.id:
        raise HTTPException(422, "You can't add yourself")
    existing = pair(db, me.id, other.id)
    if existing is not None:
        if existing.status == "pending" and existing.addressee_id == me.id:
            existing.status, existing.responded_at = "accepted", datetime.now(UTC)
            db.commit()
        return request_out(existing, me)
    f = Friendship(requester_id=me.id, addressee_id=other.id, status="pending")
    db.add(f)
    try:
        db.commit()
    except IntegrityError:  # they asked at the same moment
        db.rollback()
        f = pair(db, me.id, other.id)
    db.refresh(f)
    return request_out(f, me)


@router.get("/me/friend-requests", response_model=list[FriendRequestOut])
def my_friend_requests(
    direction: Literal["incoming", "outgoing"] = "incoming",
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    side = Friendship.addressee_id if direction == "incoming" else Friendship.requester_id
    rows = db.scalars(
        select(Friendship)
        .where(side == me.id, Friendship.status == "pending")
        .order_by(Friendship.created_at.desc())
    ).all()
    return [request_out(f, me) for f in rows]


@router.patch("/friend-requests/{request_id}", response_model=FriendRequestOut)
def answer_friend_request(
    request_id: int,
    body: FriendDecisionIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    f = db.get(Friendship, request_id)
    if f is None or f.addressee_id != me.id or f.status != "pending":
        raise HTTPException(404, "Friend request not found")
    out = request_out(f, me)
    if body.status == "declined":  # declining just removes it; they can ask again later
        db.delete(f)
        db.commit()
        return out
    f.status, f.responded_at = "accepted", datetime.now(UTC)
    db.commit()
    return request_out(f, me)


@router.get("/users/{user_id}/friends", response_model=list[PublicUser])
def list_friends(
    user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if relation(db, viewer, user) not in ("self", "friends"):
        raise HTTPException(403, "Only friends can see this")
    ids = friend_ids(db, user_id)
    return db.scalars(select(User).where(User.id.in_(ids)).order_by(User.display_name)).all() if ids else []


@router.delete("/friends/{user_id}", status_code=204)
def unfriend(user_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove a friend, or withdraw / decline a pending request between us."""
    f = pair(db, me.id, user_id)
    if f is None:
        raise HTTPException(404, "Not friends")
    db.delete(f)
    db.commit()
