"""Add daily macro fields to daily_logs

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-03-11 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add daily nutrition total fields to daily_logs table
    op.add_column(
        "daily_logs", sa.Column("total_calories", sa.Integer(), nullable=True)
    )
    op.add_column(
        "daily_logs", sa.Column("protein_g", sa.Float(), nullable=True)
    )
    op.add_column(
        "daily_logs", sa.Column("carbs_g", sa.Float(), nullable=True)
    )
    op.add_column(
        "daily_logs", sa.Column("fat_g", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("daily_logs", "fat_g")
    op.drop_column("daily_logs", "carbs_g")
    op.drop_column("daily_logs", "protein_g")
    op.drop_column("daily_logs", "total_calories")
