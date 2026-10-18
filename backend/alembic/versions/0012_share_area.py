"""users: "share my area" (an approximate location shown to others as a pulsing pin) + demo-account flag

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-18 18:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("share_area", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("area_lat", sa.Float()))
    op.add_column("users", sa.Column("area_lng", sa.Float()))
    op.add_column("users", sa.Column("area_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_share_area", "users", ["share_area"], postgresql_where=sa.text("share_area"))


def downgrade() -> None:
    op.drop_index("ix_users_share_area", table_name="users")
    for column in ("is_mock", "area_at", "area_lng", "area_lat", "share_area"):
        op.drop_column("users", column)
