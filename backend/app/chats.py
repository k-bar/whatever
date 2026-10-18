"""What the chat endpoints (app/routers/chats.py) and live delivery (app/realtime.py) share: chat keys,
which event a chat belongs to and who may open it, and how a message looks on the wire."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.friends import friend_ids
from app.models import Chat, ChatMessage, Event, Occurrence, User
from app.userevents.models import UserEvent
from app.userevents.service import can_see, photo_url

# Postgres NOTIFY channel; prod and dev share one RDS database, so it carries the schema
CHANNEL = f"chat_{settings.db_schema or 'public'}"

Kind = Literal["event", "userevent"]


class ChatAuthor(BaseModel):
    id: int
    username: str
    display_name: str
    photo: str | None


class ChatMessageOut(BaseModel):
    id: int
    key: str
    user: ChatAuthor
    body: str | None  # null once deleted
    created_at: datetime
    deleted: bool


@dataclass
class Target:
    kind: Kind
    target_id: int
    title: str
    starts_at: datetime | None
    image_url: str | None
    host_user_id: int | None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.target_id}"

    @property
    def column(self):
        return Chat.event_id if self.kind == "event" else Chat.user_event_id


def parse_key(key: str) -> tuple[Kind, int]:
    kind, _, raw = key.partition(":")
    if kind not in ("event", "userevent") or not raw.isdigit():
        raise HTTPException(404, "Chat not found")
    return kind, int(raw)  # type: ignore[return-value]


def chat_ref(chat: Chat) -> tuple[Kind, int]:
    return ("event", chat.event_id) if chat.event_id else ("userevent", chat.user_event_id)


def next_start(occurrences: list[Occurrence]) -> datetime | None:
    now = datetime.now(UTC)
    upcoming = [o.starts_at for o in occurrences if (o.ends_at or o.starts_at) >= now]
    return min(upcoming) if upcoming else (occurrences[-1].starts_at if occurrences else None)


def resolve(db: Session, kind: Kind, target_id: int, user: User | None) -> Target:
    """The event a chat belongs to, if this user may see it. A user event that is also published
    in /events answers as kind "event", so both ways of opening it share one thread."""
    t = resolve_many(db, [(kind, target_id)], user).get((kind, target_id))
    if t is None:
        raise HTTPException(404, "Chat not found")
    return t


def resolve_many(
    db: Session, refs: Iterable[tuple[Kind, int]], user: User | None
) -> dict[tuple[Kind, int], Target]:
    """resolve() for many chats in a few queries (GET /me/chats). Chats this user may not open
    (event gone, unfriended, uninvited) are left out."""
    refs = list(refs)
    ue_ids = {i for k, i in refs if k == "userevent"}
    ues = (
        {ue.id: ue for ue in db.scalars(select(UserEvent).where(UserEvent.id.in_(ue_ids)))} if ue_ids else {}
    )
    friends = None
    if user is not None and any(ue.audience == "friends" for ue in ues.values()):
        friends = set(friend_ids(db, user.id))
    visible = {i: ue for i, ue in ues.items() if can_see(db, user, ue, friends)}

    event_ids = {i for k, i in refs if k == "event"} | {ue.event_id for ue in visible.values() if ue.event_id}
    events = {}
    if event_ids:
        stmt = select(Event).where(Event.id.in_(event_ids)).options(selectinload(Event.occurrences))
        events = {ev.id: ev for ev in db.scalars(stmt)}

    out = {}
    for kind, target_id in refs:
        event_id = target_id
        if kind == "userevent":
            ue = visible.get(target_id)
            if ue is None:
                continue
            if ue.event_id is None:
                out[kind, target_id] = Target(
                    "userevent", ue.id, ue.title, ue.starts_at, photo_url(ue.photo_id), ue.host_user_id
                )
                continue
            event_id = ue.event_id
        ev = events.get(event_id)
        if ev is not None:
            out[kind, target_id] = Target(
                "event", ev.id, ev.title, next_start(ev.occurrences), ev.image_url, ev.host_user_id
            )
    return out


def message_out(m: ChatMessage, key: str) -> ChatMessageOut:
    u = m.user
    return ChatMessageOut(
        id=m.id,
        key=key,
        user=ChatAuthor(
            id=u.id, username=u.username, display_name=u.display_name, photo=(u.photos or [None])[0]
        ),
        body=None if m.deleted_at else m.body,
        created_at=m.created_at,
        deleted=m.deleted_at is not None,
    )
