from datetime import UTC, datetime, timedelta

import jwt

from app import mail
from app.config import settings
from app.models import ChatMessage, Event, User
from tests.conftest import mailed_token, register
from tests.test_api import invite
from tests.test_chats import befriend, create, say

PW = "password123"


def login(client, email, password=PW):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(r) -> dict:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_register_mails_link_and_gates_social(client):
    h = register(client, "ola@example.com", "Ola", verify=False)
    me = client.get("/me", headers=h).json()
    assert me["email_verified"] is False
    assert [m.subject for m in mail.outbox] == ["Confirm your email for Syrenka"]
    assert f"{settings.web_url}/?verify=" in mail.outbox[0].text and "Confirm email" in mail.outbox[0].html

    register(client, "kuba@example.com", "Kuba")
    r = client.post("/friends/requests", json={"username": "kuba"}, headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "Confirm your email first"

    r = client.post("/auth/verify", json={"token": mailed_token("ola@example.com")})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert client.post("/friends/requests", json={"username": "kuba"}, headers=h).status_code == 201
    # the link can be clicked again (mail clients prefetch links): still fine
    assert client.post("/auth/verify", json={"token": mailed_token("ola@example.com")}).status_code == 200


def test_verification_can_be_optional(client):
    settings.require_verified_email = False
    try:
        h = register(client, "ola@example.com", "Ola", verify=False)
        me = client.get("/me", headers=h).json()
        assert me["email_verified"] is False and me["verify_required"] is False
        assert len(mail.outbox) == 1  # the link is still mailed
        register(client, "kuba@example.com", "Kuba")
        assert client.post("/friends/requests", json={"username": "kuba"}, headers=h).status_code == 201
        ev = create(client, h)
        assert say(client, h, f"event/{ev['event_id']}", "hi").status_code == 201
    finally:
        settings.require_verified_email = True
    assert client.get("/me", headers=h).json()["verify_required"] is True
    assert client.post("/friends/requests", json={"username": "kuba"}, headers=h).status_code == 403


def test_password_is_salted_argon2(client, db):
    register(client, "a@example.com", "A")
    register(client, "b@example.com", "B")
    hashes = [u.password_hash for u in db.query(User).order_by(User.id)]
    assert all(h.startswith("$argon2id$") for h in hashes)
    assert hashes[0] != hashes[1]  # same password, different salt
    assert PW not in hashes[0]


def test_bad_verify_tokens(client, alice):
    assert client.post("/auth/verify", json={"token": "nope"}).status_code == 400
    # a login token is not a verification link, and a verify link is not a login
    login_token = alice["Authorization"].split()[1]
    assert client.post("/auth/verify", json={"token": login_token}).status_code == 400
    verify_token = mailed_token("alice@example.com")
    assert client.get("/me", headers={"Authorization": f"Bearer {verify_token}"}).status_code == 401
    expired = jwt.encode(
        {
            **jwt.decode(verify_token, options={"verify_signature": False}),
            "exp": datetime.now(UTC) - timedelta(1),
        },
        settings.jwt_secret,
    )
    assert client.post("/auth/verify", json={"token": expired}).status_code == 400


def test_resend_is_throttled(client):
    h = register(client, "ola@example.com", "Ola", verify=False)
    assert client.post("/auth/verify/resend", headers=h).status_code == 429  # register just sent one
    settings.mail_resend_seconds, old = 0, settings.mail_resend_seconds
    try:
        assert client.post("/auth/verify/resend", headers=h).status_code == 202
    finally:
        settings.mail_resend_seconds = old
    assert len(mail.outbox) == 2
    client.post("/auth/verify", json={"token": mailed_token("ola@example.com")})
    assert client.post("/auth/verify/resend", headers=h).status_code == 409


def test_forgot_and_reset_password(client, alice):
    r = client.post("/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 202 and not [m for m in mail.outbox if m.to == "nobody@example.com"]
    settings.mail_resend_seconds, old = 0, settings.mail_resend_seconds
    try:
        assert client.post("/auth/password/forgot", json={"email": "ALICE@example.com"}).status_code == 202
    finally:
        settings.mail_resend_seconds = old
    token = mailed_token("alice@example.com", "reset")
    r = client.post("/auth/password/reset", json={"token": token, "password": "new-password-1"})
    assert r.status_code == 200
    assert client.get("/me", headers=bearer(r)).status_code == 200
    assert client.get("/me", headers=alice).status_code == 401  # old sessions ended
    assert login(client, "alice@example.com").status_code == 401
    assert login(client, "alice@example.com", "new-password-1").status_code == 200
    # one use only: the link is bound to the old password hash
    again = client.post("/auth/password/reset", json={"token": token, "password": "another-pass"})
    assert again.status_code == 400


def test_change_password_and_logout_all(client, alice):
    r = client.post(
        "/me/password", json={"current_password": "wrong", "new_password": "new-password-1"}, headers=alice
    )
    assert r.status_code == 403
    r = client.post("/me/password", json={"current_password": PW, "new_password": "short"}, headers=alice)
    assert r.status_code == 422
    r = client.post(
        "/me/password", json={"current_password": PW, "new_password": "new-password-1"}, headers=alice
    )
    assert r.status_code == 200
    fresh = bearer(r)
    assert client.get("/me", headers=alice).status_code == 401
    assert client.get("/me", headers=fresh).status_code == 200

    r = client.post("/auth/logout-all", headers=fresh)
    assert client.get("/me", headers=fresh).status_code == 401
    assert client.get("/me", headers=bearer(r)).status_code == 200


def test_change_email_needs_new_verification(client, alice, bob):
    body = {"email": "bob@example.com", "password": PW}
    assert client.post("/me/email", json=body, headers=alice).status_code == 409
    body = {"email": "alice@new.example.com", "password": "wrong"}
    assert client.post("/me/email", json=body, headers=alice).status_code == 403
    r = client.post("/me/email", json={**body, "password": PW}, headers=alice)
    assert r.status_code == 200 and r.json()["email_verified"] is False
    # a link mailed to the old address no longer confirms the account
    old = mailed_token("alice@example.com")
    assert client.post("/auth/verify", json={"token": old}).status_code == 400
    assert (
        client.post("/auth/verify", json={"token": mailed_token("alice@new.example.com")}).status_code == 200
    )
    assert login(client, "alice@new.example.com").status_code == 200


def test_login_lockout(client, alice):
    settings.login_max_failures, old = 3, settings.login_max_failures
    try:
        for _ in range(3):
            assert login(client, "alice@example.com", "wrong-pass").status_code == 401
        r = login(client, "alice@example.com")
        assert r.status_code == 429 and "Try again" in r.json()["detail"]
    finally:
        settings.login_max_failures = old
    # a reset unlocks the account
    settings.mail_resend_seconds, old = 0, settings.mail_resend_seconds
    try:
        client.post("/auth/password/forgot", json={"email": "alice@example.com"})
    finally:
        settings.mail_resend_seconds = old
    token = mailed_token("alice@example.com", "reset")
    assert (
        client.post("/auth/password/reset", json={"token": token, "password": "new-password-1"}).status_code
        == 200
    )
    assert login(client, "alice@example.com", "new-password-1").status_code == 200


def test_unknown_email_and_wrong_password_look_the_same(client, alice):
    a = login(client, "nobody@example.com")
    b = login(client, "alice@example.com", "wrong-pass")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_delete_account(client, db, alice, bob):
    befriend(client, alice, bob, "bob")
    ue = create(client, alice)  # a user event, published as a public event
    hosted = invite(client, alice)  # a public invite
    bobs_event = create(client, bob, title="Bob's picnic")
    path = f"event/{bobs_event['event_id']}"
    assert say(client, alice, path, "I'll bring cake").status_code == 201
    assert say(client, bob, path, "Great").status_code == 201

    assert client.request("DELETE", "/me", json={"password": "wrong"}, headers=alice).status_code == 403
    r = client.request("DELETE", "/me", json={"password": PW}, headers=alice)
    assert r.status_code == 204
    db.expire_all()

    assert db.query(User).filter_by(email="alice@example.com").first() is None
    assert client.get("/me", headers=alice).status_code == 401
    assert login(client, "alice@example.com").status_code == 401
    # what she hosted leaves the map, without a host
    for event_id in (ue["event_id"], hosted["id"]):
        ev = db.get(Event, event_id)
        assert ev.is_active is False and ev.host_user_id is None
    # her messages and friendship are gone; Bob's event and chat stay
    assert [m.body for m in db.query(ChatMessage)] == ["Great"]
    bob_id = client.get("/me", headers=bob).json()["id"]
    assert client.get(f"/users/{bob_id}/friends", headers=bob).json() == []
    assert client.get(f"/chats/{path}/messages", headers=bob).status_code == 200
    # the address can sign up again
    register(client, "alice@example.com", "Alice")
