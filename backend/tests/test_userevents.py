import base64
from datetime import UTC, datetime, timedelta

from tests.conftest import register

# 1x1 transparent PNG
PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )
).decode()


def new_event(**over) -> dict:
    starts = datetime.now(UTC) + timedelta(days=1)
    body = {
        "title": "Sunday run along the Vistula",
        "subtitle": "Easy 5k, all paces",
        "description": "Meet at the boulevards, coffee after.",
        "event_type": "run",
        "audience": "public",
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=1)).isoformat(),
        "lat": 52.2409,
        "lng": 21.0302,
        "venue_name": "Bulwary Wiślane",
    }
    return body | over


def test_guest_session_can_create(client):
    r = client.post("/auth/guest", json={})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["display_name"] == "Guest"


def test_public_event_goes_onto_syrenka_users(client):
    host = register(client, "ola@example.com", "Ola")
    r = client.post("/userevents", json=new_event(), headers=host)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["event"]["category"] == "running"
    assert created["event"]["event_id"] is not None
    f = created["feature"]
    assert f["properties"]["subtitle"] == "Easy 5k, all paces"
    assert f["properties"]["host"]["display_name"] == "Ola"
    assert f["properties"]["source"] == "syrenka-users"
    assert f["properties"]["is_public_invite"] is True

    # everyone's map: GET /events (no login), the Syrenka Users API and the sources list
    events = client.get("/events").json()["features"]
    mine = [e for e in events if e["properties"].get("user_event_id") == created["event"]["id"]]
    assert len(mine) == 1 and mine[0]["properties"]["audience"] == "public"
    assert len(client.get("/userevents/public").json()["features"]) == 1
    sources = {s["slug"]: s for s in client.get("/sources").json()}
    assert sources["syrenka-users"]["name"] == "Syrenka Users"
    assert sources["syrenka-users"]["item_count"] == 1

    # the host counts as going and open to company, so join requests work
    occ = f["properties"]["occurrence_id"]
    guest = register(client, "kamil@example.com", "Kamil")
    r = client.post(
        f"/occurrences/{occ}/join-requests", json={"target_user_id": 1, "message": "hi"}, headers=guest
    )
    assert r.status_code == 201, r.text


def test_private_audiences_stay_off_the_public_map(client):
    host = register(client, "ola@example.com", "Ola")
    friend = register(client, "kamil@example.com", "Kamil")
    stranger = register(client, "tomek@example.com", "Tomek")
    r = client.post("/userevents", json=new_event(audience="invite", invited_user_ids=[2]), headers=host)
    assert r.status_code == 201, r.text
    assert r.json()["event"]["event_id"] is None
    assert r.json()["feature"]["properties"]["event_id"].startswith("ue-")

    assert client.get("/events").json()["features"] == []
    assert client.get("/userevents/public").json()["features"] == []
    assert len(client.get("/userevents/private", headers=host).json()["features"]) == 1
    assert len(client.get("/userevents/private", headers=friend).json()["features"]) == 1
    assert client.get("/userevents/private", headers=stranger).json()["features"] == []


def test_photo_upload_and_cancel(client):
    host = register(client, "ola@example.com", "Ola")
    r = client.post("/userevents/photos", json={"data_url": f"data:image/png;base64,{PNG}"}, headers=host)
    assert r.status_code == 201, r.text
    photo = r.json()
    img = client.get(photo["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"

    r = client.post("/userevents", json=new_event(photo_id=photo["id"]), headers=host)
    created = r.json()
    assert created["feature"]["properties"]["image_url"] == photo["url"]

    other = register(client, "kamil@example.com", "Kamil")
    assert client.delete(f"/userevents/{created['event']['id']}", headers=other).status_code == 404
    assert client.delete(f"/userevents/{created['event']['id']}", headers=host).status_code == 204
    assert client.get("/events").json()["features"] == []
    assert client.get("/userevents/mine", headers=host).json()[0]["status"] == "cancelled"


def test_validation(client):
    host = register(client, "ola@example.com", "Ola")
    assert client.post("/userevents", json=new_event(), headers={}).status_code == 401
    assert client.post("/userevents", json=new_event(event_type="rave"), headers=host).status_code == 422
    assert client.post("/userevents", json=new_event(audience="everyone"), headers=host).status_code == 422
    bad_end = new_event(ends_at=(datetime.now(UTC) - timedelta(days=1)).isoformat())
    assert client.post("/userevents", json=bad_end, headers=host).status_code == 422
    r = client.post("/userevents/photos", json={"data_url": "data:text/plain;base64,aGVsbG8="}, headers=host)
    assert r.status_code == 415
