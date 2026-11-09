"""Read MyFitnessPal's "Meals" screen from a screenshot. OCR plus a strict regex.

No model, no network. The screen is the same every day -- four cards, each
with a title and one summary line:

    Breakfast
    Oatmeal and 4 more
    640 cal • NC 58g  F 24g  P 35g

so a regex is enough, and a regex that fails is better than a guess: a meal
whose summary line does not read cleanly is **skipped and reported**, never
filled in. The macro letters follow the user's MyFitnessPal settings (NC is net
carbs; C, F and P are carbs, fat, protein) and can be in any order; in the
percent view they come as `NC 33%  F 49%  P 14%`, from which grams are derived
(4 kcal/g for carbs and protein, 9 for fat) and marked as such. When one day
arrives in several screenshots, a reading in grams beats one derived from
percentages.

**The date is the phone's business.** A screenshot says "Today", "Yesterday"
or "Nov 4", and only the device that took it knows what day that was: the
server runs UTC and the person moves between time zones. So every call takes
`today` from the client and resolves against it. An image whose header cannot
be read is refused rather than assumed to be today.

**Framework-free, deliberately.** Only Pillow and pytesseract. The tests run it
against fixture images with no server, and the router stays a thin skin.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from PIL import Image, ImageOps, UnidentifiedImageError

MEAL_TITLES = ("Breakfast", "Lunch", "Dinner", "Snacks")

#: kcal per gram. Used to turn the percent view into grams and to check that a
#: meal's macros roughly explain its calories.
KCAL_PER_G = {"carbs_g": 4.0, "fat_g": 9.0, "protein_g": 4.0}

#: A meal is flagged (not skipped) when its macros are this far from its
#: calories. Net carbs leave fibre and sugar alcohols out, and alcohol has
#: calories with no macro at all, so a loose bound: 15 % or 50 kcal.
ADDS_UP_RATIO = 0.15
ADDS_UP_MIN_KCAL = 50

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}

#: The header: "Today", "Yesterday", or "Nov 4" (OCR often drops the space:
#: "Nov4"), optionally with a year, optionally preceded by a weekday. Searched
#: only ABOVE the "Meals" heading, so a food called "Today's Special" cannot
#: become the date.
_DATE_RE = re.compile(
    r"\b(?:(?P<rel>today|yesterday)|"
    r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s*)?"
    r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s*(?P<day>\d{1,2})(?:,?\s*(?P<year>\d{4}))?)\b",
    re.IGNORECASE,
)

_TITLE_RE = re.compile(
    r"^\W*(?P<title>Breakfast|Lunch|Dinner|Snacks?)\b", re.IGNORECASE
)
_KCAL_RE = re.compile(
    r"(?<![\d.])(?P<kcal>\d{1,2}(?:,\d{3})+|\d{1,5})\s*cal\b", re.IGNORECASE
)
#: One macro token: the letter(s), the number, and g or %. `\b` on the letter
#: side keeps "F" in "Fat-Free" from matching: it must be its own word.
_MACRO_RE = re.compile(
    r"\b(?P<key>NC|C|F|P)\s*(?P<val>\d+(?:[.,]\d+)?)\s*(?P<unit>g|%)(?![a-z])",
    re.IGNORECASE,
)
_KEY_FIELD = {"NC": "carbs_g", "C": "carbs_g", "F": "fat_g", "P": "protein_g"}


class ParseError(ValueError):
    """An image that cannot be used at all (no readable date)."""


@dataclass
class MealRead:
    """One meal's summary line, as read."""

    label: str  # as MyFitnessPal titles it: Breakfast / Lunch / Dinner / Snacks
    kcal: int
    carbs_g: float
    fat_g: float
    protein_g: float
    from_percent: bool = False

    @property
    def macro_kcal(self) -> float:
        return sum(getattr(self, f) * k for f, k in KCAL_PER_G.items())

    def adds_up(self) -> bool:
        if self.from_percent:
            return True  # derived from the calories, so trivially
        gap = abs(self.kcal - self.macro_kcal)
        return gap <= max(ADDS_UP_MIN_KCAL, ADDS_UP_RATIO * self.kcal)

    def numbers(self) -> tuple[int, float, float, float]:
        return (self.kcal, self.carbs_g, self.fat_g, self.protein_g)


@dataclass
class DayRead:
    """Everything read for one calendar day, possibly from several images."""

    day: date
    meals: dict[str, MealRead] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    images: int = 0


# ── OCR ──────────────────────────────────────────────────────────────────────


def ocr_text(image_bytes: bytes) -> str:
    """Tesseract's reading of the image, one line per screen line.

    Greyscale, and inverted when the screenshot is in dark mode -- Tesseract
    wants dark text on light. `--psm 6` ("a single uniform block") keeps each
    card's summary on one line, which the regexes rely on; the sparse modes
    split "640 cal" from its macros.
    """
    import pytesseract  # imported here so the module loads without it

    with Image.open(io.BytesIO(image_bytes)) as im:
        grey = ImageOps.grayscale(im)
        if _mean_luminance(grey) < 128:
            grey = ImageOps.invert(grey)
        if grey.width < 1000:
            # A downscaled or shared-at-lower-quality screenshot. 1000 px wide
            # keeps the ~30 px summary text above Tesseract's comfort line.
            scale = 1000 / grey.width
            grey = grey.resize((1000, round(grey.height * scale)), Image.LANCZOS)
        return pytesseract.image_to_string(grey, config="--psm 6")


def _mean_luminance(grey: Image.Image) -> float:
    hist = grey.histogram()
    total = sum(hist)
    return sum(i * n for i, n in enumerate(hist)) / total if total else 255.0


# ── text → numbers ───────────────────────────────────────────────────────────


def resolve_date(text: str, today: date) -> date | None:
    """The date in the header, or None if there is none readable.

    Only the text above the "Meals" heading counts. Month-day without a year
    is the most recent such date not after `today`, so "Dec 30" read on
    January 2nd is last year's.
    """
    head = re.split(
        r"^\W*Meals\b", text, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE
    )[0]
    m = _DATE_RE.search(head)
    if not m:
        return None
    if m.group("rel"):
        return today if m.group("rel").lower() == "today" else today - timedelta(days=1)
    month = _MONTHS[m.group("mon").lower()]
    day = int(m.group("day"))
    if m.group("year"):
        try:
            return date(int(m.group("year")), month, day)
        except ValueError:
            return None
    for year in (today.year, today.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate <= today:
            return candidate
    return None


def parse_meals(text: str) -> tuple[list[MealRead], list[str]]:
    """Every meal card whose summary line reads cleanly, and why the others did not.

    A card is a title line followed within a few lines by its summary. The
    summary must carry calories and exactly one each of carbs (NC or C), fat
    and protein, all in the same unit. Anything less is a skipped meal with a
    note, so a misread digit cannot become a logged number.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    meals: list[MealRead] = []
    notes: list[str] = []
    seen: set[str] = set()
    claimed: set[int] = set()  # indexes of summary lines attributed to a title
    for i, line in enumerate(lines):
        t = _TITLE_RE.match(line)
        if not t:
            continue
        title = t.group("title").capitalize()
        if title == "Snack":
            title = "Snacks"
        if title in seen:
            continue  # the second "Breakfast" on a scrolled diary view
        # The summary is the next line that mentions calories. The food line
        # between can wrap to two, so look a little way ahead.
        j = next(
            (
                k
                for k in range(i + 1, min(i + 5, len(lines)))
                if _KCAL_RE.search(lines[k])
            ),
            None,
        )
        if j is None:
            notes.append(f"{title}: no calories line found")
            seen.add(title)
            continue
        claimed.add(j)
        read, why = _parse_summary(title, lines[j])
        if read is None:
            notes.append(f"{title}: {why} ({lines[j]!r})")
        else:
            meals.append(read)
        seen.add(title)
    # A calories line nobody claimed means a title went unread. Say so rather
    # than guess which meal it was: the order on screen is a convention, not a
    # label, and a wrong attribution is worse than a skipped meal.
    for k, line in enumerate(lines):
        if k not in claimed and _KCAL_RE.search(line) and _MACRO_RE.search(line):
            notes.append(f"a meal's title did not read; skipped ({line!r})")
    return meals, notes


def _parse_summary(title: str, line: str) -> tuple[MealRead | None, str]:
    k = _KCAL_RE.search(line)
    if not k:
        return None, "no calories"
    kcal = int(k.group("kcal").replace(",", ""))
    tokens = _MACRO_RE.findall(line[k.end() :])
    found: dict[str, float] = {}
    units: set[str] = set()
    for key, val, unit in tokens:
        f = _KEY_FIELD[key.upper()]
        if f in found:
            return None, "a macro appears twice"
        found[f] = float(val.replace(",", "."))
        units.add(unit)
    missing = [f for f in KCAL_PER_G if f not in found]
    if missing:
        return None, "macros not fully readable"
    if len(units) != 1:
        return None, "mixed units"
    if units == {"%"}:
        if sum(found.values()) > 110:
            return None, "percentages do not add up"
        grams = {f: round(kcal * found[f] / 100 / KCAL_PER_G[f], 1) for f in found}
        return MealRead(title, kcal, from_percent=True, **grams), ""
    return MealRead(title, kcal, **found), ""


# ── images → days ────────────────────────────────────────────────────────────


def parse_screenshots(images: list[bytes], today: date) -> list[DayRead]:
    """Read every image and merge them by day, oldest day first.

    Raises `ParseError` for an image with no readable date: it cannot be
    placed, and guessing "today" would log it to the wrong day silently.
    """
    days: dict[date, DayRead] = {}
    for n, blob in enumerate(images, start=1):
        try:
            text = ocr_text(blob)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            # Pillow raises UnidentifiedImageError for a file it cannot
            # decode and OSError for a truncated one; a web picker's
            # `accept="image/*"` lets both through. A bad upload is the
            # caller's problem to hear about, not a 500.
            raise ParseError(f"image {n}: not a readable image ({exc})") from None
        day = resolve_date(text, today)
        if day is None:
            raise ParseError(
                f"image {n}: no date in the header (expected Today, Yesterday or "
                "a month and day above 'Meals')"
            )
        if day > today:
            raise ParseError(f"image {n}: {day} is after today ({today})")
        read = days.setdefault(day, DayRead(day=day))
        read.images += 1
        meals, notes = parse_meals(text)
        read.notes.extend(notes)
        for meal in meals:
            _merge(read, meal)
    return [days[d] for d in sorted(days)]


def _merge(read: DayRead, meal: MealRead) -> None:
    current = read.meals.get(meal.label)
    if current is None:
        read.meals[meal.label] = meal
        return
    if current.from_percent and not meal.from_percent:
        read.meals[meal.label] = meal  # grams beat percentages
        return
    if not current.from_percent and meal.from_percent:
        return
    if current.numbers() != meal.numbers():
        read.notes.append(
            f"{meal.label}: two screenshots disagree "
            f"({current.kcal} vs {meal.kcal} kcal); kept the later one"
        )
        read.meals[meal.label] = meal


__all__ = [
    "DayRead",
    "MealRead",
    "ParseError",
    "ocr_text",
    "parse_meals",
    "parse_screenshots",
    "resolve_date",
]
