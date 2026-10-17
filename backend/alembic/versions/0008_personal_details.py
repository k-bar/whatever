"""users: first name, last name, age (personal details like backend/db/people.db)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(40)))
    op.add_column("users", sa.Column("last_name", sa.String(60)))
    op.add_column("users", sa.Column("age", sa.SmallInteger()))


def downgrade() -> None:
    for column in ("age", "last_name", "first_name"):
        op.drop_column("users", column)
