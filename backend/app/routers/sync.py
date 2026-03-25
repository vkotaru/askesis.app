"""
Sync endpoints for offline-first client.

GET  /api/sync/changes?since={timestamp}  — pull server changes since last sync
POST /api/sync/push                       — push client mutations to server
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    User,
    DailyLog,
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
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        since_dt = datetime(1970, 1, 1)

    result: dict[str, list] = {}

    for table_name, model in TABLE_MAP.items():
        # Build filter: updated_at > since OR deleted_at > since
        # This catches both modifications and soft deletes
        filters = [model.updated_at > since_dt]
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
    """Accept a batch of client mutations and apply them."""
    results: list[SyncPushResult] = []

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

            if change.operation == "create":
                server_id = _handle_create(db, model, change, current_user)
                results.append(SyncPushResult(index=i, ok=True, serverId=server_id))

            elif change.operation == "update":
                server_id = _handle_update(db, model, change, current_user)
                results.append(SyncPushResult(index=i, ok=True, serverId=server_id))

            elif change.operation == "delete":
                _handle_delete(db, model, change, current_user)
                results.append(SyncPushResult(index=i, ok=True))

            else:
                results.append(
                    SyncPushResult(
                        index=i,
                        ok=False,
                        error=f"Unknown operation: {change.operation}",
                    )
                )

        except Exception as e:
            logger.warning(f"Sync push failed for change {i}: {e}")
            results.append(SyncPushResult(index=i, ok=False, error=str(e)))

    db.commit()
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

    if model == ProgressPhoto:
        if "view" in data:
            data["view"] = PhotoView(data["view"])

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

    # For DailyLog, check if record already exists for this date (upsert)
    if model == DailyLog and "date" in data:
        existing = (
            db.query(DailyLog)
            .filter(
                DailyLog.user_id == user.id,
                DailyLog.date == data["date"],
                DailyLog.deleted_at.is_(None),
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


def _handle_update(db: Session, model: type, change: SyncChange, user: User) -> int:
    """Update an existing record. Returns server ID."""
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
        client_dt = datetime.fromisoformat(client_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        client_dt = datetime.utcnow()

    if obj.updated_at and obj.updated_at > client_dt:
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

    if model == ProgressPhoto:
        if "view" in data:
            data["view"] = PhotoView(data["view"])

    for key, value in data.items():
        if hasattr(obj, key):
            setattr(obj, key, value)

    obj.updated_at = datetime.utcnow()
    db.flush()
    return obj.id


def _handle_delete(db: Session, model: type, change: SyncChange, user: User) -> None:
    """Soft-delete a record."""
    if not change.serverId:
        return  # Nothing to delete on server

    obj = db.query(model).filter(model.id == change.serverId).first()

    if not obj:
        return  # Already gone

    if hasattr(obj, "user_id") and obj.user_id != user.id:
        raise ValueError("Permission denied")

    obj.deleted_at = datetime.utcnow()
    obj.updated_at = datetime.utcnow()
    db.flush()
