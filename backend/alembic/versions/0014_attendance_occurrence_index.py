"""attendance: index on occurrence_id (attendee counts and lists, the ingest's attendance check)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-18 20:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_attendance_occurrence_id", "attendance", ["occurrence_id"])


def downgrade() -> None:
    op.drop_index("ix_attendance_occurrence_id", table_name="attendance")
