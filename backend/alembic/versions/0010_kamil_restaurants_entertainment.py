"""Kamil's new raw tables: restaurants (OSM) and entertainment_events (Songkick, Waw4Free)

src/models.py defines them; 0007 only created the tables that existed when it ran, so environments
already past 0007 need this one. Created in this environment's schema only, like 0007.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18 03:10:00

"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = ("restaurants", "entertainment_events")


def kamil_tables() -> list[sa.Table]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for src/
    from src.models import Base

    return [t for t in Base.metadata.sorted_tables if t.name in NEW_TABLES]


def own_schema_tables(bind) -> set[str]:
    # not inspector.has_table: through the search_path it also sees public's tables from the dev box
    return set(bind.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")).scalars())


def upgrade() -> None:
    bind = op.get_bind()
    existing = own_schema_tables(bind)
    for table in kamil_tables():
        if table.name not in existing:  # a fresh database already got it from 0007
            table.create(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing = own_schema_tables(bind)
    for table in reversed(kamil_tables()):
        if table.name in existing:
            table.drop(bind, checkfirst=False)
