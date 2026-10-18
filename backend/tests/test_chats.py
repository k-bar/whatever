from app.main import app
from tests.conftest import register
from tests.test_userevents import new_event


def create(client, headers, **over) -> dict:
    r = client.post("/userevents", json=new_event(**over), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["event"]


def say(client, headers, path, text):
    return client.post(f"/chats/{path}/messages", json={"body": text}, headers=headers)


def befriend(client, a, b, b_username):
    client.post("/friends/requests", json={"username": b_username}, headers=a)
    req = client.get("/me/friend-requests", headers=b).json()[0]
    assert (
        client.patch(f"/friend-requests/{req['id']}", json={"status": "accepted"}, headers=b).status_code
        == 200
    )


def test_public_event_chat(client, alice, bob):
    ev = create(client, alice)
    path = f"event/{ev['event_id']}"
    assert client.get(f"/chats/{path}/messages").status_code == 401
    assert client.get(f"/chats/{path}/messages", headers=bob).json() == []

    r = say(client, bob, path, "  Anyone bringing a ball?  ")
    assert r.status_code == 201, r.text
    msg = r.json()
    assert msg["body"] == "Anyone bringing a ball?" and msg["user"]["username"] == "bob"
    assert msg["key"] == f"event:{ev['event_id']}"
    # opening it as a user event lands in the same thread
    same = client.get(f"/chats/userevent/{ev['id']}/messages", headers=alice).json()
    assert [m["id"] for m in same] == [msg["id"]]

    # the host follows their event's chat automatically and sees it as unread
    chats = client.get("/me/chats", headers=alice).json()
    assert len(chats) == 1 and chats[0]["unread"] == 1 and chats[0]["title"] == ev["title"]
    assert chats[0]["last_message"]["body"] == "Anyone bringing a ball?"
    r = client.put(f"/chats/{path}/read", json={"last_read_id": msg["id"]}, headers=alice)
    assert r.json()["unread"] == 0
    assert client.get("/me/chats", headers=bob).json()[0]["unread"] == 0  # own messages never unread

    assert say(client, alice, path, "").status_code == 422
    assert say(client, alice, path, "x" * 2001).status_code == 422


def test_paging(client, alice):
    ev = create(client, alice)
    path = f"event/{ev['event_id']}"
    ids = [say(client, alice, path, f"m{i}").json()["id"] for i in range(5)]
    latest = client.get(f"/chats/{path}/messages?limit=2", headers=alice).json()
    assert [m["body"] for m in latest] == ["m3", "m4"]
    older = client.get(f"/chats/{path}/messages?limit=2&before={latest[0]['id']}", headers=alice).json()
    assert [m["body"] for m in older] == ["m1", "m2"]
    after = client.get(f"/chats/{path}/messages?after={ids[2]}", headers=alice).json()
    assert [m["body"] for m in after] == ["m3", "m4"]


def test_unverified_can_read_not_write(client, alice):
    ev = create(client, alice)
    newbie = register(client, "new@example.com", "Newbie", verify=False)
    path = f"event/{ev['event_id']}"
    assert client.get(f"/chats/{path}/messages", headers=newbie).status_code == 200
    assert say(client, newbie, path, "hi").status_code == 403
    assert client.put(f"/chats/{path}/membership", headers=newbie).status_code == 403


def test_private_event_chat_follows_audience(client, alice, bob):
    carol = register(client, "carol@example.com", "Carol")
    ev = create(client, alice, audience="friends")
    path = f"userevent/{ev['id']}"
    assert client.get(f"/chats/{path}", headers=bob).status_code == 404
    assert say(client, bob, path, "can I come?").status_code == 404

    befriend(client, alice, bob, "bob")
    # friends of the host now see the event on their map and can talk about it
    pins = client.get("/userevents/private", headers=bob).json()["features"]
    assert [p["properties"]["user_event_id"] for p in pins] == [ev["id"]]
    assert say(client, bob, path, "count me in").status_code == 201
    assert client.get(f"/chats/{path}/messages", headers=carol).status_code == 404

    invite = create(client, alice, audience="invite", invited_user_ids=[3])
    assert say(client, carol, f"userevent/{invite['id']}", "thanks for the invite").status_code == 201
    assert say(client, bob, f"userevent/{invite['id']}", "me too?").status_code == 404

    # unfriended: the chat drops out of bob's list
    client.delete("/friends/2", headers=alice)
    assert client.get("/me/chats", headers=bob).json() == []


def test_follow_and_leave(client, alice, bob):
    ev = create(client, alice)
    path = f"event/{ev['event_id']}"
    say(client, alice, path, "before bob joined")
    r = client.put(f"/chats/{path}/membership", headers=bob)
    assert r.json()["joined"] is True and r.json()["unread"] == 0  # history isn't unread
    say(client, alice, path, "after")
    assert client.get("/me/chats", headers=bob).json()[0]["unread"] == 1
    assert client.delete(f"/chats/{path}/membership", headers=bob).status_code == 204
    assert client.get("/me/chats", headers=bob).json() == []


def test_delete_message(client, alice, bob):
    carol = register(client, "carol@example.com", "Carol")
    ev = create(client, alice)
    path = f"event/{ev['event_id']}"
    a = say(client, bob, path, "oops").json()
    b = say(client, bob, path, "spam").json()
    assert client.delete(f"/chats/messages/{a['id']}", headers=carol).status_code == 403
    assert client.delete(f"/chats/messages/{a['id']}", headers=bob).status_code == 204  # author
    assert client.delete(f"/chats/messages/{b['id']}", headers=alice).status_code == 204  # host
    msgs = client.get(f"/chats/{path}/messages", headers=carol).json()
    assert [(m["deleted"], m["body"]) for m in msgs] == [(True, None), (True, None)]


def test_rate_limit(client, alice):
    ev = create(client, alice)
    path = f"event/{ev['event_id']}"
    codes = [say(client, alice, path, f"m{i}").status_code for i in range(9)]
    assert codes[:8] == [201] * 8 and codes[8] == 429


def test_scraped_events_have_chats_too(client, alice, db):
    from app.models import Event, Source

    src = Source(slug="test-src", name="Test")
    ev = Event(
        source=src,
        external_key="x",
        title="Jazz at Pardon To Tu",
        categories=["music"],
        contact={},
        audience=[],
    )
    db.add(ev)
    db.commit()
    r = say(client, alice, f"event/{ev.id}", "who's going?")
    assert r.status_code == 201
    info = client.get(f"/chats/event/{ev.id}", headers=alice).json()
    assert info["title"] == "Jazz at Pardon To Tu" and info["host_user_id"] is None and info["joined"] is True
    assert client.get("/chats/event/999999", headers=alice).status_code == 404


def test_websocket_delivers_live(alice, bob):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:  # with: runs the lifespan, so the LISTEN task is up
        ev = create(c, alice)
        key = f"event:{ev['event_id']}"
        with c.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": bob["Authorization"].split()[1]})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "key": key})
            assert ws.receive_json() == {"type": "subscribed", "key": key}
            ws.send_json({"type": "subscribe", "key": "userevent:999"})
            assert ws.receive_json()["type"] == "error"
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}

            sent = say(c, alice, f"event/{ev['event_id']}", "live!").json()
            got = ws.receive_json()
            assert got["type"] == "message" and got["key"] == key and got["message"]["id"] == sent["id"]
            c.delete(f"/chats/messages/{sent['id']}", headers=alice)
            assert ws.receive_json() == {"type": "deleted", "key": key, "id": sent["id"]}


def test_websocket_rejects_bad_tokens(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "nope"})
        try:
            ws.receive_json()
            raise AssertionError("socket should be closed")
        except WebSocketDisconnect as e:
            assert e.code == 4401
