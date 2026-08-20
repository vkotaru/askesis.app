"""Add activities.source + activities.external_id (importer provenance)

Revision ID: add_activity_provenance
Revises: add_password_changed_at
Create Date: 2026-08-19 00:00:00.000000

Additive: two nullable columns and one unique constraint over them.

NULL is the meaningful default. Every row that exists today was hand-entered,
and hand-entered rows carry no provider identity — so they stay NULL and the
constraint never applies to them. Both SQLite and Postgres treat NULLs as
distinct inside a UNIQUE constraint, which is exactly the behaviour wanted
here: any number of manual rows, but at most one row per
(account, provider, provider's id).

That constraint is what makes an importer re-runnable. Without it a poller that
re-reads the last 7 days every night inserts the same workout seven times, and
nothing in the schema objects.

`external_id` is a string, not an integer, even though Garmin's activityId is
numeric — a second provider will not agree about that, and the column costs
nothing as text.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_activity_provenance"
down_revision: str | None = "add_password_changed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activities", sa.Column("source", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "activities", sa.Column("external_id", sa.String(length=64), nullable=True)
    )
    # migrations/env.py sets render_as_batch globally, so this works on SQLite
    # (which cannot ALTER a table to add a constraint) as well as Postgres.
    with op.batch_alter_table("activities") as batch_op:
        batch_op.create_unique_constraint(
            "uq_activities_user_source_external", ["user_id", "source", "external_id"]
        )


def downgrade() -> None:
    # Drops only what this revision added. Any imported rows lose their
    # provenance and become indistinguishable from hand-entered ones — a
    # re-upgrade then re-imports them as new, so re-run the importer after
    # going back up rather than expecting the old links to return.
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("uq_activities_user_source_external", type_="unique")
    op.drop_column("activities", "external_id")
    op.drop_column("activities", "source")
