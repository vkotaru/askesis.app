"""Add drive_file_id to meals table for Google Drive storage

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-11 00:02:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add drive_file_id column to meals table for Google Drive storage
    op.add_column(
        "meals", sa.Column("drive_file_id", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("meals", "drive_file_id")
