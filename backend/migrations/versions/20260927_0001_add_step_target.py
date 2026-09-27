"""Add user_settings.step_target

Revision ID: add_step_target
Revises: add_routine_exercises
Create Date: 2026-09-27 00:00:00.000000

A daily step goal, drawn as a target line on the dashboard's steps chart.
No unit conversion: a step is a step.

Hand-written, like every migration in this repo, and now for a better reason
than habit. `./db.sh new` was producing a migration that dropped the whole
schema (migrations/env.py never imported app.models, so the metadata alembic
compared against was empty); with that fixed, autogenerate produces a correct
`step_target` column buried in a dozen unrelated changes it also wants to make
-- including dropping the Google columns that CLAUDE.md says stay until their
own migration. So: read what autogenerate suggests, write the one change by
hand.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_step_target"
down_revision: str | None = "add_routine_exercises"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings", sa.Column("step_target", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_settings", "step_target")
