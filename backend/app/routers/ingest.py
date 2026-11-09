"""POST /api/ingest/mfp -- MyFitnessPal screenshots in, meals logged, plain text out.

Called twice: once with `dry_run=true`, whose text the caller shows as a
preview, then, on confirmation, with `dry_run=false`. So the response is short
plain text, not JSON, and the same code path produces both: the dry run makes
the real writes and rolls them back.

**Two ways in, told apart by the Authorization header.** The web app's
Nutrition page sends none and rides on the session cookie like every other
route, so the meals go to whoever is signed in. An iPhone Shortcut has no
cookie and sends `Authorization: Bearer <MFP_INGEST_TOKEN>` instead, compared
in constant time; that token names no account, so the meals go to
`MFP_INGEST_USER`, or the only account. A request that carries the header is
judged on the header alone -- a wrong token is 401 even beside a valid cookie,
so a misconfigured Shortcut fails loudly rather than quietly logging as
somebody. The token is optional: unset, only the cookie path works, and
`token_matches` refuses an empty configured token as a second line.

The three layers, each testable alone: `app/mfp_ocr.py` (image -> numbers),
`app/mfp_ingest.py` (numbers -> rows, through `intake_log.log_meal`), and
this file (HTTP, auth, transaction).
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import mfp_ingest, mfp_ocr
from app.config import get_settings
from app.database import get_db
from app.intake_log import normalise_label
from app.mfp_ingest import DayWrite, IngestRefused, MealNumbers
from app.models import User
from app.routers.auth import get_current_user

logger = logging.getLogger("askesis.ingest")
router = APIRouter()

MAX_IMAGES = 10


def _text_error(status: int, text: str) -> HTTPException:
    # Errors arrive as FastAPI's {"detail": "<text>"}; the text is written to
    # be shown to a person as-is, and the web app unwraps it.
    return HTTPException(status_code=status, detail=text)


def ingest_account(request: Request, db: Session = Depends(get_db)) -> User:
    """Whose meals these are: the signed-in user, or the token's account."""
    auth = request.headers.get("authorization")
    request.state.via_token = auth is not None
    if auth is None:
        return get_current_user(request, db)
    settings = get_settings()
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not mfp_ingest.token_matches(
        token.strip(), settings.mfp_ingest_token
    ):
        raise HTTPException(
            status_code=401,
            detail="Missing or wrong token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = mfp_ingest.resolve_user(db, settings.mfp_ingest_user)
    if user is None:
        raise _text_error(
            503,
            "No account to log to. Set MFP_INGEST_USER to a username."
            if settings.mfp_ingest_user == ""
            else "MFP_INGEST_USER matches no account.",
        )
    return user


def _as_numbers(meal: mfp_ocr.MealRead) -> MealNumbers:
    return MealNumbers(
        label=meal.label,
        kcal=meal.kcal,
        protein_g=meal.protein_g,
        carbs_g=meal.carbs_g,
        fat_g=meal.fat_g,
    )


#: The Shortcut shows the response in an iOS alert, which truncates silently
#: at about this many lines. The web app shows it in a scrolling box.
ALERT_LINES = 12
PAGE_LINES = 200


@router.post("/mfp", response_class=PlainTextResponse)
async def ingest_mfp(
    request: Request,
    images: list[UploadFile] = File(...),
    today: str = Form(...),
    dry_run: bool = Form(True),
    force: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(ingest_account),
) -> PlainTextResponse:
    """Read the screenshots and log their meals (or preview, with dry_run).

    `today` is the CLIENT's date as YYYY-MM-DD; "Today"/"Yesterday" in a
    screenshot resolve against it and the server clock is never consulted.
    """
    settings = get_settings()
    problem = mfp_ingest.tesseract_problem()
    if problem:
        raise _text_error(503, f"OCR unavailable: {problem}")
    try:
        today_d = date.fromisoformat(today)
    except ValueError:
        raise _text_error(400, f"today must be YYYY-MM-DD, got {today!r}") from None
    if not images:
        raise _text_error(400, "No images.")
    if len(images) > MAX_IMAGES:
        raise _text_error(400, f"At most {MAX_IMAGES} images per request.")
    blobs: list[bytes] = []
    for up in images:
        blob = await up.read()
        if len(blob) > settings.max_image_size:
            raise _text_error(413, f"{up.filename or 'image'} is too large.")
        blobs.append(blob)

    try:
        days = mfp_ocr.parse_screenshots(blobs, today_d)
    except mfp_ocr.ParseError as exc:
        raise _text_error(422, str(exc)) from None

    results: list[DayWrite] = []
    try:
        for read in days:
            results.append(_write_one(db, user.id, read, dry_run=dry_run, force=force))
    except IngestRefused as exc:
        db.rollback()
        raise _text_error(409, str(exc)) from None

    if dry_run:
        db.rollback()
    else:
        db.commit()
        for r in results:
            # Counts, never values: the log is an audit trail, not a copy.
            logger.info(
                "MFP import for user %s on %s: wrote %d, unchanged %d, skipped %d",
                user.id,
                r.day,
                r.written,
                r.unchanged,
                r.skipped,
            )
    compact = getattr(request.state, "via_token", False)
    return PlainTextResponse(
        mfp_ingest.render(results, max_lines=ALERT_LINES if compact else PAGE_LINES)
    )


def _write_one(
    db: Session, user_id: int, read: mfp_ocr.DayRead, *, dry_run: bool, force: bool
) -> DayWrite:
    """One day: the parser's notes become warnings, its meals go to `write_day`.

    In a dry run a refusal is a warning line and the screenshot's meals are
    listed plainly, so the preview shows the problem next to the numbers that
    `force` would write; in a real run it propagates and the whole request is
    rolled back, because writing some days and refusing others would leave
    the user guessing which happened.
    """
    meals = [_as_numbers(m) for m in read.meals.values()]
    flags = [
        f"{normalise_label(m.label)}: macros explain {round(m.macro_kcal)} of {m.kcal} kcal"
        for m in read.meals.values()
        if not m.adds_up()
    ]
    derived = [m.label for m in read.meals.values() if m.from_percent]
    if not meals:
        out = DayWrite(day=read.day, dry_run=dry_run, day_total_kcal=0)
    else:
        try:
            out = mfp_ingest.write_day(
                db, user_id, read.day, meals, dry_run=dry_run, force=force
            )
        except IngestRefused as exc:
            if not dry_run:
                raise
            out = DayWrite(
                day=read.day,
                dry_run=True,
                skipped=len(meals),
                day_total_kcal=sum(m.kcal for m in meals),
                lines=[mfp_ingest.plain_meal_line(m) for m in meals],
            )
            out.warnings.append(f"refused: {exc}")
    out.warnings.extend(read.notes)
    out.warnings.extend(flags)
    if derived:
        out.warnings.append(f"{', '.join(derived)}: grams derived from the % view")
    return out
