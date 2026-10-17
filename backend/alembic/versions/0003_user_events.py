"""user events (app/userevents)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 19:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_event_photos",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("venue_name", sa.String(length=200), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("photo_id", sa.String(length=32), nullable=True),
        sa.Column("invited_user_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["user_event_photos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_events_host_user_id", "user_events", ["host_user_id"])
    op.create_index("ix_user_events_starts_at", "user_events", ["starts_at"])


def downgrade() -> None:
    op.drop_index("ix_user_events_starts_at", table_name="user_events")
    op.drop_index("ix_user_events_host_user_id", table_name="user_events")
    op.drop_table("user_events")
    op.drop_table("user_event_photos")
