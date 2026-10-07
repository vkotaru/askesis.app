"""Give a saved food somewhere to keep how it was made

Revision ID: add_food_notes
Revises: add_exercise_tracking
Create Date: 2026-10-07 00:00:00.000000

The food library grows from the MCP connector now (`save_food`): a label read
off a screenshot, or a home recipe worked out per serving from its ingredients.
For a recipe the per-serving numbers are a computation, and without the inputs
there is no way to check or redo it -- you would know a bowl is 540 kcal and
never why. `notes` holds the ingredient list (or where a label's numbers came
from). Nullable; every existing row simply has none.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_food_notes"
down_revision: str | None = "add_exercise_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("food_items") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("food_items") as batch:
        batch.drop_column("notes")
