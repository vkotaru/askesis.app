"""Local filesystem media storage.

Photos live on the server's own disk under `UPLOADS_ROOT`, split into buckets
(`photos/` for progress photos, `meals/` for meal photos). The database stores
the **relative** POSIX path (`"photos/askesis_1_2026-08-04_front_ab12cd34.jpg"`),
never an absolute one: an absolute path bakes the container layout into the
database and breaks the moment the mount point moves.

`resolve_media_path` is deliberately tolerant on read, because a live database
can hold three different shapes:

1. a relative path — what this module writes,
2. a legacy absolute path produced by this host before the Drive era,
3. a legacy absolute path produced by a *different* host — those arrive via
   `POST /api/settings/restore` and `scripts/restore_backup.py`, which reinsert
   raw column values from a backup taken elsewhere.

For (2) and (3) it degrades to `<bucket>/<name>` when the parent directory is a
known bucket, otherwise to `<name>` under the default bucket. Whatever the
input shape, the result must stay inside `UPLOADS_ROOT` or the call fails.
"""

import os
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings

# Resolved once at import: the process's uploads root.
UPLOADS_ROOT = Path(get_settings().uploads_dir).resolve()

PHOTOS_BUCKET = "photos"
MEALS_BUCKET = "meals"
BUCKETS = (PHOTOS_BUCKET, MEALS_BUCKET)


def bucket_dir(bucket: str) -> Path:
    """Absolute directory for a bucket, created on demand."""
    if bucket not in BUCKETS:
        raise ValueError(f"Unknown media bucket: {bucket!r}")
    path = UPLOADS_ROOT / bucket
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_media(bucket: str, filename: str, content: bytes) -> str:
    """Write `content` atomically and return the relative POSIX path.

    The write goes to a temp file in the same directory and is then moved into
    place with `os.replace`, so a reader never observes a half-written image
    and a crash mid-write cannot corrupt an existing file.
    """
    directory = bucket_dir(bucket)
    name = Path(filename).name
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid media filename: {filename!r}")

    dest = directory / name
    tmp = directory / f".{name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return f"{bucket}/{name}"


def _candidate_relative(stored: str, default_bucket: str) -> str:
    """Normalise any stored shape to a `<bucket>/<name>` relative path."""
    raw = str(stored).strip().replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts:
        raise HTTPException(status_code=404, detail="Photo file not found")

    name = parts[-1]
    parent = parts[-2] if len(parts) >= 2 else None

    if parent in BUCKETS:
        return f"{parent}/{name}"
    return f"{default_bucket}/{name}"


def resolve_media_path(stored: str, default_bucket: str = PHOTOS_BUCKET) -> Path:
    """Resolve a stored column value to an absolute path inside UPLOADS_ROOT.

    Raises HTTPException(403) if the result escapes the uploads root. The
    containment check uses `Path.is_relative_to`, not `str.startswith`: a
    prefix comparison against "/uploads" happily accepts "/uploads-evil".
    """
    if ".." in str(stored).replace("\\", "/").split("/"):
        raise HTTPException(status_code=403, detail="Invalid media path")

    relative = _candidate_relative(stored, default_bucket)
    resolved = (UPLOADS_ROOT / relative).resolve()

    if not resolved.is_relative_to(UPLOADS_ROOT):
        raise HTTPException(status_code=403, detail="Invalid media path")

    return resolved


def media_exists(stored: str | None, default_bucket: str = PHOTOS_BUCKET) -> bool:
    """True if the stored path resolves to a readable regular file."""
    if not stored:
        return False
    try:
        return resolve_media_path(stored, default_bucket).is_file()
    except HTTPException:
        return False


def delete_media(stored: str | None, default_bucket: str = PHOTOS_BUCKET) -> bool:
    """Unlink the file a stored path points at. Returns True if it was removed."""
    if not stored:
        return False
    try:
        path = resolve_media_path(stored, default_bucket)
    except HTTPException:
        return False
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True
