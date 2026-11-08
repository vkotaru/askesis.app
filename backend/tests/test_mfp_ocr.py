"""The OCR parser against fixture screenshots. Needs the `tesseract` binary.

The committed fixtures are synthetic (see make_fixtures.py). Any real
screenshot dropped into fixtures/mfp/private/ is read too, and only has to
parse into four meals -- its numbers are not in this file on purpose.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from app import mfp_ocr
from app.mfp_ocr import MealRead, ParseError, parse_meals, resolve_date

FIX = Path(__file__).parent / "fixtures" / "mfp"
TODAY = date(2026, 11, 8)

needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


# ── pure text parsing: no OCR ────────────────────────────────────────────────


def test_resolve_date_relative_and_absolute():
    assert resolve_date("Today v\nMeals", TODAY) == TODAY
    assert resolve_date("Yesterday\nMeals", TODAY) == date(2026, 11, 7)
    assert resolve_date("Nov4 v oO\nMeals", TODAY) == date(
        2026, 11, 4
    )  # OCR drops the space
    assert resolve_date("Tue, Nov 4\nMeals", TODAY) == date(2026, 11, 4)
    assert resolve_date("Dec 30\nMeals", date(2027, 1, 2)) == date(
        2026, 12, 30
    )  # last year
    assert resolve_date("Nov 4, 2025\nMeals", TODAY) == date(2025, 11, 4)


def test_resolve_date_ignores_text_below_meals():
    assert (
        resolve_date("8:52\nMeals\nBreakfast\nToday's Special and 2 more", TODAY)
        is None
    )
    assert resolve_date("", TODAY) is None


def test_parse_meals_grams_any_order():
    text = (
        "Breakfast Log\n— Oatmeal and 4 more\n640 cal » NC 58g F 24g P 35g\n"
        "Lunch Log\nLentil Soup and 3 more\n710 cal > P 48g F 22g C 66g\n"
    )
    meals, notes = parse_meals(text)
    assert notes == []
    assert meals[0] == MealRead("Breakfast", 640, 58.0, 24.0, 35.0)
    assert meals[1] == MealRead("Lunch", 710, 66.0, 22.0, 48.0)


def test_parse_meals_skips_unreadable_summary():
    text = "Dinner Log\nFish\n480 cal » NC 35g F 9g PQg\nSnacks\nnuts\n290 cal > NC 20g F 12g P 8g\n"
    meals, notes = parse_meals(text)
    assert [m.label for m in meals] == ["Snacks"]
    assert notes == ["Dinner: macros not fully readable ('480 cal » NC 35g F 9g PQg')"]


def test_parse_meals_food_name_cannot_supply_a_macro():
    # "Fat-Free" contains an F; the food line wraps onto two lines.
    text = "Dinner Log\n& Cottage Cheese, Fat-Free and\n3 more\n480 cal » NC 35g F 9g P 55g\n"
    meals, _ = parse_meals(text)
    assert meals == [MealRead("Dinner", 480, 35.0, 9.0, 55.0)]


def test_percent_view_derives_grams():
    meals, _ = parse_meals("Lunch\nx\n800 cal • NC 45% F 25% P 30%\n")
    (m,) = meals
    assert m.from_percent
    assert (m.carbs_g, m.fat_g, m.protein_g) == (90.0, 22.2, 60.0)
    assert m.adds_up()


def test_adds_up_flag():
    assert MealRead("Breakfast", 640, 58.0, 24.0, 35.0).adds_up()  # 588
    assert not MealRead("Snacks", 290, 20.0, 12.0, 8.0).adds_up()  # 220


def test_merge_prefers_grams_over_percent_and_reports_disagreement(monkeypatch):
    texts = iter(
        [
            "Today\nMeals\nLunch\nx\n800 cal • NC 45% F 25% P 30%\n",
            "Today\nMeals\nLunch\nx\n800 cal • NC 80g F 20g P 60g\nDinner\ny\n500 cal • NC 10g F 10g P 10g\n",
            "Today\nMeals\nDinner\ny\n510 cal • NC 10g F 10g P 10g\n",
        ]
    )
    monkeypatch.setattr(mfp_ocr, "ocr_text", lambda blob: next(texts))
    (day,) = mfp_ocr.parse_screenshots([b"1", b"2", b"3"], TODAY)
    assert day.day == TODAY and day.images == 3
    assert day.meals["Lunch"] == MealRead("Lunch", 800, 80.0, 20.0, 60.0)
    assert day.meals["Dinner"].kcal == 510
    assert day.notes == [
        "Dinner: two screenshots disagree (500 vs 510 kcal); kept the later one"
    ]


def test_future_date_is_refused(monkeypatch):
    # A bare "Nov 9" on Nov 8 resolves to last year (the Dec 30 / Jan 2 rule);
    # only an explicit year can put a day in the future.
    monkeypatch.setattr(mfp_ocr, "ocr_text", lambda blob: "Nov 9, 2026\nMeals\n")
    with pytest.raises(ParseError, match="after today"):
        mfp_ocr.parse_screenshots([b"1"], TODAY)


# ── real OCR over the fixture images ─────────────────────────────────────────


@needs_tesseract
def test_grams_fixture():
    (day,) = mfp_ocr.parse_screenshots([_read("grams_nov4.png")], TODAY)
    assert day.day == date(2026, 11, 4)
    assert day.notes == []
    assert {k: m.numbers() for k, m in day.meals.items()} == {
        "Breakfast": (610, 55.0, 22.0, 38.0),
        "Lunch": (740, 70.0, 25.0, 45.0),
        "Dinner": (520, 30.0, 18.0, 50.0),
        "Snacks": (210, 25.0, 8.0, 6.0),
    }


@needs_tesseract
def test_percent_fixture_resolves_today_and_derives_grams():
    (day,) = mfp_ocr.parse_screenshots([_read("percent_today.png")], TODAY)
    assert day.day == TODAY
    assert all(m.from_percent for m in day.meals.values())
    assert day.meals["Breakfast"].numbers() == (600, 60.0, 20.0, 45.0)


@needs_tesseract
def test_dark_mode_yesterday_with_plain_carbs_key():
    (day,) = mfp_ocr.parse_screenshots([_read("dark_yesterday.png")], TODAY)
    assert day.day == date(2026, 11, 7)
    assert day.meals["Dinner"].numbers() == (810, 95.0, 28.0, 30.0)
    assert len(day.meals) == 4


@needs_tesseract
def test_garbled_lunch_is_skipped_and_reported():
    (day,) = mfp_ocr.parse_screenshots([_read("garbled_lunch.png")], TODAY)
    assert set(day.meals) == {"Breakfast", "Dinner", "Snacks"}
    assert len(day.notes) == 1 and day.notes[0].startswith(
        "Lunch: macros not fully readable"
    )


@needs_tesseract
def test_no_header_is_refused():
    with pytest.raises(ParseError, match="no date in the header"):
        mfp_ocr.parse_screenshots([_read("no_header.png")], TODAY)


@needs_tesseract
def test_two_images_one_day_merge():
    days = mfp_ocr.parse_screenshots(
        [_read("grams_nov4.png"), _read("garbled_lunch.png")], TODAY
    )
    (day,) = days
    assert day.images == 2 and len(day.meals) == 4
    assert day.notes[0].startswith("Lunch: macros not fully readable")


@needs_tesseract
@pytest.mark.parametrize(
    "path",
    sorted((FIX / "private").glob("*.png")) if (FIX / "private").exists() else [],
)
def test_private_real_screenshots_read_four_meals(path):
    """Any real screenshot in private/ must yield four meals with no notes.

    Numbers are deliberately not asserted here; they are the user's.
    """
    (day,) = mfp_ocr.parse_screenshots([path.read_bytes()], TODAY)
    assert len(day.meals) == 4, day.notes
    assert day.notes == []


def test_summary_without_a_title_is_reported_not_guessed():
    text = "Breakfast\nToast\n450 cal * C48g F14g P 20g\nRice Bowl and 3 more\n690 cal * C 80g F 20g P 35g\n"
    meals, notes = parse_meals(text)
    assert [m.label for m in meals] == ["Breakfast"]
    assert notes == [
        "a meal's title did not read; skipped ('690 cal * C 80g F 20g P 35g')"
    ]
