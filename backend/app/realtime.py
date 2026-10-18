"""Live chat delivery over WebSockets (GET /ws).

The API runs several uvicorn workers, so a message posted through one worker must reach sockets
held by the others. Postgres does the fan-out: posting a message runs pg_notify(<channel>, ...) in
the same transaction (app/routers/chats.py), and every worker LISTENs on that channel (listen(),
started in app.main's lifespan) and pushes to its own sockets. No extra broker to run.
Prod and dev share one RDS database, so the channel name carries the schema.

Protocol (JSON text frames):
    -> {"type": "auth", "token": "<login token>"}      first frame, within 10 s
    <- {"type": "ready", "user_id": 1}
    -> {"type": "subscribe", "key": "event:12"}         open chat (keys: event:<id> / userevent:<id>)
    <- {"type": "subscribed", "key": "event:12"}  |  {"type": "error", "key": ..., "detail": ...}
    -> {"type": "unsubscribe", "key": "event:12"}
    -> {"type": "ping"}  <- {"type": "pong"}           keep-alive (CloudFront drops idle sockets)
    <- {"type": "message", "key": ..., "message": ChatMessageOut}   to subscribers and chat members
    <- {"type": "deleted", "key": ..., "id": 5}
Messages are sent with POST /chats/{kind}/{id}/messages, not over the socket.
"""

import asyncio
import contextlib
import json
import logging
from collections import defaultdict

import psycopg
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import make_url, select
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import SessionLocal

log = logging.getLogger(__name__)
CHANNEL = f"chat_{settings.db_schema or 'public'}"

router = APIRouter(tags=["chats"])


class Hub:
    """This worker's open sockets: by user (for unread badges) and by open chat."""

    def __init__(self) -> None:
        self.by_user: dict[int, set[WebSocket]] = defaultdict(set)
        self.by_key: dict[str, set[WebSocket]] = defaultdict(set)
        self.user_of: dict[WebSocket, int] = {}

    def add(self, ws: WebSocket, user_id: int) -> None:
        self.by_user[user_id].add(ws)
        self.user_of[ws] = user_id

    def subscriber_ids(self, key: str) -> set[int]:
        return {self.user_of[ws] for ws in self.by_key.get(key, ()) if ws in self.user_of}

    def remove(self, ws: WebSocket, user_id: int | None) -> None:
        self.user_of.pop(ws, None)
        if user_id is not None:
            self.by_user[user_id].discard(ws)
            if not self.by_user[user_id]:
                del self.by_user[user_id]
        for key in [k for k, socks in self.by_key.items() if ws in socks]:
            self.unsubscribe(ws, key)

    def subscribe(self, ws: WebSocket, key: str) -> None:
        self.by_key[key].add(ws)

    def unsubscribe(self, ws: WebSocket, key: str) -> None:
        self.by_key[key].discard(ws)
        if not self.by_key[key]:
            del self.by_key[key]

    async def deliver(self, event: dict, key: str, allowed: set[int]) -> None:
        """Send to the chat's open sockets and its members' sockets, but only for people who may
        still see the chat (`allowed`): access can end after subscribing (unfriended, uninvited)."""
        targets = {ws for ws in self.by_key.get(key, ()) if self.user_of.get(ws) in allowed}
        for uid in allowed:
            targets |= self.by_user.get(uid, set())

        async def send(ws: WebSocket) -> None:
            try:  # one phone that stopped reading must not hold up everyone else
                await asyncio.wait_for(ws.send_json(event), timeout=SEND_TIMEOUT)
            except Exception:  # closed under us / too slow; its own handler cleans up
                pass

        await asyncio.gather(*(send(ws) for ws in targets))


hub = Hub()
SEND_TIMEOUT = 5  # seconds per socket


def _notification(
    chat_id: int, key: str, op: str, message_id: int, subscribers: set[int]
) -> tuple[dict, set[int]] | None:
    """Load what a notification points at, and who may receive it: the chat's members and this
    worker's subscribers, minus anyone who can no longer open the chat. (Runs in a thread: the ORM is sync.)"""
    from app.models import ChatMember, ChatMessage, User
    from app.routers.chats import message_out, parse_key, resolve

    with SessionLocal() as db:
        members = set(db.scalars(select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)))
        kind, target_id = parse_key(key)
        allowed = set()
        for uid in members | subscribers:
            with contextlib.suppress(HTTPException):
                resolve(db, kind, target_id, db.get(User, uid))
                allowed.add(uid)
        if op == "deleted":
            return {"type": "deleted", "key": key, "id": message_id}, allowed
        msg = db.get(ChatMessage, message_id)
        if msg is None:
            return None
        return {
            "type": "message",
            "key": key,
            "message": message_out(msg, key).model_dump(mode="json"),
        }, allowed


async def _handle(payload: str) -> None:
    n = json.loads(payload)
    subscribers = hub.subscriber_ids(n["key"])
    got = await run_in_threadpool(_notification, n["chat_id"], n["key"], n["op"], n["id"], subscribers)
    if got:
        await hub.deliver(got[0], n["key"], got[1])


async def listen() -> None:
    """LISTEN for chat notifications for as long as the app runs; reconnects when the DB drops."""
    url = make_url(settings.database_url).set(drivername="postgresql")
    conninfo = url.render_as_string(hide_password=False)
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
                await conn.execute(f'LISTEN "{CHANNEL}"')
                async for note in conn.notifies():
                    try:
                        await _handle(note.payload)
                    except Exception:
                        log.exception("chat notification failed: %s", note.payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("chat listener lost the database; retrying")
            await asyncio.sleep(3)


def _authenticate(token: str) -> int:
    from app.auth import user_from_token

    with SessionLocal() as db:
        return user_from_token(db, token).id


def _may_open(user_id: int, key: str) -> None:
    from app.models import User
    from app.routers.chats import parse_key, resolve

    with SessionLocal() as db:
        kind, target_id = parse_key(key)
        resolve(db, kind, target_id, db.get(User, user_id))


@router.websocket("/ws")
async def chat_socket(ws: WebSocket):
    await ws.accept()
    user_id = None
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if first.get("type") != "auth" or not isinstance(first.get("token"), str):
            await ws.close(code=4401, reason="auth first")
            return
        try:
            user_id = await run_in_threadpool(_authenticate, first["token"])
        except HTTPException as e:
            await ws.close(code=4401, reason=str(e.detail))
            return
        hub.add(ws, user_id)
        await ws.send_json({"type": "ready", "user_id": user_id})
        while True:
            frame = await ws.receive_json()
            kind, key = frame.get("type"), frame.get("key")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "subscribe" and isinstance(key, str):
                try:
                    await run_in_threadpool(_may_open, user_id, key)
                except HTTPException as e:
                    await ws.send_json({"type": "error", "key": key, "detail": e.detail})
                    continue
                hub.subscribe(ws, key)
                await ws.send_json({"type": "subscribed", "key": key})
            elif kind == "unsubscribe" and isinstance(key, str):
                hub.unsubscribe(ws, key)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        with contextlib.suppress(Exception):
            await ws.close(code=4401, reason="auth first")
    except Exception:  # bad JSON and the like: drop the socket, the client reconnects
        log.debug("chat socket closed", exc_info=True)
    finally:
        hub.remove(ws, user_id)
