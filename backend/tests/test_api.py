from app.ingest.run import load
from app.ingest.sources import SOURCES
from tests.conftest import fixture_records, register, soon

WARSAW_BBOX = "20.85,52.09,21.28,52.37"


def seed(db):
    for slug, spec in SOURCES.items():
        load(db, spec, spec.parse(fixture_records(slug)), None)
    db.commit()


def invite(client, headers, **kw):
    body = {
        "title": "Picnic in Pole Mokotowskie",
        "categories": ["meetups"],
        "starts_at": soon(1),
        "lat": 52.2128,
        "lng": 21.0019,
    } | kw
    r = client.post("/events", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_meta(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"
    cats = client.get("/categories").json()
    assert {"slug": "music", "label": "Music"} in cats


def test_anonymous_browse(client, db):
    seed(db)
    r = client.get(
        "/events", params={"bbox": WARSAW_BBOX, "from": "2026-01-01T00:00:00Z", "to": "2028-01-01T00:00:00Z"}
    )
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["features"]
    f = next(x for x in fc["features"] if x["properties"]["source"] == "warsaw_events")
    assert f["geometry"]["type"] == "Point" and "starts_at" in f["properties"]

    event = client.get(f"/events/{f['properties']['event_id']}", params={"past": True}).json()
    assert event["occurrences"] and event["source"] == "warsaw_events"

    sources = {s["slug"]: s for s in client.get("/sources").json()}
    assert sources["warsaw_pitches"]["item_count"] == len(fixture_records("warsaw_pitches"))

    places = client.get("/places").json()["features"]
    assert places and "opening_hours" in places[0]["properties"]

    assert client.get("/events", params={"bbox": "nope"}).status_code == 422


def test_filters(client, alice):
    invite(client, alice, title="Jazz koncert", categories=["music"])
    invite(client, alice, title="Morning yoga", categories=["yoga"])
    assert [
        f["properties"]["title"]
        for f in client.get("/events", params={"category": "yoga"}).json()["features"]
    ] == ["Morning yoga"]
    assert len(client.get("/events", params={"q": "jazz"}).json()["features"]) == 1
    now = client.get("/events/now", params={"lat": 52.2130, "lng": 21.0020}).json()["features"]
    assert len(now) == 2 and now[0]["properties"]["distance_m"] < 50


def test_auth_and_profile(client, alice):
    assert (
        client.post(
            "/auth/register",
            json={"email": "ALICE@example.com", "password": "password123", "display_name": "A2"},
        ).status_code
        == 409
    )
    assert (
        client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"}).status_code
        == 401
    )
    assert (
        client.post("/auth/login", json={"email": "alice@example.com", "password": "password123"}).status_code
        == 200
    )
    assert client.get("/me").status_code == 401

    r = client.patch(
        "/me",
        headers=alice,
        json={
            "bio": "new in town",
            "interests": ["music", "running"],
            "links": {"instagram": "https://instagram.com/alice"},
        },
    )
    assert r.status_code == 200 and r.json()["interests"] == ["music", "running"]
    public = client.get(f"/users/{r.json()['id']}").json()
    assert "email" not in public and "links" not in public
    assert client.patch("/me", headers=alice, json={"interests": ["not-a-category"]}).status_code == 422
    r = client.patch("/me", headers=alice, json={"bio": None, "display_name": None})
    assert r.json()["bio"] is None and r.json()["display_name"] == "Alice"  # bio cleared, name kept


def test_come_with_me_flow(client, alice, bob):
    carol = register(client, "carol@example.com", "Carol")
    client.patch("/me", headers=alice, json={"links": {"instagram": "https://instagram.com/alice"}})
    ev = invite(client, alice, capacity=1)
    occ_id = ev["occurrences"][0]["id"]
    alice_id = ev["host"]["id"]
    assert ev["occurrences"][0]["wanting_company"] == 1  # host auto-attends

    # Bob is going too and open to company
    r = client.put(
        f"/occurrences/{occ_id}/attendance", headers=bob, json={"wants_company": True, "max_group": 3}
    )
    assert r.status_code == 200
    going = client.get("/me/attending", headers=bob).json()
    assert [(g["occurrence_id"], g["title"]) for g in going] == [(occ_id, "Picnic in Pole Mokotowskie")]
    assert going[0]["starts_at"] and going[0]["event_id"] == ev["id"]
    attendees = client.get(
        f"/occurrences/{occ_id}/attendees", headers=carol, params={"wants_company": True}
    ).json()
    assert {a["user"]["display_name"] for a in attendees} == {"Alice", "Bob"}

    # Carol asks Alice (the host)
    r = client.post(
        f"/occurrences/{occ_id}/join-requests",
        headers=carol,
        json={"target_user_id": alice_id, "message": "Can I bring snacks?"},
    )
    assert r.status_code == 201, r.text
    req = r.json()
    assert "links" not in req["target"]
    assert (
        client.post(
            f"/occurrences/{occ_id}/join-requests", headers=carol, json={"target_user_id": alice_id}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/occurrences/{occ_id}/join-requests", headers=carol, json={"target_user_id": 999}
        ).status_code
        == 409
    )

    # Alice's swipe deck
    deck = client.get("/me/join-requests", headers=alice, params={"status": "pending"}).json()
    assert [d["id"] for d in deck] == [req["id"]]
    assert (
        client.patch(f"/join-requests/{req['id']}", headers=bob, json={"status": "accepted"}).status_code
        == 404
    )

    r = client.patch(f"/join-requests/{req['id']}", headers=alice, json={"status": "accepted"})
    assert r.status_code == 200
    assert r.json()["target"]["links"] == {"instagram": "https://instagram.com/alice"}
    assert client.get(f"/events/{ev['id']}").json()["seats_left"] == 0
    assert (
        client.patch(f"/join-requests/{req['id']}", headers=alice, json={"status": "rejected"}).status_code
        == 409
    )

    outgoing = client.get("/me/join-requests", headers=carol, params={"direction": "outgoing"}).json()
    assert outgoing[0]["status"] == "accepted"

    assert client.delete(f"/occurrences/{occ_id}/attendance", headers=bob).status_code == 204
    assert client.get(f"/events/{ev['id']}").json()["occurrences"][0]["attendees"] == 1


def test_busyareas_serves_the_committed_geojson():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/busyareas")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["features"]
    assert {f["properties"]["level"] for f in fc["features"]} <= {"busy", "very_busy"}


def test_amenities_are_opt_in_layers(client, db):
    seed(db)
    default = client.get("/places").json()["features"]
    assert default and not any({"toilets", "aed"} & set(f["properties"]["categories"]) for f in default)
    toilets = client.get("/places", params={"category": "toilets"}).json()["features"]
    assert len(toilets) == len(fixture_records("warsaw_toilets"))
    assert all(f["properties"]["categories"] == ["toilets"] for f in toilets)
    assert client.get("/places", params={"category": "aed"}).json()["features"]


def test_conditions_and_routes(client, db):
    from app.ingest.conditions import FEEDS, sync
    from app.ingest.routes import ROUTES
    from app.ingest.sources.warsaw_open_data import as_records

    for feed in [*FEEDS, ROUTES]:
        sync(db, feed, as_records(fixture_records(feed.slug)))
        sync(db, feed, as_records(fixture_records(feed.slug)))  # re-run upserts, no duplicates
    db.commit()

    c = client.get("/conditions").json()
    assert len(c["weather"]["features"]) == len(fixture_records("warsaw_weather"))
    assert len(c["air"]["features"]) == len(fixture_records("warsaw_air"))
    assert c["weather"]["features"][0]["geometry"]["type"] == "Point"

    r = client.get("/routes").json()["features"]
    assert len(r) == len(fixture_records("warsaw_routes")["result"])
    assert r[0]["geometry"]["type"] == "LineString" and len(r[0]["geometry"]["coordinates"]) > 1

    sources = {s["slug"]: s for s in client.get("/sources").json()}
    assert sources["warsaw_weather"]["last_status"] == "ok"


def test_personal_details_are_private(client, alice):
    r = client.patch("/me", headers=alice, json={"first_name": " Alicja ", "last_name": "Nowak", "age": 24})
    assert r.status_code == 200
    me = r.json()
    assert (me["first_name"], me["last_name"], me["age"]) == ("Alicja", "Nowak", 24)
    public = client.get(f"/users/{me['id']}").json()
    assert "first_name" not in public and "age" not in public
    assert client.patch("/me", headers=alice, json={"age": 7}).status_code == 422
    cleared = client.patch("/me", headers=alice, json={"first_name": "", "age": None}).json()
    assert cleared["first_name"] is None and cleared["age"] is None and cleared["last_name"] == "Nowak"
