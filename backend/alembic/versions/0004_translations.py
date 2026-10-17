"""event translations (app/translate.py)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17 21:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("i18n", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "text_translations",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("orig", sa.String(length=8), nullable=False),
        sa.Column("pl", sa.Text(), nullable=False),
        sa.Column("en", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("text_translations")
    op.drop_column("events", "i18n")
