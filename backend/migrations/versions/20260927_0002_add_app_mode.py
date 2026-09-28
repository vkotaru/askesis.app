"""Add user_settings.app_mode

Revision ID: add_app_mode
Revises: add_step_target
Create Date: 2026-09-27 00:00:00.000000

Which parts of the app an account sees. "full" is everything, as before;
"strength" is a gym logger and nothing else. Per account, because two people
share this install and use it for different things.

Defaults to "full" and is NOT NULL, so every existing account keeps exactly the
app it has today.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_app_mode"
down_revision: str | None = "add_step_target"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "app_mode",
            sa.String(20),
            nullable=False,
            server_default="full",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "app_mode")
