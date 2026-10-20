"""Log a body weight, or a finished workout, from the MCP connector.

**The second slice of logged history the connector may write** (the first is
food intake, `app/intake_log.py`). Kept as narrow as the database role allows,
and the role (`scripts/mcp_db_role.sql`) is what makes the narrowness real:

* **weight**: one column of `daily_logs`. The role may INSERT a day's row and
  UPDATE `weight`, `sources` and `updated_at` on it -- not sleep, steps, notes
  or anything else on that row. The value is stamped `manual`, because a
  person said it, so the Garmin importer never overwrites it.
* **workouts**: INSERT only, on `activities`, `exercises` and `exercise_sets`.
  The connector can add a session; it cannot edit or delete one, here or
  anywhere. A wrong session is fixed in the app.

Same contract as `planning.py`: plain SQLAlchemy, no FastAPI, nothing here
commits. The bounds restate `routers/activities.py`'s schemas, because this
package cannot import the routers; keep them at least as strict.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityType,
    DailyLog,
    Exercise,
    ExerciseSet,
    TimeOfDay,
)
from app.planning import catalog_by_name
from app.provenance import mark_manual

#: DailyLogCreate's bounds. A weight outside them is a misread, not a person.
MIN_WEIGHT_KG = 20.0
MAX_WEIGHT_KG = 500.0

#: ActivityCreate / ExerciseCreate / ExerciseSetCreate, restated.
MAX_NAME = 100
MAX_NOTES = 2000
MAX_EXERCISE_NOTES = 500
MAX_SET_NOTES = 255
MAX_EXERCISES = 50
MAX_SETS = 50
SET_TYPES = ("warmup", "working", "drop", "failure", "cooldown")
_SET_BOUNDS: dict[str, tuple[float, float, type]] = {
    "weight_kg": (0, 1000, float),
    "reps": (0, 1000, int),
    "duration_seconds": (0, 86400, int),
    "distance_m": (0, 100000, float),
    "rpe": (0, 10, float),
}


class HistoryError(ValueError):
    """A bad request, phrased to be read by a person or a model."""


# ── weight ──────────────────────────────────────────────────────────────────


def log_weight(db: Session, user_id: int, day: date, weight_kg: Any) -> dict[str, Any]:
    """Set the day's weight, creating the day's row if there is none."""
    if isinstance(weight_kg, bool) or not isinstance(weight_kg, (int, float)):
        raise HistoryError("weight_kg must be a number of kilograms.")
    value = round(float(weight_kg), 2)
    if not MIN_WEIGHT_KG <= value <= MAX_WEIGHT_KG:
        raise HistoryError(
            f"{value} kg is outside {MIN_WEIGHT_KG:g}-{MAX_WEIGHT_KG:g} kg -- "
            "check the unit (pounds need converting) or a misread digit."
        )
    log = (
        db.query(DailyLog)
        .filter(
            DailyLog.user_id == user_id,
            DailyLog.date == day,
            DailyLog.deleted_at.is_(None),
        )
        .first()
    )
    before = log.weight if log else None
    if log is None:
        # A Core insert naming its columns, not `db.add(DailyLog(...))`: the ORM
        # INSERT lists *every* column, NULLs included, and the role may insert
        # only these, plus `ate_outside`, which SQLAlchemy adds from its default
        # (scripts/mcp_db_role.sql). Postgres checks the column list, not the
        # values, so the ORM form is refused there -- and passes on the SQLite
        # every local check runs on. A column given a Python default later
        # needs adding to that grant.
        now = datetime.utcnow()
        db.execute(
            insert(DailyLog).values(
                user_id=user_id,
                date=day,
                weight=value,
                sources=mark_manual(None, ["weight"]),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        # The ORM UPDATE sends only what changed: weight, sources, updated_at.
        log.weight = value
        log.sources = mark_manual(log.sources, ["weight"])
    db.flush()
    return {
        "date": day.isoformat(),
        "result": "set" if before is None else "updated",
        "before_kg": before,
        "weight_kg": value,
    }


# ── workouts ────────────────────────────────────────────────────────────────


def _text(value: Any, limit: int, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HistoryError(f"{field} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise HistoryError(
            f"{field} is too long: {len(value)} characters, max {limit}."
        )
    return value or None


def _number(raw: dict, key: str, where: str) -> Any:
    value = raw.get(key)
    if value is None:
        return None
    low, high, cast = _SET_BOUNDS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryError(f"{where}: {key} must be a number.")
    if cast is int and value != int(value):
        raise HistoryError(f"{where}: {key} must be a whole number.")
    value = cast(value)
    if not low <= value <= high:
        raise HistoryError(f"{where}: {key} must be between {low:g} and {high:g}.")
    return value


def _clean_set(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HistoryError(f"{where} must be an object.")
    unknown = set(raw) - {*_SET_BOUNDS, "set_type", "notes"}
    if unknown:
        raise HistoryError(f"{where}: unknown field(s) {sorted(unknown)}.")
    out = {k: _number(raw, k, where) for k in _SET_BOUNDS}
    if all(v is None for v in out.values()):
        raise HistoryError(
            f"{where} is empty: give reps, weight_kg, duration_seconds or distance_m."
        )
    set_type = raw.get("set_type") or "working"
    if set_type not in SET_TYPES:
        raise HistoryError(f"{where}: set_type must be one of {', '.join(SET_TYPES)}.")
    out["set_type"] = set_type
    out["notes"] = _text(raw.get("notes"), MAX_SET_NOTES, f"{where} notes")
    return out


def log_workout(
    db: Session,
    user_id: int,
    day: date,
    name: Any,
    activity_type: str = "strength",
    exercises: list | None = None,
    duration_mins: Any = None,
    time_of_day: str | None = None,
    notes: Any = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Add one finished session, with its movements and sets. Never edits one.

    Validates everything before adding anything. A session with the same name
    on the same day is refused unless `allow_duplicate`, because the likeliest
    way to get one is a model retrying a call that already succeeded.
    """
    title = _text(name, MAX_NAME, "name")
    if not title:
        raise HistoryError("name is required, e.g. 'Morning stretch'.")
    try:
        kind = ActivityType(activity_type)
    except ValueError:
        raise HistoryError("activity_type must be 'strength' or 'cardio'.") from None
    when = None
    if time_of_day is not None:
        try:
            when = TimeOfDay(time_of_day)
        except ValueError:
            raise HistoryError(
                "time_of_day must be morning, afternoon, evening or night."
            ) from None
    minutes = None
    if duration_mins is not None:
        if (
            isinstance(duration_mins, bool)
            or not isinstance(duration_mins, (int, float))
            or not 1 <= duration_mins <= 1440
        ):
            raise HistoryError("duration_mins must be between 1 and 1440.")
        minutes = round(duration_mins)
    session_notes = _text(notes, MAX_NOTES, "notes")

    items = exercises or []
    if not isinstance(items, list):
        raise HistoryError("exercises must be a list.")
    if len(items) > MAX_EXERCISES:
        raise HistoryError(f"At most {MAX_EXERCISES} exercises per session.")
    planned: list[dict[str, Any]] = []
    for i, raw in enumerate(items, start=1):
        where = f"exercise {i}"
        if not isinstance(raw, dict):
            raise HistoryError(f"{where} must be an object with a name and sets.")
        ex_name = _text(raw.get("name"), MAX_NAME, f"{where} name")
        if not ex_name:
            raise HistoryError(f"{where} needs a name.")
        sets = raw.get("sets") or []
        if not isinstance(sets, list) or len(sets) > MAX_SETS:
            raise HistoryError(f"{ex_name}: sets must be a list of at most {MAX_SETS}.")
        entry = catalog_by_name(db, user_id, ex_name)
        planned.append(
            {
                "name": entry.name if entry else ex_name,
                "catalog_id": entry.id if entry else None,
                "notes": _text(
                    raw.get("notes"), MAX_EXERCISE_NOTES, f"{ex_name} notes"
                ),
                "sets": [
                    _clean_set(s, f"{ex_name} set {n}") for n, s in enumerate(sets, 1)
                ],
            }
        )
    if not planned and minutes is None and not session_notes:
        raise HistoryError(
            "Nothing to log: give the exercises done, a duration or notes."
        )

    if not allow_duplicate:
        twin = (
            db.query(Activity)
            .filter(
                Activity.user_id == user_id,
                Activity.date == day,
                Activity.name == title,
                Activity.deleted_at.is_(None),
            )
            .first()
        )
        if twin is not None:
            raise HistoryError(
                f"'{title}' is already logged on {day} (id {twin.id}). If this "
                "really is a second session, call again with allow_duplicate=true."
            )

    activity = Activity(
        user_id=user_id,
        date=day,
        name=title,
        activity_type=kind,
        time_of_day=when,
        duration_mins=minutes,
        notes=session_notes,
    )
    db.add(activity)
    db.flush()
    for position, item in enumerate(planned):
        ex = Exercise(
            activity_id=activity.id,
            catalog_id=item["catalog_id"],
            name=item["name"],
            position=position,
            notes=item["notes"],
        )
        db.add(ex)
        db.flush()
        for number, fields in enumerate(item["sets"], start=1):
            db.add(ExerciseSet(exercise_id=ex.id, set_number=number, **fields))
    db.flush()
    return {
        "id": activity.id,
        "date": day.isoformat(),
        "name": title,
        "activity_type": kind.value,
        "exercises": [
            {
                "name": p["name"],
                "sets": len(p["sets"]),
                "in_library": bool(p["catalog_id"]),
            }
            for p in planned
        ],
        "not_in_library": [p["name"] for p in planned if not p["catalog_id"]],
    }
