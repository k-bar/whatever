"""Create or update a teammate's Postgres login that can do anything in the `dev` schema
and nothing in `public` (prod). Password comes from the user's secret (infra TeamStack).

Run with the master credentials (DB_SECRET_ARN), from a place that can reach RDS:
    DB_SECRET_ARN=... python scripts/create_dev_db_user.py warszawa-live/dev/db-users/kamil
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg import sql  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import read_secret  # noqa: E402
from app.db import engine  # noqa: E402

SCHEMA = "dev"


def main(secret_id: str) -> None:
    login = json.loads(read_secret(secret_id))
    user, password = login["username"], login["password"]
    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        master = conn.execute(text("SELECT current_user")).scalar()
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": user}).scalar()
        stmt = "ALTER ROLE {} WITH LOGIN PASSWORD {}" if exists else "CREATE ROLE {} WITH LOGIN PASSWORD {}"
        statements = [
            sql.SQL(stmt).format(sql.Identifier(user), sql.Literal(password)),
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)),
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(login.get("dbname", "warszawa")), sql.Identifier(user)
            ),
            # dev: full access to everything, now and in future
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), sql.Identifier(user)
            ),
            sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), sql.Identifier(user)
            ),
            sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), sql.Identifier(user)
            ),
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT ALL ON TABLES TO {}").format(
                sql.Identifier(master), sql.Identifier(SCHEMA), sql.Identifier(user)
            ),
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT ALL ON SEQUENCES TO {}").format(
                sql.Identifier(master), sql.Identifier(SCHEMA), sql.Identifier(user)
            ),
            # tables the teammate creates stay usable by the dev box (which runs as the master user)
            sql.SQL("GRANT {} TO {}").format(sql.Identifier(user), sql.Identifier(master)),
            # public schema = prod: PostGIS functions only, no prod tables (no table grants given)
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(user)),
            sql.SQL("ALTER ROLE {} SET search_path = {}, public").format(
                sql.Identifier(user), sql.Identifier(SCHEMA)
            ),
        ]
        for s in statements:
            raw.execute(s)
    print(f"role {user}: {'updated' if exists else 'created'} (all on schema {SCHEMA}, no prod tables)")


if __name__ == "__main__":
    main(sys.argv[1])
