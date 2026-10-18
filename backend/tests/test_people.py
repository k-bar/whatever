from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import User


def test_share_my_area(client, db, alice, bob):
    assert client.put("/me/area", json={"share": True}, headers=alice).status_code == 422  # where?
    r = client.put("/me/area", json={"share": True, "lat": 52.234567, "lng": 21.012345}, headers=alice)
    assert r.json()["share"] and (r.json()["lat"], r.json()["lng"]) == (
        52.235,
        21.012,
    )  # ~100 m, not the spot

    people = client.get("/people/sharing", headers=alice).json()
    assert [p["is_self"] for p in people] == [True]
    assert client.get("/people/sharing", headers=bob).json()[0]["is_self"] is False

    me = db.scalar(select(User).where(User.email == "alice@example.com"))
    me.area_at = datetime.now(UTC) - timedelta(hours=7)  # forgot the app open yesterday: stale
    db.commit()
    assert client.get("/people/sharing", headers=bob).json() == []

    client.put("/me/area", json={"share": True}, headers=alice)  # back, same place
    assert len(client.get("/people/sharing", headers=bob).json()) == 1
    client.put("/me/area", json={"share": False}, headers=alice)
    assert client.get("/people/sharing", headers=bob).json() == []
    assert client.get("/me/area", headers=alice).json()["share"] is False


def test_shared_areas_need_a_login(client, alice):
    client.put("/me/area", json={"share": True, "lat": 52.23, "lng": 21.01}, headers=alice)
    assert client.get("/people/sharing").status_code == 401  # a location is personal data: no anonymous map


def test_other_peoples_event_lists_stay_private(client, alice, bob):
    bob_id = client.get("/me", headers=bob).json()["id"]
    assert client.get(f"/users/{bob_id}/events?scope=going", headers=alice).status_code == 403
