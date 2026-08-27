"""The read-only tool implementations.

Deliberately **plain functions** taking ``(db, user_id, ...)`` and returning
plain dicts. Nothing here imports the MCP SDK, so every tool can be exercised
from a shell against a real database before any protocol, auth or container
exists — and stays that way, which is the only test harness this repo has.

``mcp_server/server.py`` is the thin layer that registers these with the SDK.

──────────────────────────────────────────────────────────────────────────────
THE UNIT RULE, which every one of these functions obeys:

**Every numeric field carries its unit in its own name, and every number is
canonical metric.** ``weight_kg``, ``distance_km``, ``waist_cm``, ``water_ml``,
``protein_g``. There is never a bare ``weight`` beside a separate
``weight_unit`` label.

That pattern is a live bug in ``GET /api/report/{token}``, which returns the
user's display *preference* string ("lb") next to an unconverted kilogram
number. A model reading that believes the label. Nothing here repeats it.

Dual emission (``weight_kg`` *and* ``weight_lb``) is also rejected: it invites
a model to quote both in one sentence or sum across representations.

The user's display preference is surfaced exactly once, in `get_profile`,
explicitly labelled as a preference rather than a unit of measure.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.disciplines import DISCIPLINE_BY_KEY, DISCIPLINE_KEYS, classify, parse_plan
from app.models import (
    Activity,
    BodyMeasurement,
    DailyLog,
    DailyNutrition,
    Meal,
    MealFoodItem,
    PlannedWorkout,
    TrainingPlan,
    TrainingPlanStatus,
    User,
    UserSettings,
)
from app.provenance import parse_sources
from mcp_server.queries import (
    MAX_ROWS,
    by_id,
    capped,
    children_of,
    clamp_limit,
    in_range,
    iso,
    owned,
)

#: Widest window a single call may ask for. A model asked for "this year" will
#: happily request 365 days of joined rows; this makes it say so out loud
#: instead of returning a wall of text.
MAX_DAYS = 180

MEASUREMENT_FIELDS = (
    "neck",
    "shoulders",
    "chest",
    "bicep_left",
    "bicep_right",
    "forearm_left",
    "forearm_right",
    "waist",
    "abdomen",
    "hips",
    "thigh_left",
    "thigh_right",
    "calf_left",
    "calf_right",
)


class ToolError(ValueError):
    """A bad argument. Surfaced to the model as an error result, not a crash."""


#: Postgres ``integer`` bound. A larger value reaches the driver and raises
#: NumericValueOutOfRange, whose SQLAlchemy message embeds the full SELECT --
#: column list and bound parameters included. Reject it before it gets there.
_MAX_PG_INT = 2**31 - 1


def _row_id(value: object, field: str) -> int:
    """Validate an id argument coming from a language model."""
    if type(value) is not int or isinstance(value, bool):
        raise ToolError(f"{field} must be an integer, got {value!r}")
    if not 0 < value <= _MAX_PG_INT:
        raise ToolError(f"{field} is out of range: {value}")
    return value


# ── helpers ──────────────────────────────────────────────────────────────────


def _window(
    start: str | None, end: str | None, default_days: int = 30
) -> tuple[date_type, date_type]:
    """Parse and sanity-check a date window, defaulting to the last N days."""
    today = date_type.today()  # noqa: DTZ011 - civil date, matching how the app keys days
    try:
        e = date_type.fromisoformat(end) if end else today
        s = (
            date_type.fromisoformat(start)
            if start
            else e - timedelta(days=default_days - 1)
        )
    except (ValueError, TypeError) as exc:
        raise ToolError(f"Dates must be ISO-8601 (YYYY-MM-DD): {exc}") from exc
    if s > e:
        raise ToolError(f"start_date {s} is after end_date {e}")
    span = (e - s).days + 1
    if span > MAX_DAYS:
        raise ToolError(
            f"Range is {span} days; the maximum is {MAX_DAYS}. "
            f"Ask for a narrower window, or several in sequence."
        )
    return s, e


def _settings(db: Session, user_id: int) -> UserSettings | None:
    return owned(db, UserSettings, user_id).one_or_none()


def _meal_calories(meal: Meal) -> int | None:
    """A meal's calories: its own figure, else summed from its linked foods.

    **This deliberately diverges from what the web UI shows.** The dashboard,
    the nutrition page and the shared report all read ``meal.calories`` alone
    (nothing consumes the API's ``computed_calories``), so a meal logged purely
    as food items reads as 0 there and as its real total here. That is the
    right answer for an assistant being asked "how much did I eat", but it
    means a figure from this server can legitimately exceed the one on screen.

    The per-item rounding matches ``_compute_meal_nutrition`` in
    ``app/routers/nutrition.py`` so the two agree to the calorie rather than
    drifting by half a kcal per item. Soft-deleted food rows are skipped --
    ``link.food_item`` is a plain relationship with no ``deleted_at`` filter of
    its own, which is the one place data reaches a response without passing
    through `owned()`.
    """
    if meal.calories is not None:
        return meal.calories
    total = 0
    seen = False
    for link in meal.food_items:
        food = link.food_item
        if food is None or food.deleted_at is not None:
            continue
        if food.calories:
            total += round(food.calories * (link.quantity or 0))
            seen = True
    return total if seen else None


#: Eager-loads the meal -> link -> food chain. Without it each meal costs two
#: extra queries; a 180-day summary is ~1,100 round trips for one tool call,
#: against a connection pool shared with the app.
_MEAL_LOAD = (selectinload(Meal.food_items).selectinload(MealFoodItem.food_item),)


# ── 1. orientation ───────────────────────────────────────────────────────────


def get_profile(db: Session, user_id: int) -> dict[str, Any]:
    """Who this is, what they're aiming at, and what data exists to ask about."""
    user = by_id(db, User, user_id)
    if user is None:
        raise ToolError("This account no longer exists.")
    st = _settings(db, user_id)

    def _span(model: type) -> dict[str, Any]:
        q = owned(db, model, user_id)
        first = q.order_by(model.date.asc()).first()
        last = q.order_by(model.date.desc()).first()
        return {
            "first": iso(first.date) if first else None,
            "last": iso(last.date) if last else None,
            "count": q.count(),
        }

    return {
        # `username` is deliberately omitted. It is half of the app's login
        # credential, and the login throttle is keyed on the submitted
        # identifier -- so shipping it off the box lets anyone who has seen one
        # response lock the real account out. `name` identifies the person.
        "account": {"name": user.name},
        "display_preferences": {
            "_note": (
                "These are the user's UI preferences, NOT the units of the numbers "
                "in any response. Every numeric field from every tool on this server "
                "is metric, as stated in its field name (weight_kg, distance_km, "
                "waist_cm). Convert only when writing prose for the user."
            ),
            # Suffixed `_unit` so this block cannot be mistaken for data even
            # when a model sees it out of context: there is no key anywhere in
            # this server whose value is a number and whose name lacks a unit.
            "weight_unit": (st.weight_unit if st else "kg"),
            "distance_unit": (st.distance_unit if st else "km"),
            "measurement_unit": (st.measurement_unit if st else "cm"),
            "water_unit": (st.water_unit if st else "ml"),
        },
        "targets": {
            "calorie_target_kcal": st.calorie_target if st else None,
            "protein_target_g": st.protein_target if st else None,
            "weekly_run_km": st.weekly_run_km if st else None,
            "weekly_bike_km": st.weekly_bike_km if st else None,
            "weekly_disciplines": parse_plan(st.weekly_disciplines if st else None),
        },
        "data_available": {
            "daily_logs": _span(DailyLog),
            "activities": _span(Activity),
            "meals": _span(Meal),
            "measurements": _span(BodyMeasurement),
        },
        "disciplines_understood": list(DISCIPLINE_KEYS),
    }


# ── 2. the workhorse ─────────────────────────────────────────────────────────


def get_daily_summary(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """One row per day: log, nutrition, meal calories and an activity roll-up.

    Days with no data are returned as explicit null-filled rows rather than
    omitted, so a gap is visibly a gap and not an absence the model has to
    infer from a missing key.
    """
    start, end = _window(start_date, end_date)

    logs = {
        log.date: log
        for log in in_range(owned(db, DailyLog, user_id), DailyLog, start, end).all()
    }
    nutrition = {
        n.date: n
        for n in in_range(
            owned(db, DailyNutrition, user_id), DailyNutrition, start, end
        ).all()
    }

    meal_kcal: dict[date_type, int] = defaultdict(int)
    meal_count: dict[date_type, int] = defaultdict(int)
    for meal in (
        in_range(owned(db, Meal, user_id), Meal, start, end).options(*_MEAL_LOAD).all()
    ):
        kcal = _meal_calories(meal)
        if kcal is not None:
            meal_kcal[meal.date] += kcal
        meal_count[meal.date] += 1

    acts: dict[date_type, list[Activity]] = defaultdict(list)
    for act in in_range(owned(db, Activity, user_id), Activity, start, end).all():
        acts[act.date].append(act)

    days = []
    for offset in range((end - start).days + 1):
        d = start + timedelta(days=offset)
        log = logs.get(d)
        nut = nutrition.get(d)
        day_acts = acts.get(d, [])
        disciplines = sorted({k for k in (classify(a) for a in day_acts) if k})
        sources = parse_sources(log.sources) if log else {}
        days.append(
            {
                "date": iso(d),
                "weight_kg": log.weight if log else None,
                "sleep_hours": log.sleep_hours if log else None,
                "steps": log.steps if log else None,
                "water_ml": log.water_ml if log else None,
                "caffeine_mg": log.caffeine_mg if log else None,
                "feelings": (
                    [f for f in (log.feelings or "").split(",") if f] if log else []
                ),
                "ate_outside": log.ate_outside if log else None,
                "notes": log.notes if log else None,
                "calories_kcal": meal_kcal.get(d),
                "meal_count": meal_count.get(d, 0),
                "protein_g": nut.protein_g if nut else None,
                "carbs_g": nut.carbs_g if nut else None,
                "fat_g": nut.fat_g if nut else None,
                "activity_count": len(day_acts),
                # `if day_acts` rather than `or None`: a strength session with
                # no duration recorded is a real zero, and must not read as
                # "no activity that day".
                "activity_minutes": (
                    sum(a.duration_mins or 0 for a in day_acts) if day_acts else None
                ),
                "activity_distance_km": (
                    round(sum(a.distance_km or 0 for a in day_acts), 3)
                    if day_acts
                    else None
                ),
                "disciplines": disciplines,
                # Which fields came from a device rather than the user's own hands.
                "sources": sources or None,
            }
        )

    return {
        "start_date": iso(start),
        "end_date": iso(end),
        "days": days,
        "_units": (
            "weight_kg=kilograms, water_ml=millilitres, distance_km=kilometres, "
            "calories_kcal=kcal, protein_g/carbs_g/fat_g=grams"
        ),
        "_note": (
            "calories_kcal is summed from logged meals. protein_g/carbs_g/fat_g "
            "come from the separate daily-nutrition record, which is entered by "
            "hand -- they are null for days the user logged meals but no macros, "
            "which is not the same as zero."
        ),
    }


# ── 3. the tool that justifies the connector ─────────────────────────────────


def get_weekly_review(
    db: Session, user_id: int, week_of: str | None = None
) -> dict[str, Any]:
    """Monday–Sunday: distance and disciplines against the weekly plan.

    Week boundaries match the app's own (``today - timedelta(days=weekday())``),
    so this agrees with the dashboard rather than quietly using a different week.
    """
    try:
        anchor = date_type.fromisoformat(week_of) if week_of else date_type.today()  # noqa: DTZ011
    except ValueError as exc:
        raise ToolError(f"week_of must be ISO-8601 (YYYY-MM-DD): {exc}") from exc

    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    st = _settings(db, user_id)

    activities = in_range(owned(db, Activity, user_id), Activity, monday, sunday).all()
    by_discipline: dict[str, dict[str, Any]] = {}
    unclassified = 0
    for act in activities:
        key = classify(act)
        if key is None:
            unclassified += 1
            continue
        slot = by_discipline.setdefault(
            key,
            {
                "label": DISCIPLINE_BY_KEY[key].label,
                "sessions": 0,
                "minutes": 0,
                "distance_km": 0.0,
            },
        )
        slot["sessions"] += 1
        slot["minutes"] += act.duration_mins or 0
        slot["distance_km"] += act.distance_km or 0.0
    for slot in by_discipline.values():
        slot["distance_km"] = round(slot["distance_km"], 3)

    planned = parse_plan(st.weekly_disciplines if st else None)
    done = set(by_discipline)

    def _target(actual_key: str, target: float | None) -> dict[str, Any] | None:
        if not target:
            return None
        actual = by_discipline.get(actual_key, {}).get("distance_km", 0.0)
        return {
            "actual_km": round(actual, 3),
            "target_km": target,
            "hit": actual >= target,
            "remaining_km": round(max(0.0, target - actual), 3),
        }

    # ORDER BY is load-bearing, not tidiness: weight_change_kg is first-vs-last,
    # and an unordered scan returns heap order on Postgres, so one backfilled
    # day flips the sign and the model reports a gain in a week you lost.
    logs = (
        in_range(owned(db, DailyLog, user_id), DailyLog, monday, sunday)
        .order_by(DailyLog.date.asc())
        .all()
    )
    weights = [(log.date, log.weight) for log in logs if log.weight is not None]
    sleeps = [log.sleep_hours for log in logs if log.sleep_hours is not None]
    steps = [log.steps for log in logs if log.steps is not None]

    meals_kcal: dict[date_type, int] = defaultdict(int)
    for meal in (
        in_range(owned(db, Meal, user_id), Meal, monday, sunday)
        .options(*_MEAL_LOAD)
        .all()
    ):
        kcal = _meal_calories(meal)
        if kcal is not None:
            meals_kcal[meal.date] += kcal
    nut = in_range(
        owned(db, DailyNutrition, user_id), DailyNutrition, monday, sunday
    ).all()
    proteins = [n.protein_g for n in nut if n.protein_g is not None]

    cal_target = st.calorie_target if st else None
    pro_target = st.protein_target if st else None

    return {
        "week_start": iso(monday),
        "week_end": iso(sunday),
        "distance_targets": {
            "run": _target("run", st.weekly_run_km if st else None),
            "bike": _target("bike", st.weekly_bike_km if st else None),
        },
        "disciplines": {
            "planned": planned,
            "done": sorted(done & set(planned)),
            "missed": sorted(set(planned) - done),
            "unplanned_done": sorted(done - set(planned)),
        },
        "by_discipline": by_discipline,
        "activities_unclassified": unclassified,
        "nutrition": {
            "days_with_calorie_data": len(meals_kcal),
            "mean_calories_kcal": (
                round(sum(meals_kcal.values()) / len(meals_kcal))
                if meals_kcal
                else None
            ),
            "calorie_target_kcal": cal_target,
            "days_at_or_under_calorie_target": (
                sum(1 for v in meals_kcal.values() if v <= cal_target)
                if cal_target
                else None
            ),
            "mean_protein_g": round(sum(proteins) / len(proteins), 1)
            if proteins
            else None,
            "protein_target_g": pro_target,
            "days_at_or_over_protein_target": (
                sum(1 for p in proteins if p >= pro_target) if pro_target else None
            ),
        },
        "wellness": {
            "mean_sleep_hours": round(sum(sleeps) / len(sleeps), 2) if sleeps else None,
            "nights_logged": len(sleeps),
            "mean_steps": round(sum(steps) / len(steps)) if steps else None,
            "days_stepped": len(steps),
            "weight_first_kg": weights[0][1] if weights else None,
            "weight_last_kg": weights[-1][1] if weights else None,
            "weight_change_kg": (
                round(weights[-1][1] - weights[0][1], 2) if len(weights) > 1 else None
            ),
        },
    }


# ── 4-5. activities ──────────────────────────────────────────────────────────


def list_activities(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    discipline: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Activities in a window, with the discipline resolved server-side."""
    if discipline is not None and discipline not in DISCIPLINE_BY_KEY:
        raise ToolError(
            f"Unknown discipline {discipline!r}. Known: {', '.join(DISCIPLINE_KEYS)}"
        )
    limit = clamp_limit(limit, 200)
    start, end = _window(start_date, end_date)
    # Activity.id as a tie-break: without it, rows within one day come back in
    # planner order, so the slice below cuts arbitrarily -- and differently on
    # SQLite vs Postgres.
    q = in_range(owned(db, Activity, user_id), Activity, start, end).order_by(
        Activity.date.desc(), Activity.id.desc()
    )
    # Discipline is computed, not stored, so it cannot be a SQL filter: fetch
    # the window, then filter. capped() bounds the fetch itself -- MAX_DAYS
    # alone does not, since one day can hold any number of activities.
    rows, window_truncated = capped(q, MAX_ROWS)
    out = []
    for act in rows:
        key = classify(act)
        if discipline is not None and key != discipline:
            continue
        out.append(
            {
                "id": act.id,
                "date": iso(act.date),
                "name": act.name,
                "discipline": key,
                "activity_type": getattr(act.activity_type, "value", act.activity_type),
                "time_of_day": getattr(act.time_of_day, "value", act.time_of_day),
                "duration_mins": act.duration_mins,
                "distance_km": act.distance_km,
                "calories_kcal": act.calories,
                "tags": act.tags,
                "notes": act.notes,
                # Whether this arrived from a device or was typed in.
                "source": act.source,
            }
        )
    truncated = window_truncated or len(out) > limit
    return {
        "start_date": iso(start),
        "end_date": iso(end),
        "activities": out[:limit],
        "truncated": truncated,
        "hint": (
            f"Showing {min(len(out), limit)} of at least {len(out)} matching "
            f"activities. Raise `limit` (max 200) or narrow the date range."
            if truncated
            else None
        ),
    }


def get_activity(db: Session, user_id: int, activity_id: int) -> dict[str, Any]:
    """One activity in full, including its exercise sets."""
    activity_id = _row_id(activity_id, "activity_id")
    act = owned(db, Activity, user_id).filter(Activity.id == activity_id).one_or_none()
    if act is None:
        raise ToolError(f"No activity {activity_id} for this account.")
    return {
        "id": act.id,
        "date": iso(act.date),
        "name": act.name,
        "discipline": classify(act),
        "activity_type": getattr(act.activity_type, "value", act.activity_type),
        "time_of_day": getattr(act.time_of_day, "value", act.time_of_day),
        "duration_mins": act.duration_mins,
        "distance_km": act.distance_km,
        "calories_kcal": act.calories,
        "tags": act.tags,
        "notes": act.notes,
        "source": act.source,
        "exercises": [
            {
                "name": ex.name,
                "sets": ex.sets,
                "reps": ex.reps,
                "weight_kg": ex.weight_kg,
                "notes": ex.notes,
            }
            for ex in act.exercises
        ],
    }


# ── 6. measurements ──────────────────────────────────────────────────────────


def get_measurements(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    latest_only: bool = False,
) -> dict[str, Any]:
    """Body measurements, with the change since the previous entry.

    Every field is centimetres and shares one validation range (10-200 cm), so
    an implausible-looking value is data, not a bug.
    """
    q = owned(db, BodyMeasurement, user_id).order_by(
        BodyMeasurement.date.desc(), BodyMeasurement.id.desc()
    )
    truncated = False
    if latest_only:
        # Two rows, not one: the second is what change_since_previous_cm is
        # measured against.
        rows = q.limit(2).all()
    else:
        # default_days must not exceed MAX_DAYS, or the zero-argument call --
        # the first one a model makes -- raises before it queries anything.
        start, end = _window(start_date, end_date, default_days=MAX_DAYS)
        rows, truncated = capped(in_range(q, BodyMeasurement, start, end), 60)

    def _fields(m: BodyMeasurement) -> dict[str, Any]:
        return {f"{f}_cm": getattr(m, f) for f in MEASUREMENT_FIELDS}

    entries = []
    for i, m in enumerate(rows):
        entry = {"date": iso(m.date), **_fields(m), "notes": m.notes}
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if nxt is not None:
            entry["change_since_previous_cm"] = {
                f"{f}_cm": round(getattr(m, f) - getattr(nxt, f), 2)
                for f in MEASUREMENT_FIELDS
                if getattr(m, f) is not None and getattr(nxt, f) is not None
            }
            entry["previous_date"] = iso(nxt.date)
        entries.append(entry)

    return {
        "entries": entries[:1] if latest_only else entries,
        "truncated": truncated,
        "_units": "all measurement fields are centimetres (valid range 10-200)",
    }


# ── 7. meals ─────────────────────────────────────────────────────────────────


def get_meals(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Meals with their calories and constituent foods.

    Photos and stored AI analysis are deliberately omitted: the photo is not
    fetchable from this service, and a stale analysis string is noise.
    """
    start, end = _window(start_date, end_date)
    limit = clamp_limit(limit, 200)
    # Meal.time is nullable, and SQLite sorts NULLs first while Postgres sorts
    # them last -- untimed meals would otherwise move between backends.
    q = (
        in_range(owned(db, Meal, user_id), Meal, start, end)
        .options(*_MEAL_LOAD)
        .order_by(Meal.date.desc(), Meal.time.asc().nullslast(), Meal.id.asc())
    )
    rows, truncated = capped(q, limit)
    return {
        "start_date": iso(start),
        "end_date": iso(end),
        "meals": [
            {
                "id": m.id,
                "date": iso(m.date),
                "label": m.label,
                "time": m.time,
                "calories_kcal": _meal_calories(m),
                "calories_are_computed": m.calories is None,
                "description": m.description,
                "food_items": [
                    {
                        "name": link.food_item.name,
                        "brand": link.food_item.brand,
                        "quantity": link.quantity,
                        "serving": (
                            f"{link.food_item.serving_size:g} "
                            f"{link.food_item.serving_unit}"
                        ),
                        "calories_kcal": link.food_item.calories,
                        "protein_g": link.food_item.protein_g,
                    }
                    # The same soft-delete filter _meal_calories applies. A
                    # relationship traversal carries no deleted_at filter of its
                    # own, and fixing only the arithmetic left a deleted food
                    # listed while excluding it from the total -- worse than
                    # either alone, because the numbers stop adding up.
                    for link in m.food_items
                    if link.food_item is not None and link.food_item.deleted_at is None
                ],
            }
            for m in rows
        ],
        "truncated": truncated,
    }


# ── 8. training ──────────────────────────────────────────────────────────────


def get_training_plan(
    db: Session, user_id: int, plan_id: int | None = None
) -> dict[str, Any]:
    """The active race plan (or a named one): weeks, progress, what's next."""
    q = owned(db, TrainingPlan, user_id)
    if plan_id is not None:
        plan = q.filter(TrainingPlan.id == _row_id(plan_id, "plan_id")).one_or_none()
        if plan is None:
            # Distinct from "no active plan": saying that for a bad id would
            # have the model tell the user they have no plan when they do.
            raise ToolError(f"No training plan {plan_id} for this account.")
    else:
        # `== TrainingPlanStatus.ACTIVE`, never `== "active"`. SQLAlchemy's Enum
        # persists the member NAME, so the stored value is "ACTIVE" and a
        # lowercase comparison matches zero rows -- silently, since "no plan" is
        # a legitimate answer. The app filters the same way (training.py:416).
        plan = (
            q.filter(TrainingPlan.status == TrainingPlanStatus.ACTIVE)
            .order_by(TrainingPlan.created_at.desc())
            .first()
        )
        if plan is None:
            return {"plan": None, "note": "No active training plan."}

    # `plan.id` came from an owned() query above, which is what makes this safe.
    workouts = (
        children_of(db, PlannedWorkout, PlannedWorkout.plan_id, plan.id)
        .order_by(PlannedWorkout.date.asc())
        .all()
    )
    today = date_type.today()  # noqa: DTZ011
    by_week: dict[int, dict[str, Any]] = {}
    for w in workouts:
        slot = by_week.setdefault(
            w.week_number,
            {"week": w.week_number, "planned": 0, "completed": 0, "target_km": 0.0},
        )
        slot["planned"] += 1
        slot["completed"] += 1 if w.completed else 0
        slot["target_km"] += w.target_distance_km or 0.0
    for slot in by_week.values():
        slot["target_km"] = round(slot["target_km"], 3)

    upcoming = [
        {
            "date": iso(w.date),
            "week": w.week_number,
            "workout_type": w.workout_type,
            "description": w.description,
            "target_distance_km": w.target_distance_km,
            "target_pace": w.target_pace_description,
            "completed": bool(w.completed),
        }
        for w in workouts
        if today <= w.date < today + timedelta(days=7)
    ]

    return {
        "plan": {
            "id": plan.id,
            "name": plan.plan_display_name or plan.plan_name,
            "status": getattr(plan.status, "value", plan.status),
            "race_date": iso(plan.race_date),
            "race_distance_km": plan.race_distance_km,
            "start_date": iso(plan.start_date),
            "days_to_race": (plan.race_date - today).days,
        },
        "weeks": [by_week[k] for k in sorted(by_week)],
        "next_7_days": upcoming,
    }


#: Registered by mcp_server/server.py. Kept here so the catalogue and the
#: implementations cannot drift apart.
TOOLS = {
    "get_profile": get_profile,
    "get_daily_summary": get_daily_summary,
    "get_weekly_review": get_weekly_review,
    "list_activities": list_activities,
    "get_activity": get_activity,
    "get_measurements": get_measurements,
    "get_meals": get_meals,
    "get_training_plan": get_training_plan,
}
