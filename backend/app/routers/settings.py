import enum
import json
import logging
from datetime import date as date_type, datetime
from typing import Any, NamedTuple

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, StatementError
from pydantic import BaseModel

from app.database import Base, get_db
from app.models import User, UserSettings
from app.routers.auth import get_current_user

logger = logging.getLogger("askesis.settings")

router = APIRouter()


class UserSettingsSchema(BaseModel):
    theme: str = "system"
    font_size: str = "medium"  # xs, sm, medium, lg, xl, 2xl
    font_family: str = "space-grotesk"
    content_width: str = "medium"
    color_scheme: str = "forest"
    # Unit preferences
    distance_unit: str = "km"
    measurement_unit: str = "cm"
    weight_unit: str = "kg"
    water_unit: str = "ml"
    # Nutrition targets
    calorie_target: int | None = None
    protein_target: int | None = None

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    font_size: str | None = None  # xs, sm, medium, lg, xl, 2xl
    font_family: str | None = None
    content_width: str | None = None
    color_scheme: str | None = None
    distance_unit: str | None = None
    measurement_unit: str | None = None
    weight_unit: str | None = None
    water_unit: str | None = None
    calorie_target: int | None = None
    protein_target: int | None = None


def get_or_create_settings(db: Session, user_id: int) -> UserSettings:
    """Get existing settings or create with defaults."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

    if not settings:
        settings = UserSettings(
            user_id=user_id,
            theme="system",
            font_size="medium",
            font_family="space-grotesk",
            content_width="medium",
            color_scheme="forest",
            distance_unit="km",
            measurement_unit="cm",
            weight_unit="kg",
            water_unit="ml",
        )
        db.add(settings)
        try:
            db.commit()
            db.refresh(settings)
        except IntegrityError:
            # Another request created it, rollback and fetch
            db.rollback()
            settings = (
                db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            )

    return settings


@router.get("/", response_model=UserSettingsSchema)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )

    if not settings:
        return UserSettingsSchema()

    return settings


@router.put("/", response_model=UserSettingsSchema)
def update_settings(
    settings_data: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get or create settings (handles race condition)
    settings = get_or_create_settings(db, current_user.id)

    # Update fields
    if settings_data.theme is not None:
        settings.theme = settings_data.theme
    if settings_data.font_size is not None:
        settings.font_size = settings_data.font_size
    if settings_data.font_family is not None:
        settings.font_family = settings_data.font_family
    if settings_data.content_width is not None:
        settings.content_width = settings_data.content_width
    if settings_data.color_scheme is not None:
        settings.color_scheme = settings_data.color_scheme
    if settings_data.distance_unit is not None:
        settings.distance_unit = settings_data.distance_unit
    if settings_data.measurement_unit is not None:
        settings.measurement_unit = settings_data.measurement_unit
    if settings_data.weight_unit is not None:
        settings.weight_unit = settings_data.weight_unit
    if settings_data.water_unit is not None:
        settings.water_unit = settings_data.water_unit
    if settings_data.calorie_target is not None:
        settings.calorie_target = settings_data.calorie_target
    if settings_data.protein_target is not None:
        settings.protein_target = settings_data.protein_target

    db.commit()
    db.refresh(settings)
    return settings


# ── Personal data backup & restore ───────────────────────────────────────────
#
# Both endpoints are scoped to **the caller's own rows**. That is the whole
# security design, so it is worth stating why.
#
# This app has no admin role, and `check_view_permission` governs every other
# cross-user read: you see another household member's data only for the
# categories they explicitly shared. A whole-database dump behind a bare
# `Depends(get_current_user)` bypassed all of that — it handed any logged-in
# user every other user's health data *and*, once password auth landed, their
# bcrypt `password_hash` to crack offline. Inventing a role system for a
# two-person box is overkill; scoping to self is the right lever, and it still
# serves the actual need ("give me a copy of my data, and let me put it back").
#
# Consequences, deliberately:
#   * `users` is never exported — so `password_hash` cannot be, by construction
#     rather than by remembering to filter a column.
#   * `report_tokens` is never exported. A report token is a bearer credential:
#     anyone holding it can read the public report. It is not backup material.
#   * `data_shares` is never exported or restored. Restoring one would grant
#     cross-user access from an uploaded file; shares are re-created through
#     /api/sharing, which validates both sides.
#   * A full-database snapshot is now an *operator* task (shell access to the
#     box), not something an authenticated user can pull over HTTP.
#     See SELF_HOSTING.md.
#
# Restore never interpolates an identifier from the uploaded file into SQL.
# Table and column names are matched against SQLAlchemy's own metadata and then
# thrown away; the statement is built from the `Table` object, and every value
# is a bound parameter. A name containing a double quote simply fails the
# allow-list check.

BACKUP_FORMAT_VERSION = 2


class _TableSpec(NamedTuple):
    """How one table is scoped to a user, for both directions.

    ``user_column`` — the column holding ``users.id``; the row is mine iff it
    equals my id, and on restore it is *overwritten* with my id.

    ``required_parents`` — ``(fk_column, parent_table)`` for tables that have no
    user column of their own. Backed up only when the parent is mine; restored
    only when the referenced parent row exists and is mine, otherwise skipped.

    ``optional_parents`` — same, but a reference I do not own is nulled out
    instead of dropping the row.
    """

    table: str
    user_column: str | None = None
    required_parents: tuple[tuple[str, str], ...] = ()
    optional_parents: tuple[tuple[str, str], ...] = ()


# Order matters: parents before children, both for export readability and so a
# restore inserts a parent before anything that references it.
_BACKUP_SPEC: tuple[_TableSpec, ...] = (
    _TableSpec("user_settings", user_column="user_id"),
    _TableSpec("daily_logs", user_column="user_id"),
    _TableSpec("daily_nutrition", user_column="user_id"),
    _TableSpec("body_measurements", user_column="user_id"),
    _TableSpec("progress_photos", user_column="user_id"),
    _TableSpec("meal_templates", user_column="user_id"),
    _TableSpec("workout_templates", user_column="user_id"),
    # user_id is nullable here: NULL means a shared/seed food owned by nobody.
    # Only my own rows travel; seed rows are part of the target install.
    _TableSpec("food_items", user_column="user_id"),
    _TableSpec("meals", user_column="user_id"),
    _TableSpec("meal_food_items", required_parents=(("meal_id", "meals"),)),
    _TableSpec("activities", user_column="user_id"),
    _TableSpec("exercises", required_parents=(("activity_id", "activities"),)),
    _TableSpec("training_plans", user_column="user_id"),
    _TableSpec(
        "planned_workouts",
        required_parents=(("plan_id", "training_plans"),),
        optional_parents=(("activity_id", "activities"),),
    ),
)

_SPEC_BY_TABLE = {spec.table: spec for spec in _BACKUP_SPEC}

# Real tables a backup never reads and a restore never writes. Naming one in an
# uploaded file is not an error (old v1 backups contain `users`) — it is simply
# skipped and reported. Anything *not* in this set and not in _BACKUP_SPEC is
# rejected outright.
_NEVER_TOUCH = frozenset(
    {
        "users",  # password_hash
        "report_tokens",  # shareable bearer credential
        "data_shares",  # would grant cross-user access from a file
        "alembic_version",  # schema bookkeeping
    }
)


def _check_spec() -> None:
    """Fail loudly on a spec that does not match the models."""
    known = set(Base.metadata.tables)
    unknown = {s.table for s in _BACKUP_SPEC} - known
    if unknown:
        raise RuntimeError(f"backup spec names unknown tables: {sorted(unknown)}")
    overlap = {s.table for s in _BACKUP_SPEC} & _NEVER_TOUCH
    if overlap:
        raise RuntimeError(f"backup spec includes forbidden tables: {sorted(overlap)}")
    unclassified = known - {s.table for s in _BACKUP_SPEC} - _NEVER_TOUCH
    if unclassified:
        # Not fatal: the safe default is "not backed up, not restorable".
        logger.warning(
            "Tables absent from the backup spec (excluded from backup/restore): %s",
            sorted(unclassified),
        )


_check_spec()


def _allowed_columns(table_name: str) -> list[str]:
    """The columns of `table_name` that may appear in a backup file."""
    return list(Base.metadata.tables[table_name].columns.keys())


def _json_value(value: Any) -> Any:
    """Make a DB value JSON-serialisable, reversibly.

    Enums are stored by *name* (that is what SQLAlchemy writes to the column,
    and passing the name back on insert round-trips exactly).
    """
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, (datetime, date_type)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _python_value(column: sa.Column, value: Any, table_name: str) -> Any:
    """Turn a JSON value back into what the column's type expects.

    Driven by the column type rather than by guessing at the string's shape,
    so a note that happens to look like a date is not silently turned into one.
    """
    if value is None:
        return None
    try:
        if isinstance(column.type, sa.Enum):
            # The stored name, which SQLAlchemy maps back to the member. Check
            # it here: SQLAlchemy's Enum has validate_strings=False by default,
            # so an unrecognised string is written to the column happily and
            # then raises LookupError on every subsequent *read* — a row that
            # breaks the owner's own account.
            if value not in column.type.enums:
                raise ValueError(f"not one of {column.type.enums}")
            return value
        if isinstance(column.type, sa.DateTime):
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        if isinstance(column.type, sa.Date):
            if isinstance(value, str):
                return date_type.fromisoformat(value)
            return value
        if isinstance(column.type, sa.Boolean):
            return bool(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Backup file has a value that is not valid for "
                f"{table_name}.{column.name}: {value!r}"
            ),
        )
    return value


def _owned_ids(db: Session, user_id: int, table_name: str) -> set[int]:
    """Primary keys of `table_name` currently owned by `user_id`."""
    spec = _SPEC_BY_TABLE[table_name]
    if spec.user_column is None:
        # No nested child-of-a-child today; guard so adding one is noticed.
        raise RuntimeError(f"{table_name} cannot be used as an ownership parent")
    table = Base.metadata.tables[table_name]
    rows = db.execute(
        sa.select(table.c.id).where(table.c[spec.user_column] == user_id)
    ).scalars()
    return set(rows)


def _collect_backup(db: Session, user: User) -> dict[str, Any]:
    """Build the portable JSON backup of one user's own data."""
    tables: dict[str, Any] = {}
    exported_ids: dict[str, set[int]] = {}

    for spec in _BACKUP_SPEC:
        table = Base.metadata.tables[spec.table]
        column_names = _allowed_columns(spec.table)
        stmt = sa.select(*(table.c[name] for name in column_names))

        skip = False
        if spec.user_column is not None:
            stmt = stmt.where(table.c[spec.user_column] == user.id)
        for fk_column, parent in spec.required_parents:
            parent_ids = exported_ids.get(parent, set())
            if not parent_ids:
                skip = True
                break
            stmt = stmt.where(table.c[fk_column].in_(parent_ids))

        rows: list[dict[str, Any]] = []
        if not skip:
            for row in db.execute(stmt.order_by(table.c.id)).mappings():
                rows.append({name: _json_value(row[name]) for name in column_names})

        exported_ids[spec.table] = {r["id"] for r in rows if r.get("id") is not None}
        tables[spec.table] = {"columns": column_names, "rows": rows}
        logger.info("Backed up %d rows from %s", len(rows), spec.table)

    return {
        "version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now().isoformat(),
        "scope": "user",
        "user": {"id": user.id, "username": user.username},
        "tables": tables,
    }


@router.post("/backup")
def backup_database(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a JSON copy of **your own** data.

    Streamed straight back to the caller as an attachment; the server keeps no
    copy. Identical format on SQLite and PostgreSQL, and restorable through
    POST /api/settings/restore. Nobody else's rows are included, and no
    credential column (password hashes, report tokens) exists in the format.
    """
    logger.info("Backup requested by user %s", current_user.email)

    try:
        backup_data = _collect_backup(db, current_user)
    except SQLAlchemyError:
        logger.exception("Backup failed")
        raise HTTPException(status_code=500, detail="Backup failed.")

    content = json.dumps(backup_data, indent=2, default=str).encode("utf-8")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    download_name = f"askesis_backup_{stamp}.json"

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


class RestoreResponse(BaseModel):
    success: bool
    message: str
    tables_restored: list[str] = []
    tables_skipped: list[str] = []
    rows_restored: int = 0
    rows_skipped: int = 0


def _validate_backup(payload: Any) -> tuple[dict[str, Any], list[str]]:
    """Check and decode the uploaded file before anything is written.

    Returns ``(restorable_tables, skipped_table_names)`` with every value
    already coerced to what its column's type expects. Raises 400 on any table,
    column or value the schema does not accept — so a crafted name never
    reaches a query (not even to be rejected by the database), and a malformed
    file cannot leave a half-applied restore behind.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("tables"), dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid backup format: missing 'tables' object.",
        )

    restorable: dict[str, Any] = {}
    skipped: list[str] = []

    for table_name, table_data in payload["tables"].items():
        if not isinstance(table_name, str):
            raise HTTPException(status_code=400, detail="Invalid table name in backup.")
        if table_name in _NEVER_TOUCH:
            # Old v1 backups carried these. Never written; say so rather than
            # failing the whole restore.
            skipped.append(table_name)
            continue
        if table_name not in _SPEC_BY_TABLE:
            raise HTTPException(
                status_code=400,
                detail=f"Backup contains an unrecognised table: {table_name!r}",
            )
        if not isinstance(table_data, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data for table {table_name!r}.",
            )

        columns = table_data.get("columns") or []
        rows = table_data.get("rows") or []
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data for table {table_name!r}.",
            )

        allowed = set(_allowed_columns(table_name))
        unknown = [c for c in columns if not isinstance(c, str) or c not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Backup contains unrecognised column(s) for {table_name}: "
                    f"{sorted(str(c) for c in unknown)}"
                ),
            )
        if any(not isinstance(r, dict) for r in rows):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid row in table {table_name!r}.",
            )

        table = Base.metadata.tables[table_name]
        decoded = [
            {
                name: _python_value(table.c[name], row.get(name), table_name)
                for name in columns
            }
            for row in rows
        ]
        restorable[table_name] = {"columns": columns, "rows": decoded}

    return restorable, skipped


@router.post("/restore", response_model=RestoreResponse)
async def restore_database(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore a JSON backup into **your own** account.

    Rows always land owned by you: the `user_id` in the file is ignored and
    overwritten. Rows whose parent (meal, activity, training plan) is not yours
    are skipped, and rows whose primary key already exists are skipped, so a
    restore is safe to re-run. `users`, `report_tokens` and `data_shares` are
    never written — a restore cannot mint a login, a share, or a credential.
    """
    logger.info("Restore requested by user %s", current_user.email)

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Please upload a JSON backup file.")

    try:
        content = await file.read()
        payload = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")

    restorable, tables_skipped = _validate_backup(payload)

    tables_restored: list[str] = []
    total_inserted = 0
    total_skipped = 0

    try:
        # Spec order, not file order: parents are inserted before their children.
        for spec in _BACKUP_SPEC:
            table_data = restorable.get(spec.table)
            if not table_data or not table_data["rows"]:
                continue

            table = Base.metadata.tables[spec.table]
            columns = [c for c in table_data["columns"] if c != spec.user_column]

            parent_ids = {
                parent: _owned_ids(db, current_user.id, parent)
                for _, parent in spec.required_parents + spec.optional_parents
            }

            inserted = 0
            for row in table_data["rows"]:
                # Values were decoded and type-checked by _validate_backup.
                values = {name: row.get(name) for name in columns}
                # Ownership is asserted, never read from the file.
                if spec.user_column is not None:
                    values[spec.user_column] = current_user.id

                drop_row = False
                for fk_column, parent in spec.required_parents:
                    if values.get(fk_column) not in parent_ids[parent]:
                        drop_row = True
                        break
                if drop_row:
                    total_skipped += 1
                    continue
                for fk_column, parent in spec.optional_parents:
                    if values.get(fk_column) not in parent_ids[parent]:
                        values[fk_column] = None

                try:
                    # SAVEPOINT: a duplicate key must not poison the rows that
                    # come after it (PostgreSQL aborts the whole transaction).
                    with db.begin_nested():
                        db.execute(sa.insert(table).values(**values))
                    inserted += 1
                except IntegrityError:
                    # Already present, or violates a constraint. Expected on a
                    # re-run; skipping is what makes restore idempotent.
                    total_skipped += 1
                except (StatementError, LookupError) as exc:
                    # A value the column's type rejects — a bad enum name, a
                    # number where text is required. One malformed row must not
                    # abort the rest of the file.
                    total_skipped += 1
                    logger.warning("Skipped an unusable %s row: %s", spec.table, exc)

            if inserted:
                db.commit()
                tables_restored.append(f"{spec.table} ({inserted} rows)")
                total_inserted += inserted
                logger.info("Restored %d rows to %s", inserted, spec.table)

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Restore failed")
        raise HTTPException(status_code=500, detail="Restore failed.")

    message = f"Restore completed. {total_inserted} rows restored"
    if total_skipped:
        message += f", {total_skipped} skipped (already present or not yours)"
    message += "."
    if tables_skipped:
        message += (
            f" Ignored non-restorable tables: {', '.join(sorted(tables_skipped))}."
        )

    return RestoreResponse(
        success=True,
        message=message,
        tables_restored=tables_restored,
        tables_skipped=sorted(tables_skipped),
        rows_restored=total_inserted,
        rows_skipped=total_skipped,
    )
