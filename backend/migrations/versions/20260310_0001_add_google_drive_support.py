"""Add Google Drive support

Revision ID: a1b2c3d4e5f6
Revises: c92f92ae7150
Create Date: 2026-03-10 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c92f92ae7150"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add google_refresh_token to users table
    op.add_column("users", sa.Column("google_refresh_token", sa.Text(), nullable=True))

    # Add drive_file_id to progress_photos table
    op.add_column(
        "progress_photos", sa.Column("drive_file_id", sa.String(100), nullable=True)
    )

    # Make file_path nullable (for transition to Drive storage)
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("progress_photos") as batch_op:
        batch_op.alter_column("file_path", existing_type=sa.String(500), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("progress_photos") as batch_op:
        batch_op.alter_column("file_path", existing_type=sa.String(500), nullable=False)
    op.drop_column("progress_photos", "drive_file_id")
    op.drop_column("users", "google_refresh_token")
