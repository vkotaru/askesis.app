"""Add updated_at and deleted_at columns for offline sync

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-23 12:00:00.000000

"""

from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that need sync columns
TABLES = [
    "daily_logs",
    "activities",
    "meals",
    "food_items",
    "body_measurements",
    "progress_photos",
]


def upgrade() -> None:
    now = datetime.utcnow().isoformat()
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text(f"'{now}'"),
            ),
        )
        op.add_column(
            table,
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    # Backfill updated_at from created_at for existing rows
    for table in TABLES:
        op.execute(
            f"UPDATE {table} SET updated_at = created_at WHERE updated_at IS NULL"
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "updated_at")
