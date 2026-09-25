"""Add routine_exercises

Revision ID: add_routine_exercises
Revises: add_strength_logging
Create Date: 2026-09-25 00:00:00.000000

Routines -- a saved workout you repeat, so a session starts pre-filled.

The header reuses `workout_templates`, which has existed since the initial
schema as dead code: a model, a migration and a backup-spec entry, but no
router, no UI and no writer. Its `exercises_json` column was never written to.
Rather than add a second table meaning the same thing, this gives it real
children.

`target_*` are intentions. They are deliberately never copied into a logged set
by the migration or the API -- "what I planned" and "what I did" have to stay
distinguishable, or the question a routine exists to answer stops working.

Additive and reversible. Nothing reads the old `exercises_json`, so nothing is
migrated out of it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_routine_exercises"
down_revision: str | None = "add_strength_logging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routine_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "routine_id",
            sa.Integer(),
            sa.ForeignKey("workout_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "catalog_id",
            sa.Integer(),
            sa.ForeignKey("exercise_catalog.id"),
            nullable=True,
        ),
        # Denormalised for the same reason it is on `exercises`: the catalogue is
        # shared, so someone else renaming an entry must not rewrite what your
        # routine says.
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_routine_exercises_routine_id", "routine_exercises", ["routine_id"]
    )
    op.create_index(
        "ix_routine_exercises_catalog_id", "routine_exercises", ["catalog_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_routine_exercises_catalog_id", table_name="routine_exercises")
    op.drop_index("ix_routine_exercises_routine_id", table_name="routine_exercises")
    op.drop_table("routine_exercises")
