"""The write side of the MyFitnessPal import, with no OCR and no HTTP.

What is proven here: every meal goes through `log_meal`, a resend is a no-op,
and the double-count guard refuses a day whose totals aren't explained by its
meals unless forced -- in which case the day ends on the screenshot's numbers
and not on the sum of both.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import intake_log, mfp_ingest
from app.mfp_ingest import IngestRefused, MealNumbers, write_day
from app.models import DailyNutrition, Meal

DAY = date(2026, 11, 7)

FOUR_MEALS = [
    MealNumbers("Breakfast", 420, 30.0, 45.0, 12.0),
    MealNumbers("Lunch", 640, 35.0, 58.0, 24.0),
    MealNumbers("Dinner", 610, 48.0, 40.0, 22.0),
    MealNumbers("Snacks", 180, 6.0, 30.0, 4.0),
]


def _day(db, user_id) -> DailyNutrition | None:
    return (
        db.query(DailyNutrition)
        .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == DAY)
        .first()
    )


def _meals(db, user_id) -> dict[str, Meal]:
    rows = db.query(Meal).filter(Meal.user_id == user_id, Meal.date == DAY).all()
    return {m.label: m for m in rows}


def test_writes_all_four_meals_and_the_day_total(db, user):
    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()

    assert out.written == 4 and out.skipped == 0
    meals = _meals(db, user.id)
    assert set(meals) == {"Breakfast", "Lunch", "Dinner", "Snack"}  # normalised
    assert meals["Lunch"].calories == 640
    assert meals["Lunch"].protein_g == 35.0
    day = _day(db, user.id)
    assert (day.protein_g, day.carbs_g, day.fat_g) == (119.0, 173.0, 62.0)
    assert out.day_total_kcal == 420 + 640 + 610 + 180


def test_resend_is_idempotent(db, user):
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    before = {
        label: (m.calories, m.protein_g, m.carbs_g, m.fat_g)
        for label, m in _meals(db, user.id).items()
    }
    day_before = _day(db, user.id).protein_g

    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()

    assert out.written == 0 and out.unchanged == 4
    after = {
        label: (m.calories, m.protein_g, m.carbs_g, m.fat_g)
        for label, m in _meals(db, user.id).items()
    }
    assert after == before
    assert _day(db, user.id).protein_g == day_before
    assert len(db.query(Meal).filter(Meal.date == DAY).all()) == 4


def test_dry_run_rolls_back_to_nothing(db, user):
    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=True, force=False)
    db.rollback()  # what the router does after a preview

    assert out.dry_run and out.written == 4
    assert _meals(db, user.id) == {}
    assert _day(db, user.id) is None


def test_corrected_screenshot_replaces_rather_than_stacks(db, user):
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    fixed = [MealNumbers("Lunch", 800, 30.0, 58.0, 24.0)]

    write_day(db, user.id, DAY, fixed, dry_run=False, force=False)
    db.commit()

    assert _meals(db, user.id)["Lunch"].calories == 800
    # The day moved by lunch's change only: +3 g protein.
    assert _day(db, user.id).protein_g == 114.0


def test_day_level_macros_trip_the_guard(db, user):
    # An older day: calories per meal, macros for the day as a whole.
    intake_log.log_day(
        db,
        user.id,
        DAY,
        meals={"Breakfast": 400, "Lunch": 700},
        protein_g=90.0,
        carbs_g=150.0,
        fat_g=60.0,
    )
    db.commit()

    with pytest.raises(IngestRefused) as exc:
        write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.rollback()

    assert "force=true" in str(exc.value)
    assert "protein 90g on the day vs 0g in meals" in str(exc.value)
    # Nothing moved.
    assert _day(db, user.id).protein_g == 90.0
    assert _meals(db, user.id)["Lunch"].calories == 700


def test_force_rebases_the_day_instead_of_double_counting(db, user):
    intake_log.log_day(
        db,
        user.id,
        DAY,
        meals={"Breakfast": 400, "Lunch": 700},
        protein_g=90.0,
        carbs_g=150.0,
        fat_g=60.0,
    )
    db.commit()

    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=True)
    db.commit()

    assert (
        out.warnings[0]
        == "forced: dropping 90g protein, 150g carbs, 60g fat that no meal accounts for"
    )
    day = _day(db, user.id)
    # The screenshot's totals, not screenshot + the old day-level grams.
    assert (day.protein_g, day.carbs_g, day.fat_g) == (119.0, 173.0, 62.0)
    assert _meals(db, user.id)["Lunch"].calories == 640


def test_guard_is_quiet_once_meals_explain_the_day(db, user):
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    assert not mfp_ingest.macro_gap(db, user.id, DAY)


def test_itemised_meal_is_skipped_not_overwritten(db, user):
    from app.models import FoodItem, MealFoodItem

    food = FoodItem(name="Oats", calories=150)
    meal = Meal(user_id=user.id, date=DAY, label="Breakfast", calories=300)
    db.add_all([food, meal])
    db.flush()
    db.add(MealFoodItem(meal_id=meal.id, food_item_id=food.id, quantity=1))
    db.commit()

    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()

    assert out.skipped == 1 and out.written == 3
    assert _meals(db, user.id)["Breakfast"].calories == 300
    assert any("Breakfast: skipped" in line for line in out.lines)


def test_token_matches_is_strict():
    assert mfp_ingest.token_matches("abc", "abc")
    assert not mfp_ingest.token_matches("abc", "abd")
    assert not mfp_ingest.token_matches("", "abc")
    assert not mfp_ingest.token_matches(None, "abc")
    assert not mfp_ingest.token_matches("", "")  # unset token never matches


def test_resolve_user_single_account_or_named(db, user):
    from app.models import User

    assert mfp_ingest.resolve_user(db, "").id == user.id
    assert mfp_ingest.resolve_user(db, "one").id == user.id
    assert mfp_ingest.resolve_user(db, "nobody") is None
    db.add(User(email="two@example.test", username="two", name="Two"))
    db.commit()
    assert mfp_ingest.resolve_user(db, "") is None  # two accounts: no guessing
    assert mfp_ingest.resolve_user(db, "two").username == "two"


def test_render_fits_a_phone_alert(db, user):
    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=True, force=False)
    text = mfp_ingest.render([out])
    assert text.startswith("[preview] Sat Nov 7: 1850 kcal")
    assert "Lunch: 640 kcal P35 C58 F24 (new)" in text
    assert text.splitlines()[-1] == "Would write 4."
    assert len(text.splitlines()) <= 12


def test_hand_nudged_day_still_accepts_a_noop_resend(db, user):
    """A gap the user made on purpose must not turn every resend into a 409."""
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    day = _day(db, user.id)
    day.protein_g = 121.0  # +10 g for an unlogged snack, typed in the Daily Log
    db.commit()
    assert mfp_ingest.macro_gap(db, user.id, DAY)

    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()

    assert out.written == 0 and out.unchanged == 4 and not out.warnings
    assert _day(db, user.id).protein_g == 121.0  # the nudge survives


def test_day_below_its_meals_gets_the_other_message(db, user):
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    db.delete(_day(db, user.id))
    db.commit()
    with pytest.raises(IngestRefused) as exc:
        write_day(
            db,
            user.id,
            DAY,
            [MealNumbers("Lunch", 800, 30.0)],
            dry_run=False,
            force=False,
        )
    db.rollback()
    assert "lowered below its meals" in str(exc.value)

    out = write_day(
        db, user.id, DAY, [MealNumbers("Lunch", 800, 30.0)], dry_run=False, force=True
    )
    assert out.warnings == ["forced: day totals raised to match the meals"]
    assert _day(db, user.id).protein_g == 114.0


def test_a_failing_meal_leaves_no_half_written_row(db, user):
    """`_shift_day`'s day bound fires after the meal row is set; the savepoint undoes it."""
    write_day(
        db,
        user.id,
        DAY,
        [MealNumbers("Breakfast", 500, 990.0)],
        dry_run=False,
        force=False,
    )
    db.commit()

    out = write_day(
        db,
        user.id,
        DAY,
        [MealNumbers("Lunch", 700, 20.0), MealNumbers("Dinner", 600, 5.0)],
        dry_run=False,
        force=False,
    )
    db.commit()

    assert out.skipped == 1 and out.written == 1
    meals = _meals(db, user.id)
    assert "Lunch" not in meals  # not persisted by Dinner's flush
    assert meals["Dinner"].calories == 600
    assert _day(db, user.id).protein_g == 995.0
    assert not mfp_ingest.macro_gap(db, user.id, DAY)  # day still equals its meals


def test_force_warns_about_a_skipped_itemised_meal(db, user):
    from app.models import FoodItem, MealFoodItem

    food = FoodItem(name="Oats", calories=150, protein_g=20.0)
    meal = Meal(user_id=user.id, date=DAY, label="Breakfast", calories=300)
    db.add_all([food, meal])
    db.flush()
    db.add(MealFoodItem(meal_id=meal.id, food_item_id=food.id, quantity=1))
    db.add(DailyNutrition(user_id=user.id, date=DAY, protein_g=20.0))
    db.commit()

    out = write_day(db, user.id, DAY, FOUR_MEALS, dry_run=True, force=True)
    db.rollback()

    assert out.warnings[0] == "forced: dropping 20g protein that no meal accounts for"
    assert out.warnings[1].startswith(
        "Breakfast is itemised in the app and will be skipped"
    )


def test_macros_only_change_is_labelled(db, user):
    write_day(db, user.id, DAY, FOUR_MEALS, dry_run=False, force=False)
    db.commit()
    out = write_day(
        db,
        user.id,
        DAY,
        [MealNumbers("Lunch", 640, 30.0, 58.0, 24.0)],
        dry_run=False,
        force=False,
    )
    assert out.lines == ["Lunch: 640 kcal P30 C58 F24 (macros changed)"]


def test_render_keeps_the_verdict_when_truncating():
    from datetime import timedelta

    days = [
        mfp_ingest.DayWrite(
            day=DAY + timedelta(days=i),
            dry_run=False,
            lines=[f"Meal {j}: 100 kcal (new)" for j in range(4)],
            warnings=["forced: dropping 9g protein that no meal accounts for"],
            written=4,
            day_total_kcal=400,
        )
        for i in range(3)
    ]
    text = mfp_ingest.render(days)
    lines = text.splitlines()
    assert len(lines) == 12
    assert lines[-1] == "Wrote 12."
    assert lines[-2].startswith("... ")


def test_resolve_user_refuses_an_ambiguous_name(db, user):
    from app.models import User

    db.add(
        User(email="one", username="other", name="Other")
    )  # email equals user one's username
    db.commit()
    assert mfp_ingest.resolve_user(db, "one") is None
