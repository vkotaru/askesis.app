"""Add icon field to activities table

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-03-12 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add icon field to activities table
    op.add_column(
        "activities", sa.Column("icon", sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("activities", "icon")
