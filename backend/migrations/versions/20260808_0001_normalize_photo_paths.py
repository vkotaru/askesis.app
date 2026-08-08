"""Normalize photo paths to relative bucket paths

Revision ID: normalize_photo_paths
Revises: add_password_auth
Create Date: 2026-08-08 00:00:00.000000

Data only — no DDL. Photos now live on the server's own filesystem and the
columns hold a **relative** path (`photos/<name>`, `meals/<name>`) rooted at
`Settings.uploads_dir`. Before this revision the same two columns could hold an
absolute path from whatever host wrote it — including a *different* host, since
`POST /api/settings/restore` and `scripts/restore_backup.py` reinsert raw column
values from a backup. Absolute paths bake a container layout into the database
and break the moment the mount point moves.

This rewrites every non-null value that isn't already `<bucket>/<basename>` down
to exactly that. Idempotent: the skip guard means a second run is a no-op, so
re-running after a partial upgrade is safe.

`app.storage.resolve_media_path` still tolerates the legacy absolute shapes on
read — this migration cleans the stored data, it isn't what makes reads work.
"""

import posixpath
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "normalize_photo_paths"
down_revision: Union[str, None] = "add_password_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _basename(value: str) -> str:
    """Last path segment, tolerating Windows separators in restored data."""
    return posixpath.basename(value.replace("\\", "/").rstrip("/"))


def _normalize(table_name: str, column_name: str, bucket: str) -> int:
    bind = op.get_bind()
    table = sa.table(
        table_name,
        sa.column("id", sa.Integer),
        sa.column(column_name, sa.String),
    )
    col = table.c[column_name]

    rows = bind.execute(sa.select(table.c.id, col).where(col.isnot(None)))

    prefix = f"{bucket}/"
    updated = 0
    for row_id, value in rows:
        if not value:
            continue
        # Skip guard: already `<bucket>/<name>` with no further nesting.
        if value.startswith(prefix) and "/" not in value[len(prefix) :]:
            continue
        name = _basename(value)
        if not name:
            continue
        bind.execute(
            table.update()
            .where(table.c.id == row_id)
            .values(**{column_name: prefix + name})
        )
        updated += 1

    return updated


def upgrade() -> None:
    photos = _normalize("progress_photos", "file_path", "photos")
    meals = _normalize("meals", "photo_path", "meals")
    print(
        f"[normalize_photo_paths] rewrote {photos} progress_photos.file_path, "
        f"{meals} meals.photo_path"
    )


def downgrade() -> None:
    """No-op, deliberately.

    The original values were absolute paths tied to a host that may no longer
    exist, and they were not recorded anywhere before being rewritten — there is
    nothing to restore them from. Reverting the code that reads these columns is
    enough: `app.storage.resolve_media_path` accepts the relative shape this
    migration produces as well as the absolute shapes it replaced.
    """
    pass
