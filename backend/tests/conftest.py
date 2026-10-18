import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Must be set before app modules create the engine.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:54329/warszawa_test"
)
os.environ["REQUIRE_VERIFIED_EMAIL"] = "true"  # the gate is tested on; test_auth checks it off too

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
BACKEND = Path(__file__).parent.parent


def fixture_records(slug: str) -> list[dict]:
    return json.loads((FIXTURES / f"{slug}.json").read_text())


@pytest.fixture(scope="session")
def migrated():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated):
    from app import mail
    from app.routers import chats

    mail.outbox.clear()
    chats._recent.clear()  # chat rate limits are per process
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


def mailed_token(to: str, param: str = "verify") -> str:
    """The token in the latest mail sent to `to` (app.mail.outbox; nothing is really sent in tests)."""
    from app import mail

    sent = [m for m in mail.outbox if m.to == to]
    assert sent, f"no mail to {to}"
    return sent[-1].text.split(f"?{param}=")[1].split()[0]


def register(client, email: str, name: str, verify: bool = True) -> dict:
    r = client.post("/auth/register", json={"email": email, "password": "password123", "display_name": name})
    assert r.status_code == 201, r.text
    if verify:
        assert client.post("/auth/verify", json={"token": mailed_token(email)}).status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def alice(client):
    return register(client, "alice@example.com", "Alice")


@pytest.fixture
def bob(client):
    return register(client, "bob@example.com", "Bob")


def soon(hours: float = 1) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
