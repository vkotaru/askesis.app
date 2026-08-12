"""Add users.password_changed_at (token epoch for session invalidation)

Revision ID: add_password_changed_at
Revises: normalize_photo_paths
Create Date: 2026-08-12 00:00:00.000000

Additive only: one nullable column, nothing dropped, nothing rewritten.

Deliberately NOT backfilled. NULL is a meaningful value here — it means "this
account has not changed its password since the column existed", and
app/routers/auth.py skips the token-epoch check entirely for such rows. That is
what lets sessions issued before this migration keep working through the
deploy: their tokens carry no `pwd_at` claim, and there is nothing to compare
them against. Backfilling with `now()` would instead sign everyone out the
moment this lands, for no security gain — no password has changed.

The column stops being NULL the first time the account sets or changes a
password, and from then on every token it issues carries the matching stamp.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_password_changed_at"
down_revision: Union[str, None] = "normalize_photo_paths"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    # Only ever drops the column this revision added. Reverting re-widens the
    # session window (tokens stop being epoch-checked) but loses no user data.
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_changed_at")
