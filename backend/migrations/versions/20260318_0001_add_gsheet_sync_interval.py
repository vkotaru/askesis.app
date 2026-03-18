"""Add gsheet_sync_interval_hours to user_settings

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-03-18 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("gsheet_sync_interval_hours", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "gsheet_sync_interval_hours")
