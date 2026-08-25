"""Add daily_logs.sources (per-field provenance)

Revision ID: add_daily_log_sources
Revises: add_activity_provenance
Create Date: 2026-08-24 00:00:00.000000

One nullable text column holding comma-separated ``field:owner`` pairs
("steps:garmin,weight:manual"). Same storage convention as ``feelings``,
deliberately, rather than making this the schema's first JSON column.

**Additive in meaning as well as in shape.** Every existing row gets NULL, and
NULL parses to an empty map, which ``app/provenance.py`` defines as "unknown".
Unknown is exactly the behaviour the app had before this column: an importer
may fill a NULL field and may never overwrite a filled one. So no stored value
changes meaning and no backfill is possible -- there is genuinely no way to know
who typed a number that predates the column, and guessing would be worse than
admitting it.

What the column buys is the ability for an importer to correct *its own*
values. Fill-blanks-only is the only safe rule without provenance, and it means
whatever first lands in a NULL column is frozen there forever -- including a
partial reading pulled while the day was still running. With provenance the
rule becomes "fill a blank, or update a value I wrote myself", and a bad
reading self-heals on the next pass.

Downgrade drops the column, which reverts every field to unknown. Nothing
breaks: an importer regains the right to fill blanks a user had deliberately
cleared, and the UI stops showing provenance badges. Re-upgrading starts the
record over from the next sync rather than restoring what was dropped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_daily_log_sources"
down_revision: str | None = "add_activity_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("daily_logs", sa.Column("sources", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_logs", "sources")
