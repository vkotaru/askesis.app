"""Render synthetic MyFitnessPal "Meals" screens for the parser tests.

Real screenshots are health data and this is a public repository, so the
committed fixtures are drawn here, in the same layout as the app (header with
the date, a "Meals" heading, four cards each with a title, a food line and a
`640 cal • NC 58g  F 24g  P 35g` summary) with made-up numbers. Real
screenshots go in `private/` (gitignored) and `test_mfp_ocr.py` runs them too
when they are present.

Deterministic: re-running overwrites the same bytes. Run from backend/:

    ./venv/bin/python tests/fixtures/mfp/make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
W = 1170  # iPhone screenshot width
# Liberation Sans: Arial metrics, and a digit 1 that Tesseract does not read
# as "l" (DejaVu Sans rendered "P 12g" as "Pl2g"). Needed only to RE-RENDER;
# the PNGs are committed, so CI needs no fonts.
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

LIGHT = {
    "bg": (236, 239, 245),
    "card": (255, 255, 255),
    "fg": (20, 20, 20),
    "dim": (95, 95, 100),
    "pill": (222, 232, 252),
    "pill_fg": (40, 90, 220),
}
# The app's dark mode draws the Log pill dark blue with light text. Getting
# that right matters: a light pill on a dark card inverts into a black block
# that Tesseract treats as a picture, and the title beside it vanishes.
DARK = {
    "bg": (18, 18, 20),
    "card": (36, 36, 40),
    "fg": (240, 240, 240),
    "dim": (190, 190, 195),
    "pill": (38, 58, 110),
    "pill_fg": (140, 180, 255),
}

Meal = tuple[str, str, str]  # title, food line, summary line


def render(header: str | None, meals: list[Meal], theme=LIGHT) -> Image.Image:
    f_head = ImageFont.truetype(FONT_BOLD, 54)
    f_title = ImageFont.truetype(FONT_BOLD, 44)
    f_food = ImageFont.truetype(FONT, 36)
    f_sum = ImageFont.truetype(FONT, 34)
    card_h, gap = 300, 26
    top = 260 if header else 60
    height = top + 120 + len(meals) * (card_h + gap) + 120
    im = Image.new("RGB", (W, height), theme["bg"])
    d = ImageDraw.Draw(im)
    if header:
        d.text((48, 120), f"{header}  ▾", font=f_head, fill=theme["fg"])
    d.text((56, top), "Meals", font=f_head, fill=theme["fg"])
    d.text((W - 300, top + 10), "View diary", font=f_food, fill=(40, 90, 220))
    y = top + 120
    for title, food, summary in meals:
        d.rounded_rectangle((56, y, W - 56, y + card_h), radius=28, fill=theme["card"])
        d.text((220, y + 56), title, font=f_title, fill=theme["fg"])
        d.rounded_rectangle(
            (W - 230, y + 48, W - 100, y + 128), radius=40, fill=theme["pill"]
        )
        d.text((W - 200, y + 70), "Log", font=f_food, fill=theme["pill_fg"])
        d.text((220, y + 140), food, font=f_food, fill=theme["dim"])
        d.text((220, y + 200), summary, font=f_sum, fill=theme["dim"])
        y += card_h + gap
    d.text((W // 2 - 190, y + 20), "Complete diary", font=f_title, fill=(40, 90, 220))
    return im


def summary(kcal: int, c, f, p, unit: str = "g", carbs_key: str = "NC") -> str:
    return f"{kcal} cal  •  {carbs_key} {c}{unit}   F {f}{unit}   P {p}{unit}"


FIXTURES: dict[str, tuple[str | None, list[Meal], dict]] = {
    "grams_nov4.png": (
        "Nov 4",
        [
            ("Breakfast", "Oatmeal and 3 more", summary(610, 55, 22, 38)),
            ("Lunch", "Lentil Soup and 2 more", summary(740, 70, 25, 45)),
            ("Dinner", "Grilled Fish and 4 more", summary(520, 30, 18, 50)),
            ("Snacks", "Apple and 1 more", summary(210, 25, 8, 6)),
        ],
        LIGHT,
    ),
    "percent_today.png": (
        "Today",
        [
            ("Breakfast", "Oatmeal and 3 more", summary(600, 40, 30, 30, unit="%")),
            ("Lunch", "Lentil Soup and 2 more", summary(800, 45, 25, 30, unit="%")),
            ("Dinner", "Grilled Fish and 4 more", summary(500, 20, 30, 50, unit="%")),
            ("Snacks", "Apple and 1 more", summary(200, 50, 30, 20, unit="%")),
        ],
        LIGHT,
    ),
    "dark_yesterday.png": (
        "Yesterday",
        [
            ("Breakfast", "Toast and 2 more", summary(450, 48, 14, 20, carbs_key="C")),
            ("Lunch", "Rice Bowl and 3 more", summary(690, 80, 20, 35, carbs_key="C")),
            ("Dinner", "Pasta and 1 more", summary(810, 95, 28, 30, carbs_key="C")),
            ("Snacks", "Yogurt", summary(150, 12, 5, 12, carbs_key="C")),
        ],
        DARK,
    ),
    # Lunch's carbs lost their unit, as a smudged screenshot does: the meal
    # must be skipped and reported, and the other three still read.
    "garbled_lunch.png": (
        "Nov 4",
        [
            ("Breakfast", "Oatmeal and 3 more", summary(610, 55, 22, 38)),
            ("Lunch", "Lentil Soup and 2 more", "740 cal  •  NC 7    F 25g   P 45g"),
            ("Dinner", "Grilled Fish and 4 more", summary(520, 30, 18, 50)),
            ("Snacks", "Apple and 1 more", summary(210, 25, 8, 6)),
        ],
        LIGHT,
    ),
    # Scrolled past the header: no date anywhere. Must be refused, not
    # assumed to be today.
    "no_header.png": (
        None,
        [
            ("Breakfast", "Oatmeal and 3 more", summary(610, 55, 22, 38)),
            ("Lunch", "Lentil Soup and 2 more", summary(740, 70, 25, 45)),
        ],
        LIGHT,
    ),
}


def main() -> None:
    for name, (header, meals, theme) in FIXTURES.items():
        render(header, meals, theme).save(HERE / name, optimize=True)
        print("wrote", name)


if __name__ == "__main__":
    main()
