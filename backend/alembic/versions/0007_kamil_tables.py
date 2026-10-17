"""Kamil's raw Open Data tables (src/models.py); tourist_routes takes his shape

Kamil owns these tables: src/models.py is the definition, this migration only creates them in
this environment's schema (search_path is "<DB_SCHEMA>, public"), so src/ never lands in public
by accident. tourist_routes switches from path/points to his traces/tourist_points columns.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 23:30:00

"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def kamil_tables() -> list[sa.Table]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for src/
    from src.models import Base

    return [t for t in Base.metadata.sorted_tables if t.name != "tourist_routes"]


def own_schema_tables(bind) -> set[str]:
    # not inspector.has_table: through the search_path it also sees public's tables from the dev box
    return set(bind.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")).scalars())


def upgrade() -> None:
    # the rows are refilled by the next ingest run (app/ingest/routes.py or src/)
    op.execute("DELETE FROM tourist_routes")
    op.drop_column("tourist_routes", "path")
    op.drop_column("tourist_routes", "points")
    op.alter_column("tourist_routes", "title", type_=sa.String(length=255), existing_nullable=False)
    op.add_column("tourist_routes", sa.Column("traces", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "tourist_routes", sa.Column("tourist_points", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )

    bind = op.get_bind()
    existing = own_schema_tables(bind)
    for table in kamil_tables():
        if table.name not in existing:
            table.create(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing = own_schema_tables(bind)
    for table in reversed(kamil_tables()):
        if table.name in existing:
            table.drop(bind, checkfirst=False)

    op.execute("DELETE FROM tourist_routes")
    op.drop_column("tourist_routes", "tourist_points")
    op.drop_column("tourist_routes", "traces")
    op.alter_column("tourist_routes", "title", type_=sa.String(length=200), existing_nullable=False)
    op.add_column(
        "tourist_routes",
        sa.Column("points", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.add_column(
        "tourist_routes",
        sa.Column(
            "path",
            geoalchemy2.types.Geography(
                geometry_type="LINESTRING", srid=4326, dimension=2, spatial_index=False, name="geography"
            ),
            nullable=False,
        ),
    )
