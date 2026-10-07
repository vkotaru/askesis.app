"""The food library: foods you save once and look up from then on.

Two things fill it from the MCP connector:

* a **nutrition label** read off a screenshot -- the per-serving numbers as
  printed, so "Kirkland egg whites" is a lookup rather than a guess next time;
* a **home recipe** -- worked out per serving from its ingredients by whoever
  calls this, saved as one food with category "Recipe" and the ingredient list
  in `notes`, so the number can be checked or redone later.

The library is library data, like the exercise library: what a food *is*, not
what anyone ate. That is why the connector may write it (INSERT/UPDATE, no
DELETE -- `scripts/mcp_db_role.sql`), and why it is shared with the household
by default. A food can be saved private.

**Plain SQLAlchemy, no FastAPI, nothing here commits** -- the `planning.py`
contract, so `mcp_server/` can import it. Every bound below is at least as
strict as `FoodItemCreate` in `routers/nutrition.py`: a stored value that the
REST response model rejects would 500 the app's whole food list, which is a
trap this repo has walked into before (`_sanitise_exercise`).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import FoodItem

MAX_NAME = 200
MAX_BRAND = 200
MAX_CATEGORY = 100
MAX_UNIT = 20
MAX_NOTES = 2000
MAX_SERVING_KCAL = 5000
MAX_SERVING_G = 1000.0
MAX_SERVING_SIZE = 5000.0
MAX_RESULTS = 20

RECIPE_CATEGORY = "Recipe"


class FoodError(ValueError):
    """A bad request, phrased to be read by a person or a model."""


def food_dict(f: FoodItem, user_id: int) -> dict[str, Any]:
    return {
        "id": f.id,
        "name": f.name,
        "brand": f.brand,
        "category": f.category,
        "serving_size": f.serving_size,
        "serving_unit": f.serving_unit,
        "calories_kcal": f.calories,
        "protein_g": f.protein_g,
        "carbs_g": f.carbs_g,
        "fat_g": f.fat_g,
        "fiber_g": f.fiber_g,
        "notes": f.notes,
        "shared_with_household": bool(f.is_shared),
        "yours": f.user_id == user_id,
    }


def _visible(db: Session, user_id: int):
    """Foods this account may see: its own, and everything shared."""
    return db.query(FoodItem).filter(
        FoodItem.deleted_at.is_(None),
        or_(FoodItem.user_id == user_id, FoodItem.is_shared.is_(True)),
    )


def search(db: Session, user_id: int, query: str, limit: int = 10) -> list[FoodItem]:
    """Library foods whose name or brand contains every word of `query`.

    Word-wise rather than one substring, so "kirkland egg white" finds
    "Egg Whites" by Kirkland. Your own foods first, then the shared ones.
    """
    words = [w for w in query.lower().split() if w]
    if not words:
        raise FoodError("Give a food to search for.")
    q = _visible(db, user_id)
    for w in words[:6]:
        like = f"%{w}%"
        q = q.filter(or_(FoodItem.name.ilike(like), FoodItem.brand.ilike(like)))
    return (
        q.order_by((FoodItem.user_id == user_id).desc(), FoodItem.name)
        .limit(min(limit, MAX_RESULTS))
        .all()
    )


def _text(
    field: str, value: str | None, limit: int, *, required: bool = False
) -> str | None:
    if value is None:
        if required:
            raise FoodError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise FoodError(f"{field} must be text.")
    value = value.strip()
    if not value:
        if required:
            raise FoodError(f"{field} is required.")
        return None
    if len(value) > limit:
        raise FoodError(f"{field} is {len(value)} characters; the maximum is {limit}.")
    return value


def _number(field: str, value: Any, limit: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FoodError(f"{field} must be a number.")
    if value < 0 or value > limit:
        raise FoodError(
            f"{field}: {value} is outside 0-{limit:g} -- likely a misread digit."
        )
    return float(value)


def save(
    db: Session,
    user_id: int,
    *,
    name: str,
    serving_size: float,
    serving_unit: str,
    calories: float,
    brand: str | None = None,
    category: str | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    fiber_g: float | None = None,
    notes: str | None = None,
    private: bool = False,
) -> tuple[FoodItem, bool]:
    """Create a food, or update yours with the same name and brand.

    Returns `(food, created)`. Matching is case-insensitive on name + brand.
    Another account's shared food with that name is never edited from here --
    it is theirs -- so that is refused with a pointer to it rather than quietly
    shadowed by a near-duplicate.
    """
    name = _text("name", name, MAX_NAME, required=True)
    brand = _text("brand", brand, MAX_BRAND)
    category = _text("category", category, MAX_CATEGORY)
    unit = _text("serving_unit", serving_unit, MAX_UNIT, required=True)
    notes = _text("notes", notes, MAX_NOTES)
    size = _number("serving_size", serving_size, MAX_SERVING_SIZE)
    if not size:
        raise FoodError(
            "serving_size must be more than 0 (e.g. 46 for '3 tbsp (46 g)')."
        )
    kcal = _number("calories", calories, MAX_SERVING_KCAL)
    if kcal is None:
        raise FoodError("calories per serving is required.")
    macros = {
        "protein_g": _number("protein_g", protein_g, MAX_SERVING_G),
        "carbs_g": _number("carbs_g", carbs_g, MAX_SERVING_G),
        "fat_g": _number("fat_g", fat_g, MAX_SERVING_G),
        "fiber_g": _number("fiber_g", fiber_g, MAX_SERVING_G),
    }

    brand_match = (
        FoodItem.brand.is_(None)
        if brand is None
        else func.lower(FoodItem.brand) == brand.lower()
    )
    same = (
        _visible(db, user_id)
        .filter(func.lower(FoodItem.name) == name.lower(), brand_match)
        .order_by((FoodItem.user_id == user_id).desc())
        .first()
    )
    if same is not None and same.user_id != user_id:
        raise FoodError(
            f"'{same.name}'{f' ({same.brand})' if same.brand else ''} is already in the "
            "shared library, saved by the other account. Use it as is, or save yours "
            "under a different name or brand."
        )

    created = same is None
    food = same or FoodItem(user_id=user_id, name=name, brand=brand, source="mcp")
    if not created:
        food.name = name  # adopt the caller's capitalisation
    food.category = category
    food.serving_size = size
    food.serving_unit = unit
    food.calories = round(kcal)
    for field, value in macros.items():
        setattr(food, field, None if value is None else round(value, 1))
    food.notes = notes
    food.is_shared = not private
    if created:
        db.add(food)
    db.flush()
    return food, created
