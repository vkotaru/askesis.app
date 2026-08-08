"""Add username + password_hash to users (additive; OAuth still works)

Revision ID: add_password_auth
Revises: p4q5r6s7t8u9
Create Date: 2026-08-04 00:00:00.000000

Additive only. The pre-existing application code keeps booting against this
schema because SQLAlchemy ignores columns it doesn't map, so this is safe to
land before the frontend catches up.

`username` is backfilled from the email local-part in Python via op.get_bind()
rather than SQL: `split_part` is Postgres-only and this has to run on the
SQLite dev DB too.

`password_hash` stays nullable — Google-created rows have no password yet and a
NOT NULL here would lock the operator out of their own server.
"""

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_password_auth"
down_revision: Union[str, None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept in sync with app.models.derive_username, but duplicated on purpose:
# migrations must stay pinned to the schema as of this revision and not drift
# with application code.
_STRIP_RE = re.compile(r"[^a-z0-9._-]")


def _derive(email: str) -> str:
    local = (email or "").split("@")[0].lower()
    return _STRIP_RE.sub("", local)[:64] or "user"


def upgrade() -> None:
    # 1. Add both columns nullable so existing rows survive the ALTER.
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )

    # 2. Backfill usernames from email local-parts, de-duplicating with a
    #    numeric suffix when two emails share one.
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("email", sa.String),
        sa.column("username", sa.String),
    )

    rows = bind.execute(sa.select(users.c.id, users.c.email).order_by(users.c.id))

    taken: set[str] = set()
    for user_id, email in rows:
        base = _derive(email)
        candidate = base
        suffix = 2
        while candidate in taken:
            # Trim the base so base+suffix still fits in 64 chars.
            tail = str(suffix)
            candidate = f"{base[: 64 - len(tail)]}{tail}"
            suffix += 1
        taken.add(candidate)

        bind.execute(
            users.update().where(users.c.id == user_id).values(username=candidate)
        )

    # 3. Now that every row has a value, make it NOT NULL + unique.
    #    migrations/env.py sets render_as_batch globally, so this works on
    #    SQLite as well as Postgres.
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "username", existing_type=sa.String(length=64), nullable=False
        )
        batch_op.create_unique_constraint("uq_users_username", ["username"])

    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_username", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
