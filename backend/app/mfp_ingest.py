"""Write a day of MyFitnessPal meals into the food log -- the parts that are not OCR.

`mfp_ocr.py` turns screenshots into numbers and knows nothing about the
database. This module takes those numbers and knows nothing about images. The
router (`routers/ingest.py`) is the thin HTTP skin over both. Keeping the three
apart is what lets the parser be tested against fixture images with no server,
and the writes be tested with no Tesseract.

**Every meal goes through `intake_log.log_meal(mode="replace")`.** That is the
same call the MCP connector's `log_meal` tool makes, and it is the only place
that knows the rule "a meal's macros move the day's total by exactly that
meal's change". Nothing here writes a `Meal` row directly. Resending the same
screenshot therefore changes nothing: replace of equal numbers is a no-op, and
the day's total moves by zero.

**The double-count guard.** Days logged before meals carried their own macros
hold the whole day's protein/carbs/fat on `DailyNutrition` with nothing on the
meals (`log_day_nutrition`, and the Daily Log's own macro boxes). Writing
per-meal macros on top of that *adds* each meal's grams to a total that already
contains them. So before writing, the day's stored total is compared with the
sum of its meals' macros: a gap means some grams are accounted for by no meal,
and the write refuses unless forced. Forcing first sets the day's total equal
to its meals' sum -- dropping the unaccounted grams, and the warning says how
many -- so that after the meals are written the day equals exactly what the
screenshot said. Writing through without that rebase would be the double count
the guard exists to prevent, which is why `force` is not "write anyway".

The guard is skipped when the request changes nothing. A day the importer
wrote and the user then nudged by hand (10 g of protein for an unlogged snack)
has a gap, and must keep it; resending that day's screenshot is a no-op and
should say so rather than refuse.

**Each meal is its own savepoint.** `log_meal` validates before it mutates
with one exception -- the day-total bound inside `_shift_day` fires after the
meal row has been set -- and this module catches a meal's error and carries on
with the next. Without the savepoint the next meal's flush would persist the
half-written one. In the MCP path the whole call rolls back, so it never saw
this.

Dates are decided by the caller. The phone says what "today" is; this module
never consults the server clock, because the server runs UTC and the person
holding the phone moves between time zones.
"""

from __future__ import annotations

import hmac
import shutil
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app import intake_log
from app.intake_log import MACRO_FIELDS, MEAL_LABELS, IntakeError
from app.models import DailyNutrition, Meal, User

#: Rounding slack when comparing a day's total with the sum of its meals. Each
#: meal is stored to 0.1 g and there are at most four, so anything beyond half
#: a gram is a real discrepancy, not arithmetic.
GAP_TOLERANCE_G = 0.5


class IngestRefused(ValueError):
    """The request is understood but must not be written as-is."""


# ── identity ─────────────────────────────────────────────────────────────────


def token_matches(presented: str | None, configured: str) -> bool:
    """Constant-time check of a Bearer token against the configured one.

    An empty configured token never matches -- the route should not be mounted
    in that case, and this is the backstop if it somehow is.
    """
    if not configured or not presented:
        return False
    return hmac.compare_digest(presented.encode(), configured.encode())


def resolve_user(db: Session, configured: str) -> User | None:
    """The account the screenshots belong to: the named one, or the only one.

    Mirrors the Garmin sync's rule. Two accounts and no setting is a refusal,
    not a guess: logging one person's lunch into another's day is worse than
    an error message. Two matches for a name (one account's username equal to
    another's email) is the same refusal.
    """
    query = db.query(User)
    if configured:
        query = query.filter((User.username == configured) | (User.email == configured))
    users = query.limit(2).all()
    return users[0] if len(users) == 1 else None


def tesseract_problem() -> str | None:
    """Why OCR cannot run here, or None if it can.

    Checked once at startup so a missing binary is one clear log line rather
    than a stack trace on the first upload.
    """
    if shutil.which("tesseract") is None:
        return (
            "the `tesseract` binary is not on PATH. Install the tesseract-ocr "
            "package (the Dockerfile does). The route answers 503 until it is."
        )
    return None


# ── the double-count guard ───────────────────────────────────────────────────


def _short(macro_field: str) -> str:
    return macro_field[:-2]  # protein_g -> protein


@dataclass
class MacroGap:
    """How far a day's stored macro totals sit from the sum of its meals."""

    day: dict[str, float]
    meals: dict[str, float]
    meal_count: int

    @property
    def fields(self) -> list[str]:
        return [
            f
            for f in MACRO_FIELDS
            if abs(self.day[f] - self.meals[f]) > GAP_TOLERANCE_G
        ]

    def __bool__(self) -> bool:
        return bool(self.fields)

    @property
    def unaccounted(self) -> dict[str, float]:
        """Grams on the day that no meal explains -- what `force` drops."""
        return {
            f: round(self.day[f] - self.meals[f], 1)
            for f in self.fields
            if self.day[f] > self.meals[f]
        }

    def describe(self) -> str:
        return ", ".join(
            f"{_short(f)} {self.day[f]:g}g on the day vs {self.meals[f]:g}g in meals"
            for f in self.fields
        )

    def describe_dropped(self) -> str:
        dropped = self.unaccounted
        if not dropped:
            # Day sits BELOW its meals: lowered by hand, or the clamp in
            # `_shift_day`. Rebasing raises it; nothing is lost.
            return "day totals raised to match the meals"
        return (
            "dropping "
            + ", ".join(f"{v:g}g {_short(f)}" for f, v in dropped.items())
            + " that no meal accounts for"
        )


def _day_meals(db: Session, user_id: int, day: date) -> list[Meal]:
    return (
        db.query(Meal)
        .filter(Meal.user_id == user_id, Meal.date == day, Meal.deleted_at.is_(None))
        .all()
    )


def _day_row(db: Session, user_id: int, day: date) -> DailyNutrition | None:
    return (
        db.query(DailyNutrition)
        .filter(DailyNutrition.user_id == user_id, DailyNutrition.date == day)
        .first()
    )


def macro_gap(db: Session, user_id: int, day: date) -> MacroGap:
    """Compare the day's `DailyNutrition` macros with the sum over its meals."""
    meals = _day_meals(db, user_id, day)
    nutrition = _day_row(db, user_id, day)
    return MacroGap(
        day={f: float(getattr(nutrition, f) or 0) for f in MACRO_FIELDS}
        if nutrition
        else {f: 0.0 for f in MACRO_FIELDS},
        meals={
            f: round(sum(float(getattr(m, f) or 0) for m in meals), 1)
            for f in MACRO_FIELDS
        },
        meal_count=len(meals),
    )


def rebase_day_to_meals(db: Session, user_id: int, day: date, gap: MacroGap) -> None:
    """Set the day's totals to what its meals add up to, dropping the rest.

    The `force` path. After this, `log_meal`'s delta arithmetic lands the day
    on exactly the screenshot's numbers. Only the macro columns move; the
    day's notes and the meals themselves are untouched.
    """
    nutrition = _day_row(db, user_id, day)
    if nutrition is None:
        nutrition = DailyNutrition(user_id=user_id, date=day)
        db.add(nutrition)
    for f in MACRO_FIELDS:
        setattr(nutrition, f, gap.meals[f])
    db.flush()


# ── the write ────────────────────────────────────────────────────────────────


@dataclass
class MealNumbers:
    """One meal as read from a screenshot. Grams may be unknown (`None`)."""

    label: str
    kcal: int
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None

    def given(self) -> dict[str, float]:
        return {
            f: round(float(v), 1)
            for f, v in (
                ("protein_g", self.protein_g),
                ("carbs_g", self.carbs_g),
                ("fat_g", self.fat_g),
            )
            if v is not None
        }


@dataclass
class DayWrite:
    """What writing one day did, or would do. Rendered by `render`."""

    day: date
    dry_run: bool
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    written: int = 0
    unchanged: int = 0
    skipped: int = 0
    day_total_kcal: int | None = None


def _already_holds(rows: list[Meal], m: MealNumbers) -> bool:
    """True if the day's single row for this label already has these numbers."""
    if len(rows) != 1:
        return False
    row = rows[0]
    if row.calories != m.kcal:
        return False
    return all(getattr(row, f) == v for f, v in m.given().items())


def _would_skip(rows: list[Meal]) -> str | None:
    """Why `log_meal` will refuse this label, mirroring its own two rules."""
    if len(rows) > 1:
        return f"{len(rows)} rows"
    if rows and rows[0].food_items:
        return "itemised in the app"
    return None


def write_day(
    db: Session,
    user_id: int,
    day: date,
    meals: list[MealNumbers],
    *,
    dry_run: bool,
    force: bool,
) -> DayWrite:
    """Write one day's meals through `log_meal`, or report what that would do.

    Nothing here commits; the caller owns the transaction. A dry run makes the
    same calls inside the session and the caller rolls back, so the preview is
    the real code path and not a second implementation of it.

    Raises `IngestRefused` when the double-count guard trips and `force` is
    off -- before anything is written.
    """
    out = DayWrite(day=day, dry_run=dry_run)

    # Normalise and dedupe first, so the guard reasons about the real request.
    wanted: list[tuple[str, MealNumbers]] = []
    seen: set[str] = set()
    for m in meals:
        try:
            label = intake_log.normalise_label(m.label)
            if label in seen:
                raise IntakeError(f"{label} appears twice in this request.")
        except IntakeError as exc:
            out.skipped += 1
            out.lines.append(f"{m.label}: skipped -- {exc}")
            continue
        seen.add(label)
        wanted.append((label, m))

    rows_by_label = {
        label: [r for r in _day_meals(db, user_id, day) if r.label == label]
        for label, _ in wanted
    }
    all_unchanged = bool(wanted) and all(
        _already_holds(rows_by_label[label], m) for label, m in wanted
    )

    gap = macro_gap(db, user_id, day)
    if gap and not all_unchanged:
        if not force:
            raise IngestRefused(
                f"{day}: day macros don't match its meals ({gap.describe()}). "
                + (
                    "Those grams were logged for the day as a whole; writing "
                    "meals on top would count them twice. "
                    if gap.unaccounted
                    else "The day was lowered below its meals. "
                )
                + "Resend with force=true to make the day equal the screenshot."
            )
        out.warnings.append(f"forced: {gap.describe_dropped()}")
        for label, _ in wanted:
            why = _would_skip(rows_by_label[label])
            if why and gap.unaccounted:
                out.warnings.append(
                    f"{label} is {why} and will be skipped; any of its grams "
                    "typed into the day are in what is dropped"
                )
        rebase_day_to_meals(db, user_id, day, gap)

    for label, m in wanted:
        try:
            with db.begin_nested():
                result = intake_log.log_meal(
                    db,
                    user_id,
                    day,
                    label,
                    kcal=m.kcal,
                    protein_g=m.protein_g,
                    carbs_g=m.carbs_g,
                    fat_g=m.fat_g,
                    mode="replace",
                )
        except IntakeError as exc:
            out.skipped += 1
            out.lines.append(f"{label}: skipped -- {exc}")
            continue
        if result["before"] != result["after"]:
            out.written += 1
        else:
            out.unchanged += 1
        out.lines.append(_meal_line(label, m, result))
        out.day_total_kcal = result["day_total_kcal"]

    if out.day_total_kcal is None:
        out.day_total_kcal = sum(r.calories or 0 for r in _day_meals(db, user_id, day))
    return out


def _macros(m: MealNumbers) -> str:
    return " ".join(f"{f[0].upper()}{v:g}" for f, v in m.given().items())


def plain_meal_line(m: MealNumbers) -> str:
    """A meal as read, with no before/after: for a preview that refused."""
    return f"{intake_log.normalise_label(m.label)}: {m.kcal} kcal {_macros(m)}".rstrip()


def _meal_line(label: str, m: MealNumbers, result: dict[str, Any]) -> str:
    macros = _macros(m)
    before, after = result["before"], result["after"]
    if result["result"] == "created":
        state = "new"
    elif before == after:
        state = "same"
    elif before["kcal"] != after["kcal"]:
        state = f"was {before['kcal']} kcal"
    else:
        state = "macros changed"
    body = f"{label}: {m.kcal} kcal {macros}".rstrip()
    return f"{body} ({state})"


def render(days: list[DayWrite], *, max_lines: int = 12) -> str:
    """Plain text for a phone alert: one line per meal, then the verdict.

    Capped at `max_lines` because an iPhone Shortcut alert truncates silently.
    A day with four meals and a warning fits; several days get their meal
    lines cut, and the verdict line is always kept -- it is the one line that
    says whether anything was written.
    """
    if not days:
        return "No meals found in the screenshots."
    body: list[str] = []
    for d in days:
        total = "?" if d.day_total_kcal is None else str(d.day_total_kcal)
        head = f"{d.day:%a %b %-d}: {total} kcal"
        if d.dry_run:
            head = f"[preview] {head}"
        body.append(head)
        body.extend(f"  {line}" for line in d.lines)
        body.extend(f"  ! {w}" for w in d.warnings)
    total_written = sum(d.written for d in days)
    total_skipped = sum(d.skipped for d in days)
    verdict = (
        f"Would write {total_written}" if days[0].dry_run else f"Wrote {total_written}"
    )
    if total_skipped:
        verdict += f", skipped {total_skipped}"
    verdict += "."
    if len(body) + 1 > max_lines:
        body = _trim(body, keep=max_lines - 2)
    return "\n".join(body + [verdict])


def _trim(body: list[str], *, keep: int) -> list[str]:
    """Drop lines until `keep` remain, least important first.

    Meal lines go first (from the end), then warnings, then day headings.
    Warnings outlive meal lines because one of them may be "refused: ...",
    the line that tells the caller why nothing will be written and that
    `force` exists -- cutting it turned a multi-day preview into a surprise
    409. The marker line is counted in `keep`.
    """
    cut = len(body) - keep
    if cut <= 0:
        return body
    meals = [i for i, ln in enumerate(body) if ln.startswith("  ") and ln[2] != "!"]
    warnings = [i for i, ln in enumerate(body) if ln.startswith("  !")]
    heads = [i for i, ln in enumerate(body) if not ln.startswith("  ")]
    order = meals[::-1] + warnings[::-1] + heads[::-1]
    drop = set(order[:cut])
    return [ln for i, ln in enumerate(body) if i not in drop] + [
        f"... {cut} more lines"
    ]


__all__ = [
    "MEAL_LABELS",
    "DayWrite",
    "IngestRefused",
    "MacroGap",
    "MealNumbers",
    "macro_gap",
    "render",
    "resolve_user",
    "tesseract_problem",
    "token_matches",
    "write_day",
]
