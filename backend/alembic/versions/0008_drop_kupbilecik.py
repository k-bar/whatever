"""Kamil removed the kupbilecik source: drop kupbilecik_events, take its events off the map

kupbilecik.pl is no longer a source (src/ and backend/app/ingest/sources/). Its raw table goes, and the
events it loaded are marked inactive (kept, since people may attend them) instead of staying on the map
with no source refreshing them.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18 01:30:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # only in this environment's schema: through the search_path "dev, public" would also reach prod's table
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename = 'kupbilecik_events') THEN EXECUTE 'DROP TABLE kupbilecik_events'; END IF; END $$"
    )
    op.execute(
        "UPDATE events SET is_active = false WHERE source_id IN (SELECT id FROM sources WHERE slug = 'kupbilecik')"
    )
    op.execute("UPDATE sources SET last_status = 'removed', item_count = 0 WHERE slug = 'kupbilecik'")


def downgrade() -> None:
    pass  # the table was raw scraped data; the next src/ run would recreate it if the source came back
