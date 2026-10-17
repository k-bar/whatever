"""users.favourite_ids: favourited events/venues saved with the account

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 22:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("favourite_ids", postgresql.ARRAY(sa.Integer()), server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "favourite_ids")
