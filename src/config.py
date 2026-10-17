"""Configuration loader for PostgreSQL (local / AWS RDS) and Warsaw API."""

from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import quote_plus
import os
import re

from sqlalchemy import Engine, create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
API_KEY_FILE = BASE_DIR / "apiKey.txt"
DANE_FILE = BASE_DIR / "dane.txt"

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres@localhost:54329/warszawa"
SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def get_db_schema(env: Optional[Mapping[str, str]] = None) -> str:
    """Read and validate PostgreSQL target schema from DB_SCHEMA."""
    environ = env if env is not None else os.environ
    schema = (environ.get("DB_SCHEMA") or "public").strip()
    if not SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError(f"Invalid DB_SCHEMA identifier: {schema!r}")
    return schema


def get_database_url(env: Optional[Mapping[str, str]] = None) -> str:
    """Build PostgreSQL URL from DATABASE_URL, AWS RDS DB_* vars, or local."""
    environ = env if env is not None else os.environ

    direct_url = environ.get("DATABASE_URL")
    if direct_url:
        return direct_url.strip()

    db_host = environ.get("DB_HOST")
    if db_host:
        host = db_host.strip()
        port = environ.get("DB_PORT", "5432").strip()
        name = environ.get("DB_NAME", "warszawa_live").strip()
        user = quote_plus(environ.get("DB_USER", "warszawa").strip())
        password = quote_plus(environ.get("DB_PASSWORD", "").strip())
        default_ssl = (
            "disable" if host in ("localhost", "127.0.0.1") else "require"
        )
        sslmode = environ.get("DB_SSLMODE", default_ssl).strip()
        base = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
        if sslmode:
            return f"{base}?sslmode={quote_plus(sslmode)}"
        return base

    return DEFAULT_DATABASE_URL


def create_db_engine(
    db_url: Optional[str] = None,
    schema: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Engine:
    """Create SQLAlchemy Engine configured with DB_SCHEMA search_path."""
    resolved_url = db_url or get_database_url(env=env)
    resolved_schema = schema or get_db_schema(env=env)
    return create_engine(
        resolved_url,
        connect_args={"options": f"-csearch_path={resolved_schema},public"},
    )


def get_api_token(
    api_key_path: Path = API_KEY_FILE,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """Read Warsaw Open Data API token from env or apiKey.txt."""
    environ = env if env is not None else os.environ
    env_token = (
        environ.get("WARSZAWA_API_TOKEN")
        or environ.get("WARSAW_API_TOKEN")
    )
    if env_token:
        return env_token.strip()
    if not api_key_path.exists():
        raise FileNotFoundError(
            f"API key file not found at {api_key_path}"
        )
    token = api_key_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"API key file {api_key_path} is empty")
    return token
