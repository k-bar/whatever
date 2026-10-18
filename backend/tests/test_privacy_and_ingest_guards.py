"""Regressions from the code review: who sees what, cancelled events, seats, and broken sources."""

import json
from unittest import mock

import pytest
from sqlalchemy import select

from app.ingest import overpass
from app.ingest.run import load
from app.ingest.sources import SOURCES
from app.models import Event, Occurrence
from tests.conftest import register
from tests.test_ingest import raw
from tests.test_userevents import new_event


def befriend(client, a, b, b_username):
    client.post("/friends/requests", json={"username": b_username}, headers=a)
    req = client.get("/me/friend-requests", headers=b).json()[0]
    client.patch(f"/friend-requests/{req['id']}", json={"status": "accepted"}, headers=b)


def uid(client, auth) -> int:
    return client.get("/me", headers=auth).json()["id"]


def test_invite_only_events_stay_out_of_friends_hosting_list(client, alice, bob):
    befriend(client, alice, bob, "bob")
    client.post(
        "/userevents", json=new_event(title="Secret surprise party", audience="invite"), headers=alice
    )
    client.post("/userevents", json=new_event(title="Open picnic"), headers=alice)
    titles = [
        e["title"]
        for e in client.get(f"/users/{uid(client, alice)}/events?scope=hosting", headers=bob).json()
    ]
    assert titles == ["Open picnic"]
    mine = client.get(f"/users/{uid(client, alice)}/events?scope=hosting", headers=alice).json()
    assert len(mine) == 2  # the host sees both


def test_attendee_list_shows_strangers_only_when_they_want_company(client, db, alice, bob):
    carol = register(client, "carol@example.com", "Carol")
    load(db, SOURCES["warsaw_events"], [raw("x")], None)
    db.commit()
    occ = db.scalar(select(Occurrence.id))
    client.put(f"/occurrences/{occ}/attendance", json={"wants_company": False}, headers=alice)
    client.put(f"/occurrences/{occ}/attendance", json={"wants_company": True}, headers=carol)

    def names(who):
        return sorted(
            a["user"]["display_name"] for a in client.get(f"/occurrences/{occ}/attendees", headers=who).json()
        )

    assert names(bob) == ["Carol"]  # Alice goes quietly: a stranger doesn't see her
    befriend(client, alice, bob, "bob")
    assert names(bob) == ["Alice", "Carol"]


def test_cancelled_event_leaves_going_list(client, alice, bob):
    ev = client.post("/userevents", json=new_event(), headers=alice).json()
    occ = ev["feature"]["properties"]["occurrence_id"]
    client.put(f"/occurrences/{occ}/attendance", json={"wants_company": True}, headers=bob)
    me = uid(client, bob)
    assert len(client.get(f"/users/{me}/events?scope=going", headers=bob).json()) == 1
    client.delete(f"/userevents/{ev['event']['id']}", headers=alice)
    assert client.get(f"/users/{me}/events?scope=going", headers=bob).json() == []


def test_ingest_refuses_to_empty_a_source(db):
    spec = SOURCES["warsaw_events"]
    load(db, spec, [raw(f"e{i}") for i in range(30)], None)
    db.commit()
    with pytest.raises(RuntimeError, match="keeping the old ones"):
        load(db, spec, [], None)  # e.g. the city's API blocked us
    db.rollback()
    assert db.query(Event).filter(Event.is_active).count() == 30


def test_overpass_timeout_remark_is_a_failure():
    class Answer:
        def __init__(self, data):
            self.data = json.dumps(data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.data

    busy = Answer({"remark": "runtime error: Query timed out", "elements": []})
    ok = Answer({"elements": [{"id": 1}]})
    with mock.patch("urllib.request.urlopen", side_effect=[busy, ok]):
        assert overpass.overpass("q") == [{"id": 1}]  # the next mirror answered in full
    with mock.patch("urllib.request.urlopen", side_effect=[busy, busy]), pytest.raises(RuntimeError):
        overpass.overpass("q")


def test_last_seat_goes_once(client, db, alice, bob):
    ev = client.post("/userevents", json=new_event(audience="public_confirm"), headers=alice).json()
    occ = ev["feature"]["properties"]["occurrence_id"]
    db.execute(Event.__table__.update().where(Event.id == ev["event"]["event_id"]).values(seats_left=1))
    db.commit()
    carol = register(client, "carol@example.com", "Carol")
    host = uid(client, alice)
    for who in (bob, carol):
        client.post(f"/occurrences/{occ}/join-requests", json={"target_user_id": host}, headers=who)
    reqs = client.get("/me/join-requests", headers=alice).json()
    codes = [
        client.patch(f"/join-requests/{r['id']}", json={"status": "accepted"}, headers=alice).status_code
        for r in reqs
    ]
    assert sorted(codes) == [200, 409]
    assert db.scalar(select(Event.seats_left).where(Event.id == ev["event"]["event_id"])) == 0


def test_live_chat_stops_reaching_someone_who_lost_access(client, db, alice, bob):
    from app import realtime
    from app.models import Chat, ChatMessage
    from tests.test_chats import befriend as make_friends
    from tests.test_chats import create, say

    make_friends(client, alice, bob, "bob")
    ue = create(client, alice, audience="friends")
    path, key = f"userevent/{ue['id']}", f"userevent:{ue['id']}"
    assert say(client, bob, path, "I'm in").status_code == 201  # bob joins the chat
    chat_id = db.scalar(select(Chat.id))
    msg_id = db.scalar(select(ChatMessage.id))
    alice_id, bob_id = uid(client, alice), uid(client, bob)
    _, allowed = realtime._notification(chat_id, key, "message", msg_id, {bob_id})
    assert allowed == {alice_id, bob_id}

    client.delete(f"/friends/{bob_id}", headers=alice)  # no longer friends: the friends-only chat is gone
    _, allowed = realtime._notification(chat_id, key, "message", msg_id, {bob_id})
    assert allowed == {alice_id}
