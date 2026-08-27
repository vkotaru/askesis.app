"""Add the MCP connector's OAuth tables

Revision ID: add_mcp_oauth_tables
Revises: add_weekly_training_targets
Create Date: 2026-08-27 00:00:00.000000

Three tables backing OAuth 2.1 for the MCP connector: registered clients,
single-use authorization codes, and live grants.

**Every secret is hashed at rest**, which is a deliberate correction of the
`report_tokens` precedent — that table stores its bearer token in the clear.
SHA-256 rather than bcrypt, and only because of what these values are: 256-bit
random strings with no entropy to attack, where a per-request bcrypt on the
token path would be a self-inflicted denial of service. Passwords still go
through bcrypt (`app/security.py`); nothing here changes that.

Additive and reversible. The app never reads these tables — they exist in
`app/models.py` only so Alembic autogenerate compares against one metadata and
does not propose dropping them.

Note the MCP service must NOT run migrations: the app container owns
`alembic upgrade head`, and two containers racing it at boot is a real failure.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_mcp_oauth_tables"
down_revision: str | None = "add_weekly_training_targets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column("redirect_uris", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_mcp_clients_client_id", "mcp_clients", ["client_id"], unique=True
    )

    op.create_table(
        "mcp_auth_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(10), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_mcp_auth_codes_code_hash", "mcp_auth_codes", ["code_hash"], unique=True
    )
    op.create_index("ix_mcp_auth_codes_client_id", "mcp_auth_codes", ["client_id"])
    op.create_index("ix_mcp_auth_codes_user_id", "mcp_auth_codes", ["user_id"])

    op.create_table(
        "mcp_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mcp_grants_user_id", "mcp_grants", ["user_id"])
    op.create_index("ix_mcp_grants_client_id", "mcp_grants", ["client_id"])
    op.create_index(
        "ix_mcp_grants_refresh_token_hash",
        "mcp_grants",
        ["refresh_token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_grants_refresh_token_hash", table_name="mcp_grants")
    op.drop_index("ix_mcp_grants_client_id", table_name="mcp_grants")
    op.drop_index("ix_mcp_grants_user_id", table_name="mcp_grants")
    op.drop_table("mcp_grants")
    op.drop_index("ix_mcp_auth_codes_user_id", table_name="mcp_auth_codes")
    op.drop_index("ix_mcp_auth_codes_client_id", table_name="mcp_auth_codes")
    op.drop_index("ix_mcp_auth_codes_code_hash", table_name="mcp_auth_codes")
    op.drop_table("mcp_auth_codes")
    op.drop_index("ix_mcp_clients_client_id", table_name="mcp_clients")
    op.drop_table("mcp_clients")
