"""The shared movement library, and the "what did I lift last time" lookup.

Two things live here that pull in opposite directions, and keeping them straight
is the whole point of the module:

* **The catalogue is shared.** This is a household install; an exercise one
  person adds has to be usable by the other. New entries are written with
  `user_id = NULL`, which is `food_items`' convention for "belongs to the
  install, not to a person", and a partial unique index keeps the shared half
  free of duplicate names.
* **History is not.** `/{id}/last` answers *your* last session for a movement and
  must never reach across accounts, even though the movement itself is communal.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Activity, Exercise, ExerciseCatalog, ExerciseSet, User
from app import planning
from app.planning import visible_catalog_ids  # noqa: F401 (re-export)
from app.routers.auth import get_current_user

router = APIRouter()

#: A video link is rendered as an anchor the user clicks. `Activity.url` accepts
#: any string today and nothing in the stack blocks `javascript:`; this column is
#: new, so it starts out stricter rather than inheriting that.
_ALLOWED_URL_SCHEMES = ("http://", "https://")


class CatalogCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    muscle_group: str | None = Field(None, max_length=50)
    video_url: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=2000)

    # No validators here any more: `name` stripping/blank-rejection and the
    # video_url scheme check live in app/planning.py, so the MCP connector —
    # which cannot import this module — applies exactly the same rules.
    # Field(...) above still gives FastAPI a 422 for the obvious shape errors.


class CatalogResponse(CatalogCreate):
    id: int
    is_shared: bool
    is_archived: bool
    # Who added it, or None for a row that belongs to the household. Surfaced so
    # the UI can say "added by someone else" before an edit changes it for both.
    user_id: int | None

    class Config:
        from_attributes = True


def _entry_or_404(db: Session, user: User, entry_id: int) -> ExerciseCatalog:
    entry = (
        planning.visible_catalog(db, user.id)
        .filter(ExerciseCatalog.id == entry_id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return entry


def _http(exc: planning.PlanningError) -> HTTPException:
    """PlanningError -> the status a client can act on.

    409 for "already exists" so the frontend can offer to use the existing
    entry; 400 otherwise. The message is passed through unchanged — it is
    written to be read.
    """
    return HTTPException(status_code=409 if exc.conflict else 400, detail=str(exc))


@router.get("/", response_model=list[CatalogResponse])
def list_catalog(
    q: str | None = None,
    include_archived: bool = False,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return planning.search_catalog(
        db, current_user.id, q, include_archived=include_archived, limit=limit
    )


@router.post("/", response_model=CatalogResponse)
def create_catalog_entry(
    data: CatalogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a movement to the shared library.

    The rules live in `app/planning.py` so the MCP connector applies exactly the
    same ones — it cannot import this module, and a second copy of "is this a
    duplicate, is this URL safe" would drift.
    """
    try:
        entry, _revived = planning.create_catalog_entry(
            db,
            current_user.id,
            name=data.name,
            muscle_group=data.muscle_group,
            video_url=data.video_url,
            notes=data.notes,
        )
    except planning.PlanningError as exc:
        raise _http(exc) from None
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=CatalogResponse)
def update_catalog_entry(
    entry_id: int,
    data: CatalogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a movement. Note this changes it for everyone, by design."""
    entry = _entry_or_404(db, current_user, entry_id)
    try:
        # replace=True: a PUT carries the whole object, so an omitted field
        # means "clear it". The assistant path uses replace=False instead.
        planning.update_catalog_entry(
            db,
            entry,
            current_user.id,
            name=data.name,
            muscle_group=data.muscle_group,
            video_url=data.video_url,
            notes=data.notes,
            replace=True,
        )
    except planning.PlanningError as exc:
        raise _http(exc) from None
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def archive_catalog_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive, never delete — sessions reference this row, including theirs."""
    entry = _entry_or_404(db, current_user, entry_id)
    planning.archive_catalog_entry(entry)
    db.commit()
    return {"status": "archived", "id": entry_id}


class LastSetResponse(BaseModel):
    set_number: int
    weight_kg: float | None
    reps: int | None
    set_type: str
    rpe: float | None


class LastSessionResponse(BaseModel):
    date: str | None
    activity_id: int | None
    sets: list[LastSetResponse]


@router.get("/{entry_id}/last", response_model=LastSessionResponse)
def last_session(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The most recent time **this account** did this movement.

    The catalogue is communal; the training log is not. This joins through
    `Activity` to filter on the owner, so it can never surface the other
    person's numbers as your own previous session.
    """
    row = (
        db.query(Exercise)
        .join(Activity, Activity.id == Exercise.activity_id)
        .options(selectinload(Exercise.sets_detail))
        .filter(
            Exercise.catalog_id == entry_id,
            Activity.user_id == current_user.id,
            Activity.deleted_at.is_(None),
        )
        .order_by(Activity.date.desc(), Exercise.id.desc())
        .first()
    )
    if row is None:
        return LastSessionResponse(date=None, activity_id=None, sets=[])

    activity_date = (
        db.query(Activity.date).filter(Activity.id == row.activity_id).scalar()
    )
    return LastSessionResponse(
        date=activity_date.isoformat() if activity_date else None,
        activity_id=row.activity_id,
        sets=[
            LastSetResponse(
                set_number=s.set_number,
                weight_kg=s.weight_kg,
                reps=s.reps,
                set_type=s.set_type,
                rpe=s.rpe,
            )
            for s in sorted(row.sets_detail, key=lambda s: s.set_number)
        ],
    )


__all__ = ["router", "ExerciseSet"]
