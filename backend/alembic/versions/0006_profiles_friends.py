"""profiles: @username, gender, hangouts; friendships

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 00:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=30), nullable=True))
    op.execute("UPDATE users SET username = 'user.' || id WHERE username IS NULL")  # existing accounts; they can change it
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.add_column("users", sa.Column("gender", sa.String(length=1), nullable=True))
    op.add_column("users", sa.Column("hangouts", postgresql.JSONB(), server_default="[]", nullable=False))

    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("addressee_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("requester_id <> addressee_id", name="ck_friendships_not_self"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["addressee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_friendships_requester_id", "friendships", ["requester_id"])
    op.create_index("ix_friendships_addressee_id", "friendships", ["addressee_id"])
    op.create_index(
        "ux_friendships_pair", "friendships",
        [sa.text("least(requester_id, addressee_id)"), sa.text("greatest(requester_id, addressee_id)")], unique=True,
    )


def downgrade() -> None:
    op.drop_table("friendships")
    op.drop_column("users", "hangouts")
    op.drop_column("users", "gender")
    op.drop_constraint("users_username_key", "users", type_="unique")
    op.drop_column("users", "username")
