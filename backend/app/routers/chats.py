"""Event chats: one thread per event, for anyone who can see the event.

A chat is addressed by its event: kind "event" (any pin in /events, including public user events)
or "userevent" (friends-only / invite-only user events, which are not in /events). Reading needs a
login; writing needs a confirmed email. Posting (or hosting the event) makes you a member: the chat
then shows in GET /me/chats with an unread count, and new messages reach you live over GET /ws
(app/realtime.py).
"""

import json
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, get_verified_user
from app.chats import CHANNEL, ChatMessageOut, Kind, Target, chat_ref, message_out, resolve, resolve_many
from app.db import get_db
from app.models import Chat, ChatMember, ChatMessage, User

router = APIRouter(tags=["chats"])

MAX_BODY = 2000
RATE = (8, 10.0)  # at most 8 messages per 10 seconds per person (per API worker)
_recent: dict[int, deque] = defaultdict(deque)


class ChatInfo(BaseModel):
    key: str  # "event:12" / "userevent:3": what GET /ws subscribes to
    kind: Kind
    target_id: int
    title: str
    starts_at: datetime | None
    image_url: str | None
    host_user_id: int | None
    joined: bool
    unread: int
    last_read_id: int


class ChatSummary(ChatInfo):
    last_message: ChatMessageOut | None
    last_message_at: datetime | None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)


class ReadIn(BaseModel):
    last_read_id: int = Field(ge=0)


def find_chat(db: Session, t: Target) -> Chat | None:
    return db.scalar(select(Chat).where(t.column == t.target_id))


def ensure_chat(db: Session, t: Target) -> Chat:
    """Get or create (race-safe) the chat; the event's host is always a member."""
    db.execute(insert(Chat).values({t.column.key: t.target_id}).on_conflict_do_nothing())
    chat = find_chat(db, t)
    if t.host_user_id:
        join(db, chat.id, t.host_user_id)
    return chat


def join(db: Session, chat_id: int, user_id: int, last_read_id: int = 0) -> None:
    stmt = insert(ChatMember).values(chat_id=chat_id, user_id=user_id, last_read_id=last_read_id)
    db.execute(stmt.on_conflict_do_nothing())


def member(db: Session, chat: Chat | None, user: User) -> ChatMember | None:
    return db.get(ChatMember, (chat.id, user.id)) if chat else None


def unread_count(db: Session, chat_id: int, user_id: int, after: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(
            ChatMessage.chat_id == chat_id,
            ChatMessage.id > after,
            ChatMessage.user_id != user_id,
            ChatMessage.deleted_at.is_(None),
        )
    )


def notify(db: Session, chat: Chat, key: str, op: str, message_id: int) -> None:
    """Delivered by Postgres when the transaction commits (app/realtime.py)."""
    payload = json.dumps({"chat_id": chat.id, "key": key, "op": op, "id": message_id})
    db.execute(select(func.pg_notify(CHANNEL, payload)))


def info(db: Session, t: Target, user: User) -> ChatInfo:
    chat = find_chat(db, t)
    m = member(db, chat, user)
    last_read = m.last_read_id if m else 0
    return ChatInfo(
        key=t.key,
        kind=t.kind,
        target_id=t.target_id,
        title=t.title,
        starts_at=t.starts_at,
        image_url=t.image_url,
        host_user_id=t.host_user_id,
        joined=m is not None,
        unread=unread_count(db, chat.id, user.id, last_read) if m else 0,
        last_read_id=last_read,
    )


def throttle(user: User) -> None:
    limit, window = RATE
    q, now = _recent[user.id], time.monotonic()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Slow down a little")
    q.append(now)


# --- endpoints ----------------------------------------------------------------------------------


@router.get("/chats/{kind}/{target_id}", response_model=ChatInfo)
def get_chat(
    kind: Kind, target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return info(db, resolve(db, kind, target_id, user), user)


@router.get("/chats/{kind}/{target_id}/messages", response_model=list[ChatMessageOut])
def list_messages(
    kind: Kind,
    target_id: int,
    before: int | None = Query(None, description="older page: messages with id < before"),
    after: int | None = Query(None, description="catch up after a reconnect: messages with id > after"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Oldest first. Without before/after: the latest `limit` messages."""
    t = resolve(db, kind, target_id, user)
    chat = find_chat(db, t)
    if chat is None:
        return []
    stmt = select(ChatMessage).where(ChatMessage.chat_id == chat.id).options(selectinload(ChatMessage.user))
    if after is not None:
        rows = db.scalars(stmt.where(ChatMessage.id > after).order_by(ChatMessage.id).limit(limit)).all()
    else:
        if before is not None:
            stmt = stmt.where(ChatMessage.id < before)
        rows = list(reversed(db.scalars(stmt.order_by(ChatMessage.id.desc()).limit(limit)).all()))
    return [message_out(m, t.key) for m in rows]


@router.post("/chats/{kind}/{target_id}/messages", response_model=ChatMessageOut, status_code=201)
def post_message(
    kind: Kind,
    target_id: int,
    body: MessageIn,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    text = body.body.strip()
    if not text:
        raise HTTPException(422, "Empty message")
    t = resolve(db, kind, target_id, user)
    throttle(user)
    chat = ensure_chat(db, t)
    msg = ChatMessage(chat_id=chat.id, user_id=user.id, body=text, user=user)
    db.add(msg)
    db.flush()
    join(db, chat.id, user.id)
    db.execute(
        ChatMember.__table__.update()
        .where(and_(ChatMember.chat_id == chat.id, ChatMember.user_id == user.id))
        .values(last_read_id=msg.id)
    )
    chat.last_message_at = msg.created_at
    notify(db, chat, t.key, "message", msg.id)
    db.commit()
    return message_out(msg, t.key)


@router.delete("/chats/messages/{message_id}", status_code=204)
def delete_message(message_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authors can delete their messages; hosts can delete any message in their event's chat."""
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.deleted_at is not None:
        raise HTTPException(404, "Message not found")
    chat = db.get(Chat, msg.chat_id)
    t = resolve(db, *chat_ref(chat), user)
    if user.id not in (msg.user_id, t.host_user_id):
        raise HTTPException(403, "Only the author or the host can delete this")
    msg.deleted_at = datetime.now(UTC)
    notify(db, chat, t.key, "deleted", msg.id)
    db.commit()
    return Response(status_code=204)


@router.put("/chats/{kind}/{target_id}/read", response_model=ChatInfo)
def mark_read(
    kind: Kind,
    target_id: int,
    body: ReadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = resolve(db, kind, target_id, user)
    m = member(db, find_chat(db, t), user)
    if m is not None and body.last_read_id > m.last_read_id:
        m.last_read_id = body.last_read_id
        db.commit()
    return info(db, t, user)


@router.put("/chats/{kind}/{target_id}/membership", response_model=ChatInfo)
def join_chat(
    kind: Kind, target_id: int, user: User = Depends(get_verified_user), db: Session = Depends(get_db)
):
    """Follow a chat without posting: it shows in Messages, and new messages count as unread."""
    t = resolve(db, kind, target_id, user)
    chat = ensure_chat(db, t)
    newest = db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.chat_id == chat.id)) or 0
    join(db, chat.id, user.id, last_read_id=newest)
    db.commit()
    return info(db, t, user)


@router.delete("/chats/{kind}/{target_id}/membership", status_code=204)
def leave_chat(
    kind: Kind, target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    t = resolve(db, kind, target_id, user)
    m = member(db, find_chat(db, t), user)
    if m is not None:
        db.delete(m)
        db.commit()
    return Response(status_code=204)


@router.get("/me/chats", response_model=list[ChatSummary])
def my_chats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The Messages list: chats I follow, most recent activity first."""
    rows = db.execute(
        select(Chat, ChatMember)
        .join(ChatMember, and_(ChatMember.chat_id == Chat.id, ChatMember.user_id == user.id))
        .order_by(func.coalesce(Chat.last_message_at, Chat.created_at).desc())
        .limit(100)
    ).all()
    targets = resolve_many(db, [chat_ref(chat) for chat, _ in rows], user)
    rows = [(chat, m, targets[chat_ref(chat)]) for chat, m in rows if chat_ref(chat) in targets]
    chat_ids = [chat.id for chat, _, _ in rows]
    if not chat_ids:
        return []
    newest = (
        select(func.max(ChatMessage.id))
        .where(ChatMessage.chat_id.in_(chat_ids))
        .group_by(ChatMessage.chat_id)
    )
    last = {
        msg.chat_id: msg
        for msg in db.scalars(
            select(ChatMessage).where(ChatMessage.id.in_(newest)).options(selectinload(ChatMessage.user))
        )
    }
    unread = dict(
        db.execute(
            select(ChatMessage.chat_id, func.count())
            .join(ChatMember, and_(ChatMember.chat_id == ChatMessage.chat_id, ChatMember.user_id == user.id))
            .where(
                ChatMessage.chat_id.in_(chat_ids),
                ChatMessage.id > ChatMember.last_read_id,
                ChatMessage.user_id != user.id,
                ChatMessage.deleted_at.is_(None),
            )
            .group_by(ChatMessage.chat_id)
        ).all()
    )
    return [
        ChatSummary(
            key=t.key,
            kind=t.kind,
            target_id=t.target_id,
            title=t.title,
            starts_at=t.starts_at,
            image_url=t.image_url,
            host_user_id=t.host_user_id,
            joined=True,
            unread=unread.get(chat.id, 0),
            last_read_id=m.last_read_id,
            last_message=message_out(last[chat.id], t.key) if chat.id in last else None,
            last_message_at=chat.last_message_at,
        )
        for chat, m, t in rows
    ]
