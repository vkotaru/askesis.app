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
) -> dict[str, Any]:
    """Write one day's intake and report every field: before, after, or why not.

    Validates everything before touching anything, so a single bad value
    leaves the day exactly as it was rather than half-written.
    """
    # ── validate all of it first ─────────────────────────────────────────────
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

    # ── meals ────────────────────────────────────────────────────────────────
    meal_report: dict[str, dict[str, Any]] = {}
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
                "overwriting its total would contradict them.",
                "current_kcal": rows[0].calories,
            }
        elif rows:
            before = rows[0].calories
            rows[0].calories = kcal
            meal_report[label] = {
                "result": "unchanged" if before == kcal else "updated",
                "before_kcal": before,
                "kcal": kcal,
            }
        elif kcal == 0:
            # The Daily Log's rule: only a real number creates a row.
            meal_report[label] = {
                "result": "skipped",
                "reason": "0 kcal; no row created.",
            }
        else:
            db.add(Meal(user_id=user_id, date=day, label=label, calories=kcal))
            meal_report[label] = {"result": "created", "kcal": kcal}

    # ── macros ───────────────────────────────────────────────────────────────
    macro_report: dict[str, dict[str, Any]] = {}
    if macros:
        row = (
            db.query(DailyNutrition)
            .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == day)
            .first()
        )
        if row is None:
            row = DailyNutrition(user_id=user_id, date=day)
            db.add(row)
        for field, value in macros.items():
            before = getattr(row, field)
            setattr(row, field, value)
            macro_report[field] = {
                "result": "unchanged"
                if before == value
                else ("set" if before is None else "updated"),
                "before": before,
                "value": value,
            }

    db.flush()
    total = sum(
        r.calories or 0
        for r in db.query(Meal).filter(
            Meal.user_id == user_id, Meal.date == day, Meal.deleted_at.is_(None)
        )
    )
    return {
        "date": day.isoformat(),
        "meals": meal_report,
        "macros": macro_report,
        "day_total_kcal": total,
    }
