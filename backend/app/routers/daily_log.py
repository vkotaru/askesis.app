from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date

from app.database import get_db
from app.models import User, DailyLog
from app.provenance import (
    EDITED_FIELDS_KEY,
    MANUAL,
    claimed_fields,
    mark_manual,
    parse_sources,
)
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

# Pagination defaults
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class DailyLogCreate(BaseModel):
    date: date
    weight: float | None = Field(None, ge=20, le=500, description="Weight in kg")
    sleep_hours: float | None = Field(None, ge=0, le=24)
    steps: int | None = Field(None, ge=0, le=100000)
    water_ml: int | None = Field(None, ge=0, le=10000)
    feelings: list[str] | None = None
    caffeine_mg: int | None = Field(None, ge=0, le=2000)
    ate_outside: bool | None = None
    notes: str | None = Field(None, max_length=2000)
    # Which fields the user actually edited. Provenance only — never written to
    # a column. Aliased because a leading underscore is private to pydantic.
    edited: list[str] | None = Field(None, alias="_edited")

    class Config:
        populate_by_name = True


class DailyLogResponse(BaseModel):
    id: int
    user_id: int
    date: date
    weight: float | None = None
    sleep_hours: float | None = None
    steps: int | None = None
    water_ml: int | None = None
    feelings: list[str] | None = None
    caffeine_mg: int | None = None
    ate_outside: bool | None = None
    notes: str | None = None
    # Server-owned: which fields came from an importer rather than the user.
    # Absent from DailyLogCreate on purpose -- a client can never assert it.
    sources: dict[str, str] | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_feelings(cls, log: "DailyLog"):
        feelings_list = log.feelings.split(",") if log.feelings else None
        return cls(
            id=log.id,
            user_id=log.user_id,
            date=log.date,
            weight=log.weight,
            sleep_hours=log.sleep_hours,
            steps=log.steps,
            water_ml=log.water_ml,
            feelings=feelings_list,
            caffeine_mg=log.caffeine_mg,
            ate_outside=log.ate_outside,
            notes=log.notes,
            sources=parse_sources(log.sources) or None,
        )


@router.get("/", response_model=list[DailyLogResponse])
def get_logs(
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "daily_logs", db, current_user)
    query = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == target_user.id)
        .filter(DailyLog.deleted_at.is_(None))
    )

    if start_date:
        query = query.filter(DailyLog.date >= start_date)
    if end_date:
        query = query.filter(DailyLog.date <= end_date)

    logs = query.order_by(DailyLog.date.desc()).offset(offset).limit(limit).all()
    return [DailyLogResponse.from_orm_with_feelings(log) for log in logs]


@router.get("/{log_date}", response_model=DailyLogResponse)
def get_log_by_date(
    log_date: date,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "daily_logs", db, current_user)
    log = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == target_user.id, DailyLog.date == log_date)
        .filter(DailyLog.deleted_at.is_(None))
        .first()
    )

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return DailyLogResponse.from_orm_with_feelings(log)


@router.post("/", response_model=DailyLogResponse)
def create_or_update_log(
    log_data: DailyLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only get fields that were actually provided (not default None values)
    data = log_data.model_dump(exclude_unset=True)
    # Out of `data` before anything iterates it: this names fields, it is not one.
    claim = {EDITED_FIELDS_KEY: data.pop("edited", None)}
    # `is not None`, not truthiness: an empty list means "you deselected your
    # last feeling", and the truthy test let that list through unjoined to
    # sqlite, which refuses to bind it. The sync path already got this right.
    if data.get("feelings") is not None:
        data["feelings"] = ",".join(data["feelings"])

    # Check if log exists for this date
    existing = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == current_user.id, DailyLog.date == log_data.date)
        .filter(DailyLog.deleted_at.is_(None))
        .first()
    )

    if existing:
        # Update only provided fields (preserve existing data)
        touched = [k for k in data if k != "date"]
        # A person set these, including any they set to empty. That claim is
        # what stops an importer refilling a field the user deliberately
        # cleared -- see app/provenance.py.
        #
        # Only the ones whose value moved, though. `exclude_unset` already drops
        # fields the request omitted, but the form posts what it loaded, so a
        # submit that changed only the weight still carries the day's steps. The
        # value is the evidence: unchanged means the client echoed it back, not
        # that someone typed it. Claiming it anyway locks the importer out of its
        # own reading for good.
        sources = parse_sources(existing.sources)
        edited = claimed_fields(claim, touched, lambda f: sources.get(f))
        for key in touched:
            # A field an importer owns and the user did not claim is not ours to
            # overwrite either: the value in the payload is whatever the client
            # happened to be holding, which may predate the importer's latest
            # reading. Writing it would undo a correction and then, on the next
            # sync, look like the importer had drifted.
            if key not in edited and sources.get(key) not in (None, MANUAL):
                continue
            setattr(existing, key, data[key])
        if edited:
            existing.sources = mark_manual(existing.sources, edited)
        db.commit()
        db.refresh(existing)
        return DailyLogResponse.from_orm_with_feelings(existing)

    # Create new - use full data with defaults for creation
    create_data = log_data.model_dump()
    create_data.pop("edited", None)  # names fields, is not one
    if create_data.get("feelings") is not None:
        create_data["feelings"] = ",".join(create_data["feelings"])
    log = DailyLog(
        user_id=current_user.id,
        sources=mark_manual(None, [k for k in data if k != "date"]),
        **create_data,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return DailyLogResponse.from_orm_with_feelings(log)
