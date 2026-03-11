"""Add drive_parent_folder_id to user_settings

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10 00:02:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add drive_parent_folder_id to user_settings table
    op.add_column(
        "user_settings", sa.Column("drive_parent_folder_id", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_settings", "drive_parent_folder_id")
