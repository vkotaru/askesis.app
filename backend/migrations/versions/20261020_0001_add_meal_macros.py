"""Give each meal its own protein, carbs and fat

Revision ID: add_meal_macros
Revises: add_mcp_refresh_reuse
Create Date: 2026-10-20 00:00:00.000000

Macros were stored only as one total per day (daily_nutrition), so logging
lunch through the MCP connector in replace mode overwrote breakfast's, and
nothing recorded which meal contributed what. These columns hold a meal's
share. The day total stays where it is; see app/intake_log.py. Nullable:
every existing meal simply has no breakdown.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_meal_macros"
down_revision: str | None = "add_mcp_refresh_reuse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("meals") as batch:
        batch.add_column(sa.Column("protein_g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("carbs_g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("fat_g", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meals") as batch:
        batch.drop_column("fat_g")
        batch.drop_column("carbs_g")
        batch.drop_column("protein_g")
