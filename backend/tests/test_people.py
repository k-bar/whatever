from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app import mocksocial
from app.ingest.run import load
from app.ingest.sources import SOURCES
from app.models import Attendance, Friendship, JoinRequest, Occurrence, User
from app.routers.profiles import friend_ids
from app.userevents.models import UserEvent
from tests.test_ingest import raw


def iso(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def catalogue(db):
    """12 concerts that are over and 12 coming up."""
    past = [raw(f"p{i}", starts=(iso(-2 - i),)) for i in range(12)]
    future = [raw(f"f{i}", starts=(iso(2 + i),)) for i in range(12)]
    load(db, SOURCES["warsaw_events"], past + future, None)
    db.commit()


def counts(db, user_id: int) -> tuple[int, int]:
    now = datetime.now(UTC)
    rows = db.execute(
        select(Occurrence.starts_at)
        .join(Attendance, Attendance.occurrence_id == Occurrence.id)
        .join(UserEvent, UserEvent.event_id == Occurrence.event_id, isouter=True)
        .where(Attendance.user_id == user_id, UserEvent.id.is_(None))  # catalogue only, not their own invite
    ).all()
    return sum(s < now for (s,) in rows), sum(s >= now for (s,) in rows)


def test_demo_people(db, client):
    catalogue(db)
    out = mocksocial.run(db)
    assert out["people"] == 30
    assert 3 <= out["friends_min"] and out["friends_max"] <= 20

    users = db.scalars(select(User).where(User.is_mock).order_by(User.id)).all()
    assert [u.username for u in users[:3]] == ["agnieszk.w", "macie_k", "zbysz37"]
    now = datetime.now(UTC)
    for u in users:
        assert 3 <= len(friend_ids(db, u.id)) <= 20
        been, going = counts(db, u.id)
        assert 1 <= been <= 3 and 1 <= going <= 3, (u.username, been, going)
        hosted = db.scalars(select(UserEvent).where(UserEvent.host_user_id == u.id)).all()
        assert len(hosted) == 1 and hosted[0].audience == "public_confirm" and hosted[0].starts_at > now
        asks = db.scalars(select(JoinRequest).where(JoinRequest.target_user_id == u.id)).all()
        assert any(j.status == "accepted" for j in asks)
        assert all(j.requester_id in friend_ids(db, u.id) for j in asks)
        assert u.share_area and u.photos == ["/people/avatar.svg"]

    # safe to re-run: nothing doubles
    before = [
        db.scalar(select(func.count()).select_from(t))
        for t in (User, Friendship, UserEvent, JoinRequest, Attendance)
    ]
    mocksocial.run(db)
    after = [
        db.scalar(select(func.count()).select_from(t))
        for t in (User, Friendship, UserEvent, JoinRequest, Attendance)
    ]
    assert before == after

    # their pins, and their open profiles
    people = client.get("/people/sharing").json()
    assert len(people) == 30 and all(p["hosting"] for p in people)
    first = people[0]
    profile = client.get(f"/users/{first['id']}/profile").json()
    assert profile["can_see_events"] and profile["stats"]["hosted"] == 1
    assert client.get(f"/users/{first['id']}/events?scope=been").status_code == 200
    assert client.get("/people/avatar.svg").headers["content-type"].startswith("image/svg")


def test_hosted_invitation_moves_on_once_over(db):
    mocksocial.run(db)
    ue = db.scalar(select(UserEvent).order_by(UserEvent.id))
    ue.starts_at, ue.ends_at = (
        datetime.now(UTC) - timedelta(days=2),
        datetime.now(UTC) - timedelta(days=2, hours=-2),
    )
    db.commit()
    mocksocial.run(db)
    db.refresh(ue)
    assert ue.starts_at > datetime.now(UTC)
    assert db.scalar(select(Occurrence.starts_at).where(Occurrence.event_id == ue.event_id)) == ue.starts_at


def test_share_my_area(client, db, alice):
    assert client.put("/me/area", json={"share": True}, headers=alice).status_code == 422  # where?
    r = client.put("/me/area", json={"share": True, "lat": 52.234567, "lng": 21.012345}, headers=alice)
    assert r.json()["share"] and (r.json()["lat"], r.json()["lng"]) == (
        52.235,
        21.012,
    )  # ~100 m, not the spot

    people = client.get("/people/sharing", headers=alice).json()
    assert [p["is_self"] for p in people] == [True]
    assert client.get("/people/sharing").json()[0]["is_self"] is False

    me = db.scalar(select(User).where(User.email == "alice@example.com"))
    me.area_at = datetime.now(UTC) - timedelta(hours=7)  # forgot the app open yesterday: stale
    db.commit()
    assert client.get("/people/sharing").json() == []

    client.put("/me/area", json={"share": True}, headers=alice)  # back, same place
    assert len(client.get("/people/sharing").json()) == 1
    client.put("/me/area", json={"share": False}, headers=alice)
    assert client.get("/people/sharing").json() == []
    assert client.get("/me/area", headers=alice).json()["share"] is False


def test_demo_profiles_are_open_but_real_ones_are_not(client, db, alice, bob):
    mocksocial.run(db)
    bob_id = client.get("/me", headers=bob).json()["id"]
    assert client.get(f"/users/{bob_id}/events?scope=going", headers=alice).status_code == 403
    demo = db.scalar(select(User.id).where(User.is_mock))
    assert client.get(f"/users/{demo}/friends", headers=alice).status_code == 200
