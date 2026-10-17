import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Must be set before app modules create the engine.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:54329/warszawa_test"
)

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


@pytest.fixture(scope="session", autouse=True)
def migrated():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated):
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


def register(client, email: str, name: str) -> dict:
    r = client.post("/auth/register", json={"email": email, "password": "password123", "display_name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def alice(client):
    return register(client, "alice@example.com", "Alice")


@pytest.fixture
def bob(client):
    return register(client, "bob@example.com", "Bob")


def soon(hours: float = 1) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
