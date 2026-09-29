"""The planning half of the app: the exercise library, routines and targets.

**Plain SQLAlchemy. No FastAPI.** That is the point of the module existing: it
is imported by the routers *and* by `mcp_server/`, which cannot import anything
under `app.routers` — CI greps for it, and the MCP image ships no FastAPI, so
the import would fail at boot even if the grep let it through.

Without this module the MCP write tools would need a second copy of every rule
here: the URL scheme check, the duplicate-then-revive branch, the rename
collision, the replace-all for a routine's movements, the clearable-target
semantics. This repo has paid for that mistake twice already — three write paths
for `daily_logs` where only two learned the provenance rule, and two
`_write_exercises` that disagreed about what an empty list means. One
implementation, two callers.

**Nothing here commits.** The caller owns the transaction: a router commits per
request, and the MCP layer commits once per tool call. Returning without
committing is deliberate, not an omission.

Errors are `PlanningError`, a plain `ValueError` subclass carrying text written
to be read by a person or a model. Routers map it to 4xx; the MCP layer maps it
to `ToolError`. Neither layer has to know the other's vocabulary.

## What is deliberately NOT here

Logged history — activities, sets, daily logs, meals, measurements. The line
this module draws is **what you intend** versus **what you did**, and only the
first is something an assistant should be able to change on your behalf. Moving
a write for logged data in here would quietly widen what the MCP connector can
touch, because the connector's permission is "everything in this module".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.disciplines import DISCIPLINE_KEYS
from app.models import (
    ActivityType,
    ExerciseCatalog,
    RoutineExercise,
    UserSettings,
    WorkoutTemplate,
)


class PlanningError(ValueError):
    """A bad request, phrased for whoever made it.

    A `ValueError` rather than an HTTP exception so this module stays free of
    FastAPI. Callers translate: the routers to `HTTPException`, the MCP tools to
    `ToolError`, both preserving the message because it is written to be read.
    """

    def __init__(self, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        #: True for "that already exists" — the routers turn this into 409
        #: rather than 400, which a client distinguishes.
        self.conflict = conflict


# ── The shared exercise library ──────────────────────────────────────────────
#
# Rows with `user_id IS NULL` belong to the install rather than to a person:
# this is a household app and a movement one account adds has to be usable by
# the other. See ExerciseCatalog in models.py for the partial unique index that
# keeps the shared half free of duplicate names.

#: Schemes a video link may use. `Activity.url` accepts anything and nothing in
#: the stack blocks `javascript:`; this column is newer and starts stricter.
_ALLOWED_URL_SCHEMES = ("http://", "https://")


#: Column limits, restated here because this module is the only validator the
#: MCP path passes through. They were left behind in the routers' Pydantic
#: schemas when the rest of the rules moved here -- so a tool could write 2500
#: characters of notes into a Text column, which committed happily and then made
#: `GET /api/exercise-catalog/` fail its response model on every subsequent
#: call. A 500 on the list endpoint is unrecoverable from the UI, because the
#: page that would let you fix the row is the one that will not load.
#:
#: Anything writable from here needs a bound. A `Text` column has no natural one
#: and is the dangerous case: `varchar` at least raises at the database.
MAX_NAME = 100
MAX_MUSCLE_GROUP = 50
MAX_VIDEO_URL = 500
MAX_CATALOG_NOTES = 2000
MAX_ROUTINE_NOTES = 255


def clean_text(
    value: str | None, limit: int, *, field: str, allow_blank: bool = True
) -> str | None:
    """Trim an optional free-text field to something the column and the API accept."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlanningError(f"{field} must be text, got {type(value).__name__}")
    cleaned = value.strip()
    if not cleaned:
        return None if allow_blank else cleaned
    if len(cleaned) > limit:
        raise PlanningError(
            f"{field} is too long: {len(cleaned)} characters, maximum is {limit}"
        )
    return cleaned


def clean_name(value: str | None, *, field: str = "name") -> str:
    """Strip and reject blank.

    A length check alone is not enough: `min_length=1` counts characters, so
    "   " passes it and lands as an unselectable blank row in a library both
    accounts see.
    """
    if value is not None and not isinstance(value, str):
        raise PlanningError(f"{field} must be text, got {type(value).__name__}")
    cleaned = (value or "").strip()
    if not cleaned:
        raise PlanningError(f"{field} cannot be blank")
    if len(cleaned) > MAX_NAME:
        raise PlanningError(
            f"{field} is too long: {len(cleaned)} characters, maximum is {MAX_NAME}"
        )
    return cleaned


def clean_video_url(value: str | None) -> str | None:
    """Normalise a link, or refuse it.

    Empty or whitespace becomes None rather than "", so a cleared field reads as
    absent everywhere downstream.

    The scheme test is case-insensitive, which the version this was extracted
    from was not: it compared with a bare `str.startswith` against lowercase
    prefixes, so a perfectly good `HTTPS://youtu.be/...` was rejected with a
    message about needing to start with `https://`.
    """
    if value is None or not value.strip():
        return None
    cleaned = value.strip()
    if not cleaned.lower().startswith(_ALLOWED_URL_SCHEMES):
        raise PlanningError("video_url must start with http:// or https://")
    if len(cleaned) > MAX_VIDEO_URL:
        raise PlanningError(
            f"video_url is too long: {len(cleaned)} characters, "
            f"maximum is {MAX_VIDEO_URL}"
        )
    return cleaned


def visible_catalog(db: Session, user_id: int):
    """Rows this account may see: the shared library plus anything of its own."""
    return db.query(ExerciseCatalog).filter(
        ExerciseCatalog.deleted_at.is_(None),
        or_(
            ExerciseCatalog.user_id.is_(None),
            ExerciseCatalog.user_id == user_id,
        ),
    )


def visible_catalog_ids(db: Session, user_id: int, ids) -> set[int]:
    """Which of `ids` this account is allowed to point an exercise at.

    Both activity write paths take `catalog_id` from the client and neither
    checked it. Two ways that bites: an id that does not exist raises a foreign
    key violation and 500s the save, and an id belonging to the *other* account's
    private entries would link your session to a row you cannot see -- so the
    name on your own exercise would be one you have no way to read or edit.
    Callers null out anything this does not return.
    """
    wanted = {int(i) for i in ids if i is not None}
    if not wanted:
        return set()
    rows = db.query(ExerciseCatalog.id).filter(
        ExerciseCatalog.id.in_(wanted),
        ExerciseCatalog.deleted_at.is_(None),
        or_(ExerciseCatalog.user_id.is_(None), ExerciseCatalog.user_id == user_id),
    )
    return {row.id for row in rows}


def catalog_by_name(db: Session, user_id: int, name: str) -> ExerciseCatalog | None:
    """The visible entry with this name, matched the way the index dedupes.

    ``func.lower(name) ==`` rather than ``ilike``: ilike treats % and _ in the
    argument as wildcards, so an exercise called "100%% effort" would match rows
    it is not. Ordering puts a shared row ahead of a personal one, and this
    takes the first rather than ``one_or_none`` -- pre-index duplicates can
    exist in an install that upgraded, and a 500 is a worse answer than a
    slightly arbitrary one.
    """
    return (
        visible_catalog(db, user_id)
        .filter(func.lower(ExerciseCatalog.name) == name.lower())
        .order_by(ExerciseCatalog.user_id.is_(None).desc(), ExerciseCatalog.id)
        .first()
    )


def search_catalog(
    db: Session,
    user_id: int,
    q: str | None = None,
    *,
    include_archived: bool = False,
    limit: int = 200,
) -> list[ExerciseCatalog]:
    """Name search over the visible library."""
    query = visible_catalog(db, user_id)
    if not include_archived:
        query = query.filter(ExerciseCatalog.is_archived.is_(False))
    if q:
        # Escape the wildcards, or searching for "_" returns the whole library.
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(ExerciseCatalog.name.ilike(f"%{pattern}%", escape="\\"))
    return query.order_by(ExerciseCatalog.name).limit(limit).all()


def create_catalog_entry(
    db: Session,
    user_id: int,
    *,
    name: str,
    muscle_group: str | None = None,
    video_url: str | None = None,
    notes: str | None = None,
) -> tuple[ExerciseCatalog, bool]:
    """Add a movement to the shared library. Returns (entry, revived).

    `user_id` is left NULL on the row deliberately: the entry is the household's,
    so the other account sees it immediately and the partial unique index can
    stop the two of you creating "Squat" twice. Attributing it to the creator
    would defeat both, because a per-user unique constraint cannot see across
    accounts.

    `revived` is True when an archived entry came back rather than a new row
    being created — re-adding something archived is the common case, a movement
    returning to a program, and refusing it would leave the caller stuck with no
    obvious remedy.
    """
    name = clean_name(name)
    video_url = clean_video_url(video_url)
    muscle_group = clean_text(muscle_group, MAX_MUSCLE_GROUP, field="muscle_group")
    notes = clean_text(notes, MAX_CATALOG_NOTES, field="notes")

    existing = catalog_by_name(db, user_id, name)
    if existing is not None:
        if existing.is_archived:
            existing.is_archived = False
            return existing, True
        raise PlanningError(f"'{name}' is already in the list", conflict=True)

    entry = ExerciseCatalog(
        user_id=None,
        is_shared=True,
        name=name,
        muscle_group=muscle_group,
        video_url=video_url,
        notes=notes,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        # The other account added the same movement between the check above and
        # this insert. The unique index is the real arbiter; report the same
        # conflict the check would have, rather than a 500 on a race whose
        # outcome the caller can see by reloading.
        db.rollback()
        raise PlanningError(f"'{name}' is already in the list", conflict=True) from exc
    return entry, False


def update_catalog_entry(
    db: Session,
    entry: ExerciseCatalog,
    user_id: int,
    *,
    name: str | None = None,
    muscle_group: str | None = None,
    video_url: str | None = None,
    notes: str | None = None,
    replace: bool = False,
) -> ExerciseCatalog:
    """Edit a movement. Note this changes it for everyone, by design.

    `replace=True` is the REST semantic — a PUT sends the whole object, so an
    omitted field means "clear it". `replace=False` is the assistant semantic:
    only the arguments actually supplied change, because "add a video link to my
    squat" must not also wipe the form notes nobody mentioned.
    """
    if name is not None:
        name = clean_name(name)
        clash = catalog_by_name(db, user_id, name)
        if clash is not None and clash.id != entry.id:
            raise PlanningError(f"'{name}' is already in the list", conflict=True)
        entry.name = name
    elif replace:
        raise PlanningError("name is required")

    if video_url is not None or replace:
        entry.video_url = clean_video_url(video_url)
    if muscle_group is not None or replace:
        entry.muscle_group = clean_text(
            muscle_group, MAX_MUSCLE_GROUP, field="muscle_group"
        )
    if notes is not None or replace:
        entry.notes = clean_text(notes, MAX_CATALOG_NOTES, field="notes")

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PlanningError(
            f"'{entry.name}' is already in the list", conflict=True
        ) from exc
    return entry


def archive_catalog_entry(entry: ExerciseCatalog) -> ExerciseCatalog:
    """Archive, never delete.

    Sessions reference this row — including the other person's — so removing it
    would strand their history. Archiving hides it from the picker and leaves
    every past workout intact.
    """
    entry.is_archived = True
    return entry


# ── Routines ─────────────────────────────────────────────────────────────────
#
# Unlike the catalogue, a routine belongs to ONE account. The movements in it
# are shared; how you choose to program them is yours. Two people following
# different plans out of the same library is the normal case.

#: A routine with more movements than this is a mistake, not a program.
MAX_ROUTINE_EXERCISES = 50


def owned_routines(db: Session, user_id: int):
    return db.query(WorkoutTemplate).filter(WorkoutTemplate.user_id == user_id)


def routine_by_name(db: Session, user_id: int, name: str) -> WorkoutTemplate | None:
    return (
        owned_routines(db, user_id)
        .filter(func.lower(WorkoutTemplate.name) == name.strip().lower())
        .order_by(WorkoutTemplate.id)
        .first()
    )


def write_routine_exercises(
    db: Session, routine: WorkoutTemplate, user_id: int, exercises: list[Any]
) -> None:
    """Replace a routine's movements. Order comes from the list, not the caller.

    Deletes through the ORM rather than a bulk `query.delete()`: `RoutineExercise`
    is on a `delete-orphan` relationship, and a bulk delete emits one statement
    that bypasses it.

    `catalog_id` is validated here, which the version this replaced did not do —
    it passed the client's value straight to the foreign key, so a bogus id was
    a 500 and another account's private entry was a link to a row you cannot
    read. An id that does not check out is dropped to NULL; `name` is
    denormalised, so the movement still reads.
    """
    if len(exercises) > MAX_ROUTINE_EXERCISES:
        raise PlanningError(
            f"A routine can hold {MAX_ROUTINE_EXERCISES} movements; got {len(exercises)}"
        )

    allowed = visible_catalog_ids(
        db, user_id, (_field(e, "catalog_id") for e in exercises)
    )

    for existing in db.query(RoutineExercise).filter(
        RoutineExercise.routine_id == routine.id
    ):
        db.delete(existing)
    db.flush()

    for order, raw in enumerate(exercises):
        catalog_id = _field(raw, "catalog_id")
        db.add(
            RoutineExercise(
                routine_id=routine.id,
                position=order,
                name=clean_name(_field(raw, "name"), field="exercise name"),
                catalog_id=catalog_id if catalog_id in allowed else None,
                target_sets=_bounded(raw, "target_sets", 1, 100, int),
                target_reps=_bounded(raw, "target_reps", 1, 1000, int),
                target_weight_kg=_bounded(raw, "target_weight_kg", 0, 1000, float),
                notes=clean_text(
                    _field(raw, "notes"),
                    MAX_ROUTINE_NOTES,
                    field="exercise notes",
                ),
            )
        )


def save_routine(
    db: Session,
    user_id: int,
    *,
    name: str,
    exercises: list[Any] | None = None,
    default_duration_mins: int | None = None,
    routine: WorkoutTemplate | None = None,
    replace: bool = False,
) -> WorkoutTemplate:
    """Create a routine, or update the one passed in.

    `exercises=None` means "this change is not about the movements" and leaves
    them alone; `[]` means "empty it". The two are different instructions, and
    conflating them is how an edit meant to rename a routine silently deletes
    its contents — the same failure the activity write paths hit.

    `replace=True` is the REST semantic, where a PUT carries the whole object:
    an omitted `default_duration_mins` means "clear it". Without it, clearing
    the duration box in the UI returned 200 and kept the old value, because the
    assistant's presence-not-truthiness rule had been applied to both callers.
    """
    name = clean_name(name)
    if default_duration_mins is not None and not 1 <= default_duration_mins <= 600:
        raise PlanningError("default_duration_mins must be between 1 and 600")

    if routine is None:
        routine = WorkoutTemplate(
            user_id=user_id,
            name=name,
            # The table predates this feature and requires a type; a routine is
            # always strength, which is the only kind with movements to plan.
            activity_type=ActivityType.STRENGTH,
            default_duration_mins=default_duration_mins,
        )
        db.add(routine)
        db.flush()
    else:
        routine.name = name
        if default_duration_mins is not None or replace:
            routine.default_duration_mins = default_duration_mins

    if exercises is not None:
        write_routine_exercises(db, routine, user_id, exercises)
    return routine


def _field(raw: Any, key: str) -> Any:
    """Read a field from either a dict or a Pydantic model.

    The routers pass validated models; the MCP tools pass dicts, because the
    tool schema is generated from builtin annotations only.
    """
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)


def _bounded(raw: Any, key: str, low: float, high: float, cast) -> Any:
    value = _field(raw, key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise PlanningError(f"{key} must be a number")
    try:
        value = cast(value)
    except (TypeError, ValueError) as exc:
        raise PlanningError(f"{key} must be a number, got {value!r}") from exc
    if not low <= value <= high:
        raise PlanningError(f"{key} must be between {low:g} and {high:g}")
    return value


# ── Settings, targets and the weekly plan ────────────────────────────────────

#: Bounds the API never had. `UserSettingsUpdate` declares these as bare
#: `int | None` with no `Field(...)`, so a calorie target of -5000 was legal
#: through the REST endpoint. Validating here fixes both callers at once.
#: Lower bounds are 1, not a sensible-training-minimum. The job here is to
#: reject values that are obviously not a target -- negative, or a billion --
#: not to have an opinion about how much anyone should eat or walk. Setting
#: them higher made the settings page 422 on a 400-calorie or 50-step target
#: that it had always accepted, and the user saw only a generic toast.
TARGET_BOUNDS: dict[str, tuple[float, float, type]] = {
    "calorie_target": (1, 20000, int),
    "protein_target": (1, 1000, int),
    "step_target": (1, 300000, int),
    "weekly_run_km": (0, 1000, float),
    "weekly_bike_km": (0, 2000, float),
}

#: Every field `apply_targets` will touch. A field absent from `supplied` is
#: left alone; present-and-None clears it.
TARGET_FIELDS = (*TARGET_BOUNDS, "weekly_disciplines")


def get_or_create_settings(db: Session, user_id: int) -> UserSettings:
    """Get existing settings or create with defaults.

    Lives here rather than in the settings router so both the app and the MCP
    connector can reach it; `export.py` already imported it cross-module.
    """
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings is not None:
        return settings

    settings = UserSettings(user_id=user_id)
    db.add(settings)
    try:
        db.flush()
    except IntegrityError:
        # Two requests raced to create the single row this account is allowed
        # (user_id is unique). The other one won; use it.
        db.rollback()
        settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).one()
    return settings


def clean_disciplines(values: list[str] | None) -> str | None:
    """Validate the weekly plan's discipline keys on the way IN.

    `parse_plan` filters unknown keys on every read, so a typo written through
    the API today is invisible: it is stored, silently dropped when rendered,
    and the weekly review simply never mentions it. Refusing at the boundary
    means the caller learns immediately, which matters most for a model that
    would otherwise report success.
    """
    if values is None:
        return None
    keys = [str(v).strip().lower() for v in values if str(v).strip()]
    unknown = [k for k in keys if k not in DISCIPLINE_KEYS]
    if unknown:
        raise PlanningError(
            f"Unknown discipline(s): {', '.join(unknown)}. "
            f"Valid keys are: {', '.join(DISCIPLINE_KEYS)}"
        )
    # De-duplicate, keeping the canonical order rather than the caller's.
    ordered = [k for k in DISCIPLINE_KEYS if k in set(keys)]
    return ",".join(ordered) or None


def apply_targets(settings: UserSettings, supplied: dict[str, Any]) -> list[str]:
    """Write the target fields present in `supplied`. Returns what changed.

    **Presence is the instruction, not truthiness.** A key that is absent means
    "this request says nothing about that target"; a key whose value is None
    means "clear it". Building a dict of all six fields and passing it here
    wipes the five the caller did not mention — which is exactly the trap the
    REST handler's `exclude_unset` exists to avoid.
    """
    changed: list[str] = []
    for field in TARGET_FIELDS:
        if field not in supplied:
            continue
        value = supplied[field]
        if value is not None and field in TARGET_BOUNDS:
            low, high, cast = TARGET_BOUNDS[field]
            if isinstance(value, bool):
                raise PlanningError(f"{field} must be a number")
            try:
                value = cast(value)
            except (TypeError, ValueError) as exc:
                raise PlanningError(
                    f"{field} must be a number, got {supplied[field]!r}"
                ) from exc
            if not low <= value <= high:
                raise PlanningError(f"{field} must be between {low:g} and {high:g}")
        if getattr(settings, field) != value:
            setattr(settings, field, value)
            changed.append(field)
    return changed
