"""Add weekly training targets to user_settings

Revision ID: add_weekly_training_targets
Revises: add_daily_log_sources
Create Date: 2026-08-25 00:00:00.000000

Three nullable columns backing the dashboard's weekly-targets tile: a run
distance, a bike distance, and the set of disciplines you plan to touch.

All nullable with no backfill, because NULL is meaningful here -- it means "no
target set", and the tile renders nothing rather than inventing a goal of zero
and reporting you permanently short of it.

Distances are km. Everything in this schema is canonical metric and converts at
the API boundary (app/units.py); a column holding miles would be the first
exception and would silently break for anyone who switches units.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_weekly_training_targets"
down_revision: str | None = "add_daily_log_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings", sa.Column("weekly_run_km", sa.Float(), nullable=True)
    )
    op.add_column(
        "user_settings", sa.Column("weekly_bike_km", sa.Float(), nullable=True)
    )
    op.add_column(
        "user_settings", sa.Column("weekly_disciplines", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_settings", "weekly_disciplines")
    op.drop_column("user_settings", "weekly_bike_km")
    op.drop_column("user_settings", "weekly_run_km")
