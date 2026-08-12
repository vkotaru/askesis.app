"""
Sync endpoints for offline-first client.

GET  /api/sync/changes?since={timestamp}  — pull server changes since last sync
POST /api/sync/push                       — push client mutations to server
"""

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import Date, or_
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    User,
    DailyLog,
    DailyNutrition,
    Activity,
    Exercise,
    Meal,
    FoodItem,
    BodyMeasurement,
    ProgressPhoto,
    PhotoView,
    ActivityType,
    TimeOfDay,
)
from app.routers.auth import get_current_user

logger = logging.getLogger("askesis.sync")

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class SyncChange(BaseModel):
    table: str
    operation: str  # create, update, delete
    localId: int
    serverId: int | None = None
    data: dict[str, Any] | None = None
    timestamp: str


class SyncPushRequest(BaseModel):
    changes: list[SyncChange]


class SyncPushResult(BaseModel):
    index: int
    ok: bool
    serverId: int | None = None
    error: str | None = None


class SyncPushResponse(BaseModel):
    results: list[SyncPushResult]


# ── Helpers ───────────────────────────────────────────────────────────────────

# Map client table names to SQLAlchemy models
TABLE_MAP = {
    "dailyLogs": DailyLog,
    "dailyNutrition": DailyNutrition,
    "activities": Activity,
    "meals": Meal,
    "foods": FoodItem,
    "measurements": BodyMeasurement,
    "photos": ProgressPhoto,
}


def model_to_dict(obj, include_relationships: bool = False) -> dict:
    """Convert a SQLAlchemy model instance to a dict for JSON response."""
    d: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "value"):  # Enum
            val = val.value
        elif hasattr(val, "isoformat"):  # date
            val = val.isoformat()
        d[col.name] = val

    # Include exercises for activities
    if include_relationships and isinstance(obj, Activity):
        d["exercises"] = [
            {
                "id": ex.id,
                "name": ex.name,
                "sets": ex.sets,
                "reps": ex.reps,
                "weight_kg": ex.weight_kg,
                "notes": ex.notes,
            }
            for ex in obj.exercises
        ]

    # Include food_items for meals
    if include_relationships and isinstance(obj, Meal):
        d["food_items"] = [
            {
                "id": mfi.id,
                "food_item_id": mfi.food_item_id,
                "food_item_name": mfi.food_item.name if mfi.food_item else "",
                "serving_size": mfi.food_item.serving_size if mfi.food_item else 0,
                "serving_unit": mfi.food_item.serving_unit if mfi.food_item else "",
                "quantity": mfi.quantity,
                "calories": round(mfi.food_item.calories * mfi.quantity)
                if mfi.food_item and mfi.food_item.calories
                else None,
                "protein_g": round(mfi.food_item.protein_g * mfi.quantity, 1)
                if mfi.food_item and mfi.food_item.protein_g
                else None,
                "carbs_g": round(mfi.food_item.carbs_g * mfi.quantity, 1)
                if mfi.food_item and mfi.food_item.carbs_g
                else None,
                "fat_g": round(mfi.food_item.fat_g * mfi.quantity, 1)
                if mfi.food_item and mfi.food_item.fat_g
                else None,
                "notes": mfi.notes,
            }
            for mfi in obj.food_items
        ]

    # Convert feelings from comma-separated to list for daily logs
    if isinstance(obj, DailyLog) and d.get("feelings"):
        d["feelings"] = d["feelings"].split(",")

    return d


# ── GET /changes ──────────────────────────────────────────────────────────────


@router.get("/changes")
def get_changes(
    since: str = Query(..., description="ISO timestamp to get changes after"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all rows changed or deleted since the given timestamp."""
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except ValueError:
        since_dt = datetime(1970, 1, 1)

    result: dict[str, list] = {}

    for table_name, model in TABLE_MAP.items():
        # Build filter: updated_at > since OR deleted_at > since
        # This catches both modifications and soft deletes. Not every model
        # has deleted_at (daily_nutrition is upsert-only, never deleted), so
        # only add that clause where the column exists.
        filters = [model.updated_at > since_dt]
        if hasattr(model, "deleted_at"):
            filters.append(model.deleted_at > since_dt)

        query = db.query(model).filter(or_(*filters))

        # Scope to current user
        if hasattr(model, "user_id"):
            query = query.filter(model.user_id == current_user.id)

        rows = query.all()
        if rows:
            include_rels = table_name in ("activities", "meals")
            result[table_name] = [
                model_to_dict(row, include_relationships=include_rels) for row in rows
            ]

    return result


# ── POST /push ────────────────────────────────────────────────────────────────


@router.post("/push", response_model=SyncPushResponse)
def push_changes(
    body: SyncPushRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept a batch of client mutations and apply them.

    Every change is applied in its own transaction and committed on its own.
    That is deliberate, not laziness about batching:

    * The response is per-change, and the client deletes exactly the queue
      entries it was told succeeded. Any scheme where a later failure could
      undo an earlier success (one transaction for the batch, or a savepoint
      per change with a single final commit that can still fail) would have
      the client drop work that was never persisted. Per-change commit is the
      only shape where "ok" means "durable".
    * A failed ``flush`` leaves the session in needs-rollback state, so without
      the rollback below every *subsequent* change in the batch dies with
      ``PendingRollbackError`` and the final commit turns the whole request
      into a 500 — which makes the client keep the entire batch queued and
      retry the same poison forever. One bad row must never wedge the queue.
    """
    results: list[SyncPushResult] = []

    # (table, localId) -> the server id this batch just assigned to that client
    # row. A client that created a row offline has no server id to send for the
    # follow-up update/delete it queued against the same localId, so resolve it
    # here from the create that came earlier in the same batch. Without this an
    # offline create+delete pair leaves the row alive on the server, and an
    # offline create+update pair inserts a second copy.
    created_ids: dict[tuple[str, int], int] = {}

    for i, change in enumerate(body.changes):
        try:
            model = TABLE_MAP.get(change.table)
            if not model:
                results.append(
                    SyncPushResult(
                        index=i, ok=False, error=f"Unknown table: {change.table}"
                    )
                )
                continue

            created_in_batch = False
            if not change.serverId:
                known = created_ids.get((change.table, change.localId))
                if known is not None:
                    change = change.model_copy(update={"serverId": known})
                    created_in_batch = True

            if change.operation == "create":
                server_id = _handle_create(db, model, change, current_user)

            elif change.operation == "update":
                server_id = _handle_update(
                    db, model, change, current_user, created_in_batch=created_in_batch
                )

            elif change.operation == "delete":
                _handle_delete(db, model, change, current_user)
                server_id = None

            else:
                results.append(
                    SyncPushResult(
                        index=i,
                        ok=False,
                        error=f"Unknown operation: {change.operation}",
                    )
                )
                continue

            db.commit()

            if server_id is not None:
                created_ids[(change.table, change.localId)] = server_id

            results.append(SyncPushResult(index=i, ok=True, serverId=server_id))

        except Exception as e:
            # Discard this change's partial work and hand the session back
            # usable, so the next change in the batch starts clean.
            db.rollback()
            logger.warning(f"Sync push failed for change {i}: {e}")
            results.append(SyncPushResult(index=i, ok=False, error=str(e)))

    return SyncPushResponse(results=results)


# ── Mutation handlers ─────────────────────────────────────────────────────────

# Fields to exclude from client data before setting on model
_EXCLUDE_FIELDS = {
    "localId",
    "serverId",
    "updatedAt",
    "updated_at",
    "created_at",
    "id",
    "user_id",
    "userId",
}


def _clean_data(data: dict | None) -> dict:
    """Remove client-only fields and convert camelCase keys."""
    if not data:
        return {}
    return {k: v for k, v in data.items() if k not in _EXCLUDE_FIELDS}


def _coerce_column_types(model: type, data: dict) -> dict:
    """Convert ISO date strings into date objects for Date columns.

    The client always sends dates as "YYYY-MM-DD". Postgres accepts that
    string as a literal, SQLite refuses it outright, so normalise here and
    both backends behave the same.
    """
    out = dict(data)
    for col in model.__table__.columns:
        value = out.get(col.name)
        if isinstance(value, str) and isinstance(col.type, Date):
            try:
                out[col.name] = date.fromisoformat(value)
            except ValueError:
                pass  # Leave it alone and let the DB reject it
    return out


def _handle_create(db: Session, model: type, change: SyncChange, user: User) -> int:
    """Create a new record from client data. Returns server ID."""
    data = _clean_data(change.data)

    # Handle special fields
    if model == DailyLog:
        if "feelings" in data and isinstance(data["feelings"], list):
            data["feelings"] = ",".join(data["feelings"])

    if model == Activity:
        exercises_data = data.pop("exercises", [])
        if "activity_type" in data:
            data["activity_type"] = ActivityType(data["activity_type"])
        if "time_of_day" in data and data["time_of_day"]:
            data["time_of_day"] = TimeOfDay(data["time_of_day"])

    if model == Meal:
        data.pop("food_items", None)
        data.pop("photo_url", None)
        data.pop("computed_calories", None)
        data.pop("computed_protein_g", None)
        data.pop("computed_carbs_g", None)
        data.pop("computed_fat_g", None)

    if model == ProgressPhoto:
        if "view" in data:
            data["view"] = PhotoView(data["view"])

    # Strip any keys that aren't actual model columns to prevent constructor errors
    model_columns = {c.name for c in model.__table__.columns}
    data = {k: v for k, v in data.items() if k in model_columns}
    data = _coerce_column_types(model, data)

    # Check for existing record with same serverId (dedup)
    if change.serverId:
        existing = db.query(model).filter(model.id == change.serverId).first()
        if existing and hasattr(existing, "user_id") and existing.user_id == user.id:
            # Already exists — treat as update
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing.id

    # DailyLog and BodyMeasurement are one-row-per-date by design — the UI edits
    # "the log for this day" / "the measurements for this day", and the client
    # looks a row up by date before writing — so a create pushed for a date that
    # already has a row must upsert. Nothing at the DB level enforces that:
    # daily_nutrition is the only one of the three with a UniqueConstraint on
    # (user_id, date); these two carry a plain non-unique Index. Without this
    # branch a second offline create for the same date just inserts a twin.
    if model in (DailyLog, BodyMeasurement) and "date" in data:
        existing = (
            db.query(model)
            .filter(
                model.user_id == user.id,
                model.date == data["date"],
                model.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            for key, value in data.items():
                if key != "date" and hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing.id

    # DailyNutrition has a UniqueConstraint on (user_id, date) and no
    # deleted_at, so a re-pushed row must upsert instead of insert.
    if model == DailyNutrition and "date" in data:
        existing = (
            db.query(DailyNutrition)
            .filter(
                DailyNutrition.user_id == user.id,
                DailyNutrition.date == data["date"],
            )
            .first()
        )
        if existing:
            for key, value in data.items():
                if key != "date" and hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing.id

    obj = model(user_id=user.id, **data)
    obj.updated_at = datetime.utcnow()
    db.add(obj)
    db.flush()

    # Handle exercises for activities
    if model == Activity and exercises_data:
        for ex_data in exercises_data:
            ex = Exercise(
                activity_id=obj.id,
                name=ex_data.get("name", ""),
                sets=ex_data.get("sets"),
                reps=ex_data.get("reps"),
                weight_kg=ex_data.get("weight_kg"),
                notes=ex_data.get("notes"),
            )
            db.add(ex)

    return obj.id


def _handle_update(
    db: Session,
    model: type,
    change: SyncChange,
    user: User,
    created_in_batch: bool = False,
) -> int:
    """Update an existing record. Returns server ID.

    ``created_in_batch`` says the row this update targets was inserted by an
    earlier change in this same push, so its ``updated_at`` is the moment of
    the push rather than a real edit from another device. The server-wins
    check below must be skipped in that case: it would compare the client's
    (older, offline) edit timestamp against a server timestamp the client just
    caused, and throw the edit away.
    """
    if not change.serverId:
        # No server ID — might be a create that was queued as update
        return _handle_create(db, model, change, user)

    obj = db.query(model).filter(model.id == change.serverId).first()

    if not obj:
        # Record doesn't exist — create it
        return _handle_create(db, model, change, user)

    # Verify ownership
    if hasattr(obj, "user_id") and obj.user_id != user.id:
        raise ValueError("Permission denied")

    # Server-wins conflict resolution: compare timestamps
    client_ts = change.timestamp
    try:
        client_dt = datetime.fromisoformat(client_ts.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except (ValueError, AttributeError):
        client_dt = datetime.utcnow()

    if not created_in_batch and obj.updated_at and obj.updated_at > client_dt:
        # Server version is newer — skip this update (server wins)
        return obj.id

    data = _clean_data(change.data)

    if model == DailyLog:
        if "feelings" in data and isinstance(data["feelings"], list):
            data["feelings"] = ",".join(data["feelings"])

    if model == Activity:
        exercises_data = data.pop("exercises", [])
        if "activity_type" in data:
            data["activity_type"] = ActivityType(data["activity_type"])
        if "time_of_day" in data and data["time_of_day"]:
            data["time_of_day"] = TimeOfDay(data["time_of_day"])

        # Replace exercises
        if exercises_data:
            db.query(Exercise).filter(Exercise.activity_id == obj.id).delete()
            for ex_data in exercises_data:
                ex = Exercise(
                    activity_id=obj.id,
                    name=ex_data.get("name", ""),
                    sets=ex_data.get("sets"),
                    reps=ex_data.get("reps"),
                    weight_kg=ex_data.get("weight_kg"),
                    notes=ex_data.get("notes"),
                )
                db.add(ex)

    if model == Meal:
        data.pop("food_items", None)
        data.pop("photo_url", None)
        data.pop("computed_calories", None)
        data.pop("computed_protein_g", None)
        data.pop("computed_carbs_g", None)
        data.pop("computed_fat_g", None)

    if model == ProgressPhoto:
        if "view" in data:
            data["view"] = PhotoView(data["view"])

    # Only set actual model columns
    model_columns = {c.name for c in model.__table__.columns}
    data = _coerce_column_types(model, data)
    for key, value in data.items():
        if key in model_columns:
            setattr(obj, key, value)

    obj.updated_at = datetime.utcnow()
    db.flush()
    return obj.id


def _handle_delete(db: Session, model: type, change: SyncChange, user: User) -> None:
    """Soft-delete a record."""
    if not change.serverId:
        # No server id, and `push_changes` could not resolve one from a create
        # earlier in this batch, so this row has never reached the server and
        # there is nothing here to delete. (A client that pushed the create in
        # an earlier batch must have written the returned serverId back onto
        # its queued delete — see `applyServerIds` in frontend/src/lib/sync.ts.)
        return

    obj = db.query(model).filter(model.id == change.serverId).first()

    if not obj:
        return  # Already gone

    if hasattr(obj, "user_id") and obj.user_id != user.id:
        raise ValueError("Permission denied")

    # Not every synced model carries a tombstone column — DailyNutrition, for
    # one, is upsert-only and has no deleted_at. Setting the attribute anyway
    # would just bind a stray instance attribute that never reaches SQL (or
    # raise, on a model with __slots__), leaving the row silently alive. Hard
    # delete those instead: with no deleted_at there is nothing for
    # /api/sync/changes to hand clients as a tombstone anyway.
    if hasattr(type(obj), "deleted_at"):
        obj.deleted_at = datetime.utcnow()
        obj.updated_at = datetime.utcnow()
    else:
        db.delete(obj)
    db.flush()
