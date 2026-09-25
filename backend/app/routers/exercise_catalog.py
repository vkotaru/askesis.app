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
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
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

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        # min_length counts characters, so "   " passes it and then lands as an
        # unselectable blank row in a library both accounts see.
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

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


def _by_name(db: Session, user: User, name: str):
    """The visible entry with this name, matched the way the index dedupes.

    ``func.lower(name) ==`` rather than ``ilike``: ilike treats % and _ in the
    argument as wildcards, so an exercise called "100%% effort" would match rows
    it is not. Ordering puts a shared row ahead of a personal one, and this
    takes the first rather than ``one_or_none`` -- pre-index duplicates can
    exist in an install that upgraded, and a 500 is a worse answer than a
    slightly arbitrary one.
    """
    return (
        _visible(db, user)
        .filter(func.lower(ExerciseCatalog.name) == name.lower())
        .order_by(ExerciseCatalog.user_id.is_(None).desc(), ExerciseCatalog.id)
        .first()
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
        # Escape the wildcards, or searching for "_" returns the whole library.
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(ExerciseCatalog.name.ilike(f"%{pattern}%", escape="\\"))
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
    name = data.name
    existing = _by_name(db, current_user, name)
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
    try:
        db.commit()
    except IntegrityError:
        # The other account added the same movement between the check above and
        # this insert. The unique index is the real arbiter; report the same 409
        # the check would have, rather than a 500 on a race the user can see the
        # outcome of by reloading.
        db.rollback()
        raise HTTPException(status_code=409, detail=f"'{name}' is already in the list")
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
    clash = _by_name(db, current_user, data.name)
    if clash is not None and clash.id != entry.id:
        raise HTTPException(
            status_code=409, detail=f"'{data.name}' is already in the list"
        )
    for key, value in data.model_dump().items():
        setattr(entry, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"'{data.name}' is already in the list"
        )
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
