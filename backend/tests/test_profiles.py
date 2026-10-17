from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ingest.run import load
from app.ingest.sources import SOURCES
from app.models import Event, Occurrence
from tests.conftest import register
from tests.test_ingest import raw
from tests.test_userevents import new_event


def me(client, auth):
    return client.get("/me", headers=auth).json()


# --- @usernames -------------------------------------------------------------------------------------


def test_new_accounts_get_a_username_from_their_name(client):
    a = register(client, "lucja@example.com", "Łucja Kowalska")
    b = register(client, "lucja2@example.com", "Łucja Kowalska")
    assert me(client, a)["username"] == "lucja.kowalska"
    assert me(client, b)["username"] == "lucja.kowalska.2"


def test_choose_and_change_username(client, alice, bob):
    r = client.post(
        "/auth/register",
        json={
            "email": "c@example.com",
            "password": "password123",
            "display_name": "C",
            "username": "@Spatif.Fan",
        },
    )
    assert r.status_code == 201
    assert client.get("/profiles/spatif.fan").json()["display_name"] == "C"

    assert (
        client.post(
            "/auth/register",
            json={
                "email": "d@example.com",
                "password": "password123",
                "display_name": "D",
                "username": "spatif.fan",
            },
        ).status_code
        == 409
    )
    assert client.patch("/me", json={"username": "spatif.fan"}, headers=alice).status_code == 409
    assert client.patch("/me", json={"username": ".bad..name"}, headers=alice).status_code == 422
    assert client.patch("/me", json={"username": "admin"}, headers=alice).status_code == 422

    assert client.patch("/me", json={"username": "Ola_W"}, headers=alice).json()["username"] == "ola_w"
    # the old name is free again; your own name counts as available to you
    assert client.get("/usernames/alice/available").json()["available"] is True
    assert client.get("/usernames/ola_w/available", headers=alice).json()["available"] is True
    check = client.get("/usernames/ola_w/available", headers=bob).json()
    assert check == {"username": "ola_w", "available": False, "reason": "Username taken"}


def test_gender_and_hangouts(client, alice):
    r = client.patch(
        "/me",
        json={"gender": "f", "hangouts": [{"name": "Spatif"}, {"name": "Hala Koszyki", "place_id": None}]},
        headers=alice,
    )
    assert r.status_code == 200
    assert r.json()["gender"] == "f" and [h["name"] for h in r.json()["hangouts"]] == [
        "Spatif",
        "Hala Koszyki",
    ]
    assert client.patch("/me", json={"gender": ""}, headers=alice).json()["gender"] is None
    assert (
        client.patch(
            "/me", json={"hangouts": [{"name": f"P{i}"} for i in range(6)]}, headers=alice
        ).status_code
        == 422
    )


def test_profile_picture_from_an_upload(client, alice):
    from tests.test_userevents import PNG

    photo = client.post(
        "/userevents/photos", json={"data_url": f"data:image/png;base64,{PNG}"}, headers=alice
    ).json()
    r = client.patch("/me", json={"photos": [photo["url"]]}, headers=alice)
    assert r.status_code == 200 and r.json()["photos"] == [photo["url"]]
    assert client.get(photo["url"]).status_code == 200
    assert client.patch("/me", json={"photos": ["/etc/passwd"]}, headers=alice).status_code == 422
    assert (
        client.patch("/me", json={"photos": ["https://example.com/me.jpg"]}, headers=alice).status_code == 200
    )
    assert client.patch("/me", json={"photos": []}, headers=alice).json()["photos"] == []


# --- friends ----------------------------------------------------------------------------------------


def test_friend_request_accept_and_unfriend(client, alice, bob):
    bob_id, alice_id = me(client, bob)["id"], me(client, alice)["id"]
    r = client.post("/friends/requests", json={"username": "bob"}, headers=alice)
    assert r.status_code == 201 and r.json()["direction"] == "outgoing" and r.json()["status"] == "pending"
    assert client.get(f"/users/{bob_id}/profile", headers=alice).json()["relation"] == "request_sent"
    assert client.get(f"/users/{alice_id}/profile", headers=bob).json()["relation"] == "request_received"

    incoming = client.get("/me/friend-requests", headers=bob).json()
    assert [x["user"]["username"] for x in incoming] == ["alice"]
    assert (
        client.patch(
            f"/friend-requests/{incoming[0]['id']}", json={"status": "accepted"}, headers=alice
        ).status_code
        == 404
    )  # not hers to answer
    assert (
        client.patch(
            f"/friend-requests/{incoming[0]['id']}", json={"status": "accepted"}, headers=bob
        ).json()["status"]
        == "accepted"
    )

    p = client.get(f"/users/{bob_id}/profile", headers=alice).json()
    assert p["relation"] == "friends" and p["can_see_events"] is True and p["stats"]["friends"] == 1
    assert [u["username"] for u in client.get(f"/users/{alice_id}/friends", headers=bob).json()] == ["bob"]

    assert client.delete(f"/friends/{alice_id}", headers=bob).status_code == 204
    assert client.get(f"/users/{bob_id}/profile", headers=alice).json()["stats"]["friends"] == 0


def test_asking_back_accepts_and_declining_lets_them_ask_again(client, alice, bob):
    client.post("/friends/requests", json={"username": "bob"}, headers=alice)
    r = client.post("/friends/requests", json={"username": "alice"}, headers=bob)
    assert r.json()["status"] == "accepted"

    carol = register(client, "carol@example.com", "Carol")
    req = client.post("/friends/requests", json={"username": "carol"}, headers=alice).json()
    assert (
        client.patch(f"/friend-requests/{req['id']}", json={"status": "declined"}, headers=carol).status_code
        == 200
    )
    assert client.get("/me/friend-requests", headers=carol).json() == []
    assert client.post("/friends/requests", json={"username": "carol"}, headers=alice).status_code == 201
    assert client.post("/friends/requests", json={"username": "alice"}, headers=alice).status_code == 422


def test_people_search(client, alice, bob):
    register(client, "bobby@example.com", "Robert")
    names = [u["username"] for u in client.get("/people/search?q=bo", headers=alice).json()]
    assert names[:2] == ["bob", "robert"] or set(names) >= {"bob"}
    assert "alice" not in [u["username"] for u in client.get("/people/search?q=ali", headers=alice).json()]


# --- going / been to / hosting + stats ---------------------------------------------------------------


def test_events_lists_and_stats(client, db, alice, bob):
    now = datetime.now(UTC)
    load(
        db,
        SOURCES["warsaw_events"],
        [
            raw("past", starts=((now - timedelta(days=3)).isoformat(),)),
            raw("future", starts=((now + timedelta(days=3)).isoformat(),)),
        ],
        None,
    )
    db.commit()
    occ = {e.external_key: o.id for e, o in db.execute(select(Event, Occurrence).join(Occurrence))}
    for key in ("past", "future"):
        assert client.put(f"/occurrences/{occ[key]}/attendance", json={}, headers=alice).status_code == 200
    assert client.post("/userevents", json=new_event(), headers=alice).status_code == 201

    alice_id = me(client, alice)["id"]
    own = client.get(f"/users/{alice_id}/profile", headers=alice).json()
    assert own["stats"] == {"friends": 0, "been_to": 1, "hosted": 1}
    assert [
        e["title"] for e in client.get(f"/users/{alice_id}/events?scope=going", headers=alice).json()
    ] == ["Koncert future"]
    assert [e["title"] for e in client.get(f"/users/{alice_id}/events?scope=been", headers=alice).json()] == [
        "Koncert past"
    ]
    hosting = client.get(f"/users/{alice_id}/events?scope=hosting", headers=alice).json()
    assert [e["title"] for e in hosting] == ["Sunday run along the Vistula"] and hosting[0]["user_event_id"]

    # strangers see the numbers, not the lists
    stranger = client.get(f"/users/{alice_id}/profile", headers=bob).json()
    assert stranger["stats"]["been_to"] == 1 and stranger["can_see_events"] is False
    assert client.get(f"/users/{alice_id}/events?scope=going", headers=bob).status_code == 403
    assert client.get(f"/users/{alice_id}/events?scope=going").status_code == 403
