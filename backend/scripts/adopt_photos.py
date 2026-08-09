#!/usr/bin/env python3
"""Adopt photo files copied onto the server by hand, matching them to DB rows.

The operator drops their Google Drive photo dump into `<uploads>/_inbox/` — an
unzipped Drive folder tree works as-is, the walk is recursive — and this script
figures out which `progress_photos` / `meals` row each file belongs to by
parsing the filename, copies it into the right bucket, and sets the row's path
column.

    python scripts/adopt_photos.py                 # dry run (the default)
    python scripts/adopt_photos.py --apply         # actually copy + update rows
    python scripts/adopt_photos.py --apply --create-missing
    python scripts/adopt_photos.py --prune-inbox   # remove verified sources
    python scripts/adopt_photos.py --verify        # audit rows vs disk

Filenames come from the two generators in the app:

    askesis_{user_id}_{date}_{view}_{hex8}.jpg     progress photo
    meal_{user_id}_{meal_id}_{hex8}.jpg            meal photo

plus the pre-Drive local names, which lack the prefix, and Drive's ` (1)`
collision suffix on duplicate downloads. `.jpeg` and upper-case extensions are
accepted too.

Outcomes, one per file:

    ADOPT           parsed, matched exactly one row, will be/was linked
    SKIP-ALREADY    row already points at this file, it exists, bytes match
    CONFLICT-DEST   destination exists with *different* bytes — never clobbered
    CONFLICT-ROWS   more than one candidate row — ambiguous, never guessed
    ORPHAN          filename parses but no row matches
    UNPARSEABLE     filename doesn't match any known pattern

Exit status is non-zero if any CONFLICT occurred, so this is safe to gate a
deploy on.
"""

import argparse
import hashlib
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import storage  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Meal, PhotoView, ProgressPhoto, User  # noqa: E402


INBOX_DIRNAME = "_inbox"
ORPHANS_DIRNAME = "_orphans"
UNPARSEABLE_DIRNAME = "_unparseable"
# Subdirectories of _inbox that hold this script's own output, never re-walked.
RESERVED = {ORPHANS_DIRNAME, UNPARSEABLE_DIRNAME}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# ── Filename patterns ────────────────────────────────────────────────────────
# Drive appends " (1)" to a duplicate download; the suffix lands before the
# extension. `_DUP` absorbs any number of them.
_DUP = r"(?: ?\(\d+\))*"
_EXT = r"\.(?:jpe?g|png|webp|heic|heif)"
_VIEW = r"(?P<view>front|side|back)"

# Current generator: askesis_{user_id}_{date}_{view}_{hex8}.jpg
PROGRESS_RE = re.compile(
    rf"^askesis_(?P<user_id>\d+)_(?P<date>\d{{4}}-\d{{2}}-\d{{2}})_{_VIEW}_[0-9a-f]+{_DUP}{_EXT}$",
    re.IGNORECASE,
)
# Pre-Drive local name, same fields without the `askesis_` prefix.
PROGRESS_LEGACY_RE = re.compile(
    rf"^(?P<user_id>\d+)_(?P<date>\d{{4}}-\d{{2}}-\d{{2}})_{_VIEW}_[0-9a-f]+{_DUP}{_EXT}$",
    re.IGNORECASE,
)
# Current generator: meal_{user_id}_{meal_id}_{hex8}.jpg
MEAL_RE = re.compile(
    rf"^meal_(?P<user_id>\d+)_(?P<meal_id>\d+)_[0-9a-f]+{_DUP}{_EXT}$",
    re.IGNORECASE,
)
# Pre-Drive local name, same fields without the `meal_` prefix. NOTE: this is
# ambiguous with PROGRESS_LEGACY_RE for a name like `1_57_9f0e.jpg`, which could
# be either. The date-bearing progress pattern is tried first, so a name that
# can be read as a progress photo is read as one.
MEAL_LEGACY_RE = re.compile(
    rf"^(?P<user_id>\d+)_(?P<meal_id>\d+)_[0-9a-f]+{_DUP}{_EXT}$",
    re.IGNORECASE,
)


@dataclass
class Parsed:
    kind: str  # "progress" | "meal"
    user_id: int
    view: str | None = None
    photo_date: date_type | None = None
    meal_id: int | None = None


def parse_filename(name: str) -> Parsed | None:
    """Identify a filename. Order matters — see MEAL_LEGACY_RE's note."""
    for pattern in (PROGRESS_RE, PROGRESS_LEGACY_RE):
        m = pattern.match(name)
        if m:
            try:
                parsed_date = date_type.fromisoformat(m.group("date"))
            except ValueError:
                continue
            return Parsed(
                kind="progress",
                user_id=int(m.group("user_id")),
                view=m.group("view").lower(),
                photo_date=parsed_date,
            )

    for pattern in (MEAL_RE, MEAL_LEGACY_RE):
        m = pattern.match(name)
        if m:
            return Parsed(
                kind="meal",
                user_id=int(m.group("user_id")),
                meal_id=int(m.group("meal_id")),
            )

    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Result:
    source: Path
    outcome: str
    detail: str = ""
    dest: str | None = None


@dataclass
class Plan:
    results: list[Result] = field(default_factory=list)

    def add(
        self, source: Path, outcome: str, detail: str = "", dest: str | None = None
    ):
        self.results.append(Result(source, outcome, detail, dest))


# ── Inbox handling ───────────────────────────────────────────────────────────


def inbox_root() -> Path:
    return storage.UPLOADS_ROOT / INBOX_DIRNAME


def walk_inbox(root: Path) -> list[Path]:
    """Every image file under the inbox, skipping this script's own output."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if rel_parts and rel_parts[0] in RESERVED:
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        files.append(path)
    return files


def quarantine(source: Path, root: Path, bucket_dirname: str, apply: bool) -> str:
    """Move a file into `_inbox/<bucket_dirname>/`, preserving its subpath."""
    relative = source.relative_to(root)
    dest = root / bucket_dirname / relative
    if apply:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Don't clobber a previous quarantine of the same name.
        final = dest
        counter = 1
        while final.exists():
            final = dest.with_name(f"{dest.stem}.{counter}{dest.suffix}")
            counter += 1
        shutil.move(str(source), str(final))
        return str(final.relative_to(root))
    return str(dest.relative_to(root))


# ── Row matching ─────────────────────────────────────────────────────────────


def find_progress_rows(db, parsed: Parsed) -> list[ProgressPhoto]:
    try:
        view = PhotoView(parsed.view)
    except ValueError:
        return []
    return (
        db.query(ProgressPhoto)
        .filter(
            ProgressPhoto.user_id == parsed.user_id,
            ProgressPhoto.date == parsed.photo_date,
            ProgressPhoto.view == view,
        )
        # A soft-deleted row is a tombstone; adopting a file onto it would
        # resurrect nothing and just strand the file.
        .filter(ProgressPhoto.deleted_at.is_(None))
        .order_by(ProgressPhoto.id)
        .all()
    )


def find_meal_rows(db, parsed: Parsed) -> list[Meal]:
    # Both id AND user_id: a meal id that belongs to another user means the
    # file is foreign or the filename is corrupt, and must not be adopted.
    return (
        db.query(Meal)
        .filter(Meal.id == parsed.meal_id, Meal.user_id == parsed.user_id)
        .filter(Meal.deleted_at.is_(None))
        .order_by(Meal.id)
        .all()
    )


def bucket_for(kind: str) -> str:
    return storage.PHOTOS_BUCKET if kind == "progress" else storage.MEALS_BUCKET


def row_label(row) -> str:
    """Table-qualified row id — 'row 2' alone is ambiguous across two tables."""
    table = "progress_photos" if isinstance(row, ProgressPhoto) else "meals"
    return f"{table} id={row.id}"


def current_path(row) -> str | None:
    return row.file_path if isinstance(row, ProgressPhoto) else row.photo_path


def set_path(row, value: str) -> None:
    if isinstance(row, ProgressPhoto):
        row.file_path = value
    else:
        row.photo_path = value


# ── Main adoption pass ───────────────────────────────────────────────────────


def adopt(apply: bool, create_missing: bool, prune_inbox: bool) -> Plan:
    plan = Plan()
    root = inbox_root()

    if not root.is_dir():
        print(f"No inbox at {root} — nothing to adopt.")
        print(f"Create it and copy your Drive photo dump in:  mkdir -p {root}")
        return plan

    files = walk_inbox(root)
    if not files:
        print(f"Inbox {root} contains no image files.")
        return plan

    db = SessionLocal()
    try:
        for source in files:
            parsed = parse_filename(source.name)

            if parsed is None:
                moved = quarantine(source, root, UNPARSEABLE_DIRNAME, apply)
                plan.add(source, "UNPARSEABLE", f"-> {INBOX_DIRNAME}/{moved}")
                continue

            bucket = bucket_for(parsed.kind)
            rows = (
                find_progress_rows(db, parsed)
                if parsed.kind == "progress"
                else find_meal_rows(db, parsed)
            )

            if len(rows) > 1:
                table = "progress_photos" if parsed.kind == "progress" else "meals"
                ids = ",".join(str(r.id) for r in rows)
                plan.add(source, "CONFLICT-ROWS", f"matches {table} ids {ids}")
                continue

            if not rows:
                if parsed.kind == "progress" and create_missing:
                    row = synthesize_progress(db, parsed, apply)
                    if row is None:
                        moved = quarantine(source, root, ORPHANS_DIRNAME, apply)
                        plan.add(
                            source,
                            "ORPHAN",
                            f"user {parsed.user_id} does not exist -> {INBOX_DIRNAME}/{moved}",
                        )
                        continue
                    rows = [row]
                else:
                    # A Meal needs `date` and `label`, neither of which the
                    # filename carries, so a meal row is never synthesized.
                    moved = quarantine(source, root, ORPHANS_DIRNAME, apply)
                    plan.add(source, "ORPHAN", f"no row -> {INBOX_DIRNAME}/{moved}")
                    continue

            row = rows[0]
            dest_rel = f"{bucket}/{source.name}"
            dest_abs = storage.UPLOADS_ROOT / bucket / source.name
            source_digest = sha256_file(source)

            # SKIP-ALREADY: the row already points here, the file is on disk,
            # and the bytes match. This is what makes a re-run a no-op.
            if (
                current_path(row) == dest_rel
                and dest_abs.is_file()
                and sha256_file(dest_abs) == source_digest
            ):
                plan.add(source, "SKIP-ALREADY", row_label(row), dest_rel)
                if prune_inbox and apply:
                    source.unlink()
                continue

            # CONFLICT-DEST: something else already occupies the destination.
            if dest_abs.is_file() and sha256_file(dest_abs) != source_digest:
                plan.add(
                    source,
                    "CONFLICT-DEST",
                    f"{dest_rel} exists with different bytes",
                    dest_rel,
                )
                continue

            label = row_label(row) + (
                " (created)" if getattr(row, "_synthesized", False) else ""
            )
            plan.add(source, "ADOPT", label, dest_rel)

            if not apply:
                continue

            # Copy (never move): the source stays put so a failure here is
            # recoverable and --prune-inbox can verify before deleting.
            dest_abs.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest_abs.with_name(f".{dest_abs.name}.tmp")
            shutil.copyfile(source, tmp)
            tmp.replace(dest_abs)

            set_path(row, dest_rel)
            # Commit per file: a crash mid-run leaves a consistent partial
            # state that a re-run completes.
            db.commit()

            if prune_inbox:
                # Re-read from disk and compare before unlinking the source.
                if sha256_file(dest_abs) == source_digest:
                    source.unlink()
                else:
                    plan.results[-1].detail += " (copy mismatch; source kept)"
    finally:
        db.close()

    return plan


def synthesize_progress(db, parsed: Parsed, apply: bool) -> ProgressPhoto | None:
    """Create the progress_photos row a filename describes.

    Only progress photos: the filename carries user_id + date + view, which is
    the whole row. Returns None if the user doesn't exist.
    """
    user = db.query(User).filter(User.id == parsed.user_id).first()
    if not user:
        return None

    row = ProgressPhoto(
        user_id=parsed.user_id,
        date=parsed.photo_date,
        view=PhotoView(parsed.view),
        file_path=None,
        notes="Adopted from filesystem import",
    )
    row._synthesized = True
    if not apply:
        # Dry run: hand back an unsaved stand-in so the caller can report ADOPT
        # without touching the database.
        row.id = 0
        return row

    db.add(row)
    db.commit()
    db.refresh(row)
    row._synthesized = True
    return row


# ── Verify ───────────────────────────────────────────────────────────────────


def verify() -> int:
    """Report rows whose file is missing, and files no row references."""
    db = SessionLocal()
    missing: list[str] = []
    referenced: set[Path] = set()

    try:
        photos = (
            db.query(ProgressPhoto).filter(ProgressPhoto.file_path.isnot(None)).all()
        )
        for p in photos:
            try:
                path = storage.resolve_media_path(p.file_path, storage.PHOTOS_BUCKET)
            except Exception as e:
                missing.append(f"progress_photos id={p.id} {p.file_path!r}: {e}")
                continue
            if path.is_file():
                referenced.add(path)
            else:
                missing.append(
                    f"progress_photos id={p.id} user={p.user_id} date={p.date} "
                    f"view={p.view.value} -> {p.file_path} (missing on disk)"
                )

        meals = db.query(Meal).filter(Meal.photo_path.isnot(None)).all()
        for m in meals:
            try:
                path = storage.resolve_media_path(m.photo_path, storage.MEALS_BUCKET)
            except Exception as e:
                missing.append(f"meals id={m.id} {m.photo_path!r}: {e}")
                continue
            if path.is_file():
                referenced.add(path)
            else:
                missing.append(
                    f"meals id={m.id} user={m.user_id} date={m.date} "
                    f"-> {m.photo_path} (missing on disk)"
                )
    finally:
        db.close()

    unreferenced: list[Path] = []
    for bucket in storage.BUCKETS:
        directory = storage.UPLOADS_ROOT / bucket
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path not in referenced
            ):
                unreferenced.append(path)

    print(f"\n=== VERIFY ({storage.UPLOADS_ROOT}) ===")
    print(f"\nRows whose file is missing on disk: {len(missing)}")
    for line in missing:
        print(f"  {line}")

    print(f"\nFiles on disk no row references: {len(unreferenced)}")
    for path in unreferenced:
        print(f"  {path.relative_to(storage.UPLOADS_ROOT)}")

    print(f"\nRows correctly backed by a file: {len(referenced)}")
    return 0


# ── Reporting ────────────────────────────────────────────────────────────────


def report(plan: Plan, root: Path, apply: bool) -> int:
    if not plan.results:
        return 0

    print(f"\n{'OUTCOME':<15} {'FILE':<52} DETAIL")
    print("-" * 110)
    for r in plan.results:
        try:
            shown = str(r.source.relative_to(root))
        except ValueError:
            shown = r.source.name
        if len(shown) > 51:
            shown = "..." + shown[-48:]
        print(f"{r.outcome:<15} {shown:<52} {r.detail}")

    counts = Counter(r.outcome for r in plan.results)
    print("\n=== SUMMARY ===")
    for outcome in (
        "ADOPT",
        "SKIP-ALREADY",
        "CONFLICT-DEST",
        "CONFLICT-ROWS",
        "ORPHAN",
        "UNPARSEABLE",
    ):
        if counts.get(outcome):
            print(f"  {outcome:<15} {counts[outcome]}")
    print(f"  {'TOTAL':<15} {len(plan.results)}")

    conflicts = counts.get("CONFLICT-DEST", 0) + counts.get("CONFLICT-ROWS", 0)
    if not apply:
        print("\nDRY RUN — nothing was written. Re-run with --apply to commit.")
    if conflicts:
        print(
            f"\n{conflicts} conflict(s) need a human decision; "
            "no file was overwritten and no ambiguous row was guessed."
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Adopt photo files copied into <uploads>/_inbox/ by matching their "
            "filenames to existing progress_photos / meals rows."
        ),
        epilog=(
            "Dry run is the default: nothing is written unless you pass --apply.\n"
            "\n"
            "--create-missing is asymmetric on purpose. A progress filename carries\n"
            "user_id, date and view — the entire row — so the row can be synthesized\n"
            "(provided the user exists). A meals row additionally needs `date` and\n"
            "`label`, and the filename carries neither, so a meal row is NEVER\n"
            "synthesized: an unmatched meal photo goes to _inbox/_orphans/ instead.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually copy files and update rows (default is a dry run)",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="synthesize a progress_photos row when none matches (never a meal row)",
    )
    parser.add_argument(
        "--prune-inbox",
        action="store_true",
        help="unlink each source only after its copy re-reads with a matching sha256",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="audit rows against disk and exit; does not walk the inbox",
    )
    args = parser.parse_args()

    if args.verify:
        return verify()

    if args.prune_inbox and not args.apply:
        print("--prune-inbox requires --apply (it deletes files).", file=sys.stderr)
        return 2

    root = inbox_root()
    print(f"Uploads root: {storage.UPLOADS_ROOT}")
    print(f"Inbox:        {root}")
    print(f"Mode:         {'APPLY' if args.apply else 'DRY RUN'}")

    plan = adopt(
        apply=args.apply,
        create_missing=args.create_missing,
        prune_inbox=args.prune_inbox,
    )
    return report(plan, root, args.apply)


if __name__ == "__main__":
    sys.exit(main())
