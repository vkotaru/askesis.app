"""Add google_sheet_id and last_gsheet_sync to user_settings

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-03-11 00:04:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Google Sheets sync settings to user_settings table
    op.add_column(
        "user_settings", sa.Column("google_sheet_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "user_settings", sa.Column("last_gsheet_sync", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_settings", "last_gsheet_sync")
    op.drop_column("user_settings", "google_sheet_id")
