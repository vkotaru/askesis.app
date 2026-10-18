"""Remember each MCP grant's previous refresh token, to catch its reuse

Revision ID: add_mcp_refresh_reuse
Revises: add_food_notes
Create Date: 2026-10-18 00:00:00.000000

Refresh tokens rotate, so a stolen one works once. Without the value it
replaced, the server could only say "unknown token" when the old one came back,
and could not tell a replay from garbage. `prior_refresh_token_hash` is that
value (a SHA-256 digest, like the current one). Presenting it means two parties
hold the token, and `oauth._refresh` revokes the grant. Nullable. Existing grants
simply have none until their next refresh.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_mcp_refresh_reuse"
down_revision: str | None = "add_food_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_grants") as batch:
        batch.add_column(
            sa.Column("prior_refresh_token_hash", sa.String(64), nullable=True)
        )
        batch.create_index(
            "ix_mcp_grants_prior_refresh_token_hash", ["prior_refresh_token_hash"]
        )


def downgrade() -> None:
    with op.batch_alter_table("mcp_grants") as batch:
        batch.drop_index("ix_mcp_grants_prior_refresh_token_hash")
        batch.drop_column("prior_refresh_token_hash")
