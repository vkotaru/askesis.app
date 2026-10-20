"""Write one day's food intake: calories per meal, and the day's macros.

**The one piece of logged history the MCP connector may write.** Everything
else the connector writes is a plan (`app/planning.py`); this module is the
deliberate, narrow exception, added so a screenshot of another food tracker can
be shared to an assistant and logged without retyping four numbers. It is kept
out of `planning.py` on purpose: that module's rule is "the connector may call
anything in here", and that must not quietly grow to cover history.

It writes exactly the shape the Daily Log's quick entry writes, because that is
how calories are stored here: one label-only `Meal` row per meal
(Breakfast/Lunch/Dinner/Snack, no food items) whose calories sum to the day, and
protein/carbs/fat on the day's single `DailyNutrition` row. The rules mirror
`routes/daily-log/+page.svelte`:

* one row per label is **updated**, not added to -- a second Lunch row would
  double-count the day;
* a label with several rows, or with itemised foods, is **left alone** and
  reported, the same way the Daily Log locks it;
* no zero-calorie row is ever created;
* nothing is deleted. `None` means "leave as is".

**Macros per meal** (`log_meal`). A meal row can carry its own protein/carbs/
fat, but the day's total on `DailyNutrition` stays the one number everything
reads -- the dashboard, the Daily Log, reports, the read tools. Logging a meal
moves that total by *the meal's change* (new minus old), never sets it. So
lunch logged twice replaces lunch rather than stacking, breakfast is never
touched, and a whole-day number typed into the Daily Log stays authoritative:
whatever it holds beyond the logged meals is simply not broken out. Deleting a
meal takes its share back out (`release_meal_macros`).

**Plain SQLAlchemy, no FastAPI, and nothing here commits** -- same contract as
`planning.py`, so the MCP image can import it and the caller owns the
transaction.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import local_today
from app.models import DailyNutrition, Meal

#: The labels the Daily Log shows. Anything else would be stored and then never
#: displayed, so an unknown label is refused rather than written.
MEAL_LABELS = ("Breakfast", "Lunch", "Dinner", "Snack")

#: Bounds that only reject what cannot be a real day -- a misread digit, not an
#: unusual diet. A screenshot read as 21400 kcal for lunch should fail loudly.
MAX_MEAL_KCAL = 5000
MAX_MACRO_G = 1000.0
#: How far back a day may be written. Wide enough to catch up a missed month or
#: a year of history; narrow enough that a misread year (2016 for 2026) fails.
MAX_DAYS_BACK = 400


class IntakeError(ValueError):
    """A bad request, phrased to be read by a person or a model."""


def normalise_label(label: str) -> str:
    """'snacks', 'SNACK', ' Lunch ' -> the canonical label, or IntakeError."""
    key = label.strip().lower().rstrip("s")
    for canonical in MEAL_LABELS:
        if canonical.lower() == key:
            return canonical
    raise IntakeError(
        f"Unknown meal {label!r}. Use one of: {', '.join(MEAL_LABELS)}. "
        "Fold anything else (e.g. 'Pre-workout') into Snack."
    )


def parse_day(value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise IntakeError(f"date must be YYYY-MM-DD, got {value!r}") from None
    today = local_today()
    if day > today:
        raise IntakeError(f"{day} is in the future (today is {today}).")
    if day < today - timedelta(days=MAX_DAYS_BACK):
        raise IntakeError(
            f"{day} is more than {MAX_DAYS_BACK} days ago -- check the year was read right."
        )
    return day


def _check_kcal(label: str, kcal: Any) -> int:
    if isinstance(kcal, bool) or not isinstance(kcal, (int, float)):
        raise IntakeError(f"{label} calories must be a number.")
    value = round(kcal)
    if value < 0 or value > MAX_MEAL_KCAL:
        raise IntakeError(
            f"{label}: {value} kcal is outside 0-{MAX_MEAL_KCAL} -- likely a misread digit."
        )
    return value


def _check_grams(name: str, grams: float | None) -> float | None:
    if grams is None:
        return None
    if isinstance(grams, bool) or not isinstance(grams, (int, float)):
        raise IntakeError(f"{name} must be a number of grams.")
    if grams < 0 or grams > MAX_MACRO_G:
        raise IntakeError(
            f"{name}: {grams} g is outside 0-{MAX_MACRO_G:g} -- likely a misread digit."
        )
    return round(float(grams), 1)


def log_day(
    db: Session,
    user_id: int,
    day: date,
    meals: dict[str, Any] | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    mode: str = "replace",
) -> dict[str, Any]:
    """Write one day's intake and report every field: before, after, or why not.

    `mode="replace"` sets each given total (a screenshot of the whole day).
    `mode="add"` adds each given amount to what is there (one more snack), in
    one step on the server, so a caller never has to read a total, add to it
    and write it back -- the read-modify-write that loses an entry whenever it
    slips.

    Validates everything -- including, in add mode, the totals it would
    produce -- before touching anything, so one bad value leaves the day
    exactly as it was rather than half-written.
    """
    if mode not in ("replace", "add"):
        raise IntakeError(f"mode must be 'replace' or 'add', got {mode!r}.")
    adding = mode == "add"

    # ── validate the input ───────────────────────────────────────────────────
    wanted: dict[str, int] = {}
    for raw_label, kcal in (meals or {}).items():
        if kcal is None:
            continue
        label = normalise_label(raw_label)
        if label in wanted:
            raise IntakeError(
                f"{label} was given twice ({raw_label!r}); merge them first."
            )
        wanted[label] = _check_kcal(label, kcal)
    macros = {
        "protein_g": _check_grams("protein_g", protein_g),
        "carbs_g": _check_grams("carbs_g", carbs_g),
        "fat_g": _check_grams("fat_g", fat_g),
    }
    macros = {k: v for k, v in macros.items() if v is not None}
    if not wanted and not macros:
        raise IntakeError(
            "Nothing to log: pass at least one meal's calories or a macro."
        )

    # ── plan: read only, and refuse here if any result is out of bounds ──────
    meal_report: dict[str, dict[str, Any]] = {}
    meal_writes: list[tuple[Meal | None, str, int]] = []  # (row or new, label, kcal)
    for label, kcal in wanted.items():
        rows = (
            db.query(Meal)
            .filter(
                Meal.user_id == user_id,
                Meal.date == day,
                Meal.label == label,
                Meal.deleted_at.is_(None),
            )
            .all()
        )
        if len(rows) > 1:
            meal_report[label] = {
                "result": "skipped",
                "reason": f"{len(rows)} {label} entries already exist that day; "
                "edit them in the app so the total isn't double-counted.",
                "current_kcal": sum(r.calories or 0 for r in rows),
            }
        elif rows and rows[0].food_items:
            meal_report[label] = {
                "result": "skipped",
                "reason": f"{label} has itemised foods logged in the app; "
                "changing its total would contradict them.",
                "current_kcal": rows[0].calories,
            }
        elif rows:
            before = rows[0].calories
            after = (before or 0) + kcal if adding else kcal
            if after > MAX_MEAL_KCAL:
                raise IntakeError(
                    f"{label} would become {after} kcal, over {MAX_MEAL_KCAL} -- "
                    "check the amount, or whether it was already logged."
                )
            meal_writes.append((rows[0], label, after))
            meal_report[label] = {
                "result": "unchanged" if before == after else "updated",
                "before_kcal": before,
                "kcal": after,
            }
        elif kcal == 0:
            # The Daily Log's rule: only a real number creates a row.
            meal_report[label] = {
                "result": "skipped",
                "reason": "0 kcal; no row created.",
            }
        else:
            meal_writes.append((None, label, kcal))
            meal_report[label] = {
                "result": "created",
                "before_kcal": None,
                "kcal": kcal,
            }

    macro_report: dict[str, dict[str, Any]] = {}
    nutrition = None
    if macros:
        nutrition = (
            db.query(DailyNutrition)
            .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == day)
            .first()
        )
        for field, value in macros.items():
            before = getattr(nutrition, field) if nutrition else None
            after = round((before or 0) + value, 1) if adding else value
            if after > MAX_MACRO_G:
                raise IntakeError(
                    f"{field} would become {after} g for the day, over "
                    f"{MAX_MACRO_G:g} -- check the amount."
                )
            macro_report[field] = {
                "result": "unchanged"
                if before == after
                else ("set" if before is None else "updated"),
                "before": before,
                "value": after,
            }

    # ── apply ────────────────────────────────────────────────────────────────
    for row, label, kcal in meal_writes:
        if row is None:
            db.add(Meal(user_id=user_id, date=day, label=label, calories=kcal))
        else:
            row.calories = kcal
    if macros:
        if nutrition is None:
            nutrition = DailyNutrition(user_id=user_id, date=day)
            db.add(nutrition)
        for field, entry in macro_report.items():
            setattr(nutrition, field, entry["value"])

    db.flush()
    total = sum(
        r.calories or 0
        for r in db.query(Meal).filter(
            Meal.user_id == user_id, Meal.date == day, Meal.deleted_at.is_(None)
        )
    )
    return {
        "date": day.isoformat(),
        "mode": mode,
        "meals": meal_report,
        "macros": macro_report,
        "day_total_kcal": total,
    }


MACRO_FIELDS = ("protein_g", "carbs_g", "fat_g")


def _shift_day(
    db: Session, user_id: int, day: date, deltas: dict[str, float]
) -> dict[str, dict[str, Any]]:
    """Move the day's macro totals by `deltas`, and report each one.

    A total that would go below zero is held at zero and says so: that only
    happens when the day was lowered by hand below what its meals add up to,
    and a negative gram count would be a worse lie than the clamp.
    """
    deltas = {k: v for k, v in deltas.items() if v}
    if not deltas:
        return {}
    nutrition = (
        db.query(DailyNutrition)
        .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == day)
        .first()
    )
    if nutrition is None:
        nutrition = DailyNutrition(user_id=user_id, date=day)
        db.add(nutrition)
    report: dict[str, dict[str, Any]] = {}
    for field, delta in deltas.items():
        before = getattr(nutrition, field)
        raw = round((before or 0) + delta, 1)
        after = max(raw, 0.0)
        if after > MAX_MACRO_G:
            raise IntakeError(
                f"{field} would become {after} g for the day, over "
                f"{MAX_MACRO_G:g} -- check the amount."
            )
        setattr(nutrition, field, after)
        report[field] = {"before": before, "value": after}
        if raw < 0:
            report[field]["note"] = "held at 0; the day was below its meals"
    return report


def log_meal(
    db: Session,
    user_id: int,
    day: date,
    label: str,
    kcal: float | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    mode: str = "replace",
) -> dict[str, Any]:
    """Write one meal's calories and macros, and move the day's totals to match.

    `mode="replace"` sets this meal's numbers ("lunch was 650 kcal, 40 g
    protein"); `mode="add"` adds to them ("I also had a banana at lunch").
    Either way only the given fields change, and the day's macros move by
    exactly this meal's difference, so other meals are never touched.

    Validates before writing anything, like `log_day`.
    """
    if mode not in ("replace", "add"):
        raise IntakeError(f"mode must be 'replace' or 'add', got {mode!r}.")
    adding = mode == "add"
    label = normalise_label(label)
    new_kcal = None if kcal is None else _check_kcal(label, kcal)
    given = {
        "protein_g": _check_grams("protein_g", protein_g),
        "carbs_g": _check_grams("carbs_g", carbs_g),
        "fat_g": _check_grams("fat_g", fat_g),
    }
    given = {k: v for k, v in given.items() if v is not None}
    if new_kcal is None and not given:
        raise IntakeError("Nothing to log: pass the meal's calories or a macro.")

    rows = (
        db.query(Meal)
        .filter(
            Meal.user_id == user_id,
            Meal.date == day,
            Meal.label == label,
            Meal.deleted_at.is_(None),
        )
        .all()
    )
    if len(rows) > 1:
        raise IntakeError(
            f"{len(rows)} {label} entries already exist on {day}; edit them in "
            "the app so the day isn't double-counted."
        )
    meal = rows[0] if rows else None
    if meal is not None and meal.food_items:
        raise IntakeError(
            f"{label} on {day} has itemised foods logged in the app; its "
            "numbers come from those foods, so they are not changed here."
        )
    if meal is None and not new_kcal:
        raise IntakeError(
            f"No {label} logged on {day} yet: pass its calories (more than 0) "
            "to create it."
        )

    before = {
        "kcal": meal.calories if meal else None,
        **{f: (getattr(meal, f) if meal else None) for f in MACRO_FIELDS},
    }
    after = dict(before)
    if new_kcal is not None:
        after["kcal"] = (before["kcal"] or 0) + new_kcal if adding else new_kcal
        if after["kcal"] > MAX_MEAL_KCAL:
            raise IntakeError(
                f"{label} would become {after['kcal']} kcal, over {MAX_MEAL_KCAL} "
                "-- check the amount, or whether it was already logged."
            )
    for field, value in given.items():
        after[field] = round((before[field] or 0) + value, 1) if adding else value
        if after[field] > MAX_MACRO_G:
            raise IntakeError(
                f"{label} {field} would become {after[field]} g, over "
                f"{MAX_MACRO_G:g} -- check the amount."
            )

    if meal is None:
        meal = Meal(user_id=user_id, date=day, label=label)
        db.add(meal)
    meal.calories = after["kcal"]
    for field in given:
        setattr(meal, field, after[field])
    day_macros = _shift_day(
        db,
        user_id,
        day,
        {f: after[f] - (before[f] or 0) for f in given},
    )

    db.flush()
    total = sum(
        r.calories or 0
        for r in db.query(Meal).filter(
            Meal.user_id == user_id, Meal.date == day, Meal.deleted_at.is_(None)
        )
    )
    return {
        "date": day.isoformat(),
        "meal": label,
        "mode": mode,
        "result": "updated" if rows else "created",
        "before": before,
        "after": after,
        "day_macros": day_macros,
        "day_total_kcal": total,
    }


def release_meal_macros(db: Session, meal: Meal) -> None:
    """Take a deleted meal's macros back out of its day's total.

    Called by every path that deletes a meal. Without it a removed lunch would
    leave its protein counted in the day forever. Nothing to do for a meal that
    was never broken out.
    """
    deltas = {f: -(getattr(meal, f) or 0) for f in MACRO_FIELDS}
    if any(deltas.values()):
        _shift_day(db, meal.user_id, meal.date, deltas)
