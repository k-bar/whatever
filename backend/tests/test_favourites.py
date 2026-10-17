from app.models import Event, Source
from tests.conftest import register


def venue(db, title: str) -> int:
    source = db.query(Source).filter_by(slug="test").one_or_none() or Source(slug="test", name="Test")
    event = Event(source=source, external_key=title, kind="place", title=title)
    db.add(event)
    db.commit()
    return event.id


def test_favourites_are_saved_with_the_account(client, db):
    me = register(client, "ola@example.com", "Ola")
    a, b = venue(db, "Hala Koszyki"), venue(db, "Bulwary Wiślane")
    assert client.get("/me/favourites", headers=me).json() == {"ids": []}

    r = client.put("/me/favourites", headers=me, json={"ids": [b, a, b, 999999]})
    assert r.status_code == 200, r.text
    assert r.json() == {"ids": [b, a]}  # order kept, duplicate and unknown id dropped
    assert client.get("/me/favourites", headers=me).json() == {"ids": [b, a]}
    assert client.get("/me", headers=me).json()["favourite_ids"] == [b, a]

    other = register(client, "kuba@example.com", "Kuba")
    assert client.get("/me/favourites", headers=other).json() == {"ids": []}  # per account


def test_favourites_need_a_login(client):
    assert client.get("/me/favourites").status_code == 401
    assert client.put("/me/favourites", json={"ids": []}).status_code == 401
