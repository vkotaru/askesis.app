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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Activity, Exercise, ExerciseCatalog, ExerciseSet, User
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

    @field_validator("video_url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.startswith(_ALLOWED_URL_SCHEMES):
            raise ValueError("video_url must start with http:// or https://")
        return v


class CatalogResponse(CatalogCreate):
    id: int
    is_shared: bool
    is_archived: bool
    # Who added it, or None for a row that belongs to the household. Surfaced so
    # the UI can say "added by someone else" before an edit changes it for both.
    user_id: int | None

    class Config:
        from_attributes = True


def _visible(db: Session, user: User):
    """Rows this account may see: the shared library plus anything of its own."""
    return db.query(ExerciseCatalog).filter(
        ExerciseCatalog.deleted_at.is_(None),
        or_(
            ExerciseCatalog.user_id.is_(None),
            ExerciseCatalog.user_id == user.id,
        ),
    )


@router.get("/", response_model=list[CatalogResponse])
def list_catalog(
    q: str | None = None,
    include_archived: bool = False,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _visible(db, current_user)
    if not include_archived:
        query = query.filter(ExerciseCatalog.is_archived.is_(False))
    if q:
        query = query.filter(ExerciseCatalog.name.ilike(f"%{q}%"))
    return query.order_by(ExerciseCatalog.name).limit(limit).all()


@router.post("/", response_model=CatalogResponse)
def create_catalog_entry(
    data: CatalogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a movement to the shared library.

    `user_id` is left NULL deliberately: the entry is the household's, so the
    other account sees it immediately and the partial unique index can stop the
    two of you creating "Squat" twice. Attributing it to the creator would defeat
    both, because a per-user unique constraint cannot see across accounts.
    """
    name = data.name.strip()
    existing = (
        _visible(db, current_user)
        .filter(ExerciseCatalog.name.ilike(name))
        .one_or_none()
    )
    if existing is not None:
        # Re-adding something archived is the common case — a movement comes back
        # into a program. Revive it rather than refusing, which would leave the
        # user unable to proceed with no obvious remedy.
        if existing.is_archived:
            existing.is_archived = False
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=409, detail=f"'{name}' is already in the list")

    entry = ExerciseCatalog(
        user_id=None,
        is_shared=True,
        **{**data.model_dump(), "name": name},
    )
    db.add(entry)
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
    entry = _visible(db, current_user).filter(ExerciseCatalog.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    for key, value in data.model_dump().items():
        setattr(entry, key, value)
    entry.name = entry.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def archive_catalog_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive, never delete.

    Sessions reference this row — including the other person's — so removing it
    would strand their history. Archiving hides it from the picker and leaves
    every past workout intact.
    """
    entry = _visible(db, current_user).filter(ExerciseCatalog.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    entry.is_archived = True
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
