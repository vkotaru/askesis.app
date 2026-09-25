from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime

from app.database import get_db
from app.models import (
    User,
    Activity,
    Exercise,
    ExerciseSet,
    ActivityType,
    TimeOfDay,
)
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


#: Only `working` counts toward volume; a warm-up should not inflate a total.
SET_TYPES = ("warmup", "working", "failure")


class ExerciseSetCreate(BaseModel):
    set_number: int = Field(1, ge=1, le=100)
    # Both nullable: a bodyweight movement has no weight, a timed hold no reps.
    weight_kg: float | None = Field(None, ge=0, le=1000)
    reps: int | None = Field(None, ge=0, le=1000)
    set_type: str = Field("working")
    rpe: float | None = Field(None, ge=0, le=10)
    notes: str | None = Field(None, max_length=255)

    @field_validator("set_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in SET_TYPES:
            raise ValueError(f"set_type must be one of {SET_TYPES}")
        return v


class ExerciseSetResponse(ExerciseSetCreate):
    id: int

    class Config:
        from_attributes = True


class ExerciseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    catalog_id: int | None = None
    position: int = Field(0, ge=0, le=100)
    notes: str | None = Field(None, max_length=500)
    sets_detail: list[ExerciseSetCreate] = Field(default_factory=list, max_length=50)

    # Legacy shape. Still accepted so an older client, an old queued offline
    # mutation, or a CSV import keeps working; nothing new should send them.
    sets: int | None = Field(None, ge=1, le=100)
    reps: str | None = Field(None, max_length=50)
    weight_kg: float | None = Field(None, ge=0, le=1000)


class ExerciseResponse(ExerciseCreate):
    id: int
    sets_detail: list[ExerciseSetResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ActivityCreate(BaseModel):
    date: date
    name: str = Field(..., min_length=1, max_length=100)
    activity_type: ActivityType
    time_of_day: TimeOfDay | None = None
    duration_mins: int | None = Field(None, ge=1, le=1440)  # Max 24 hours
    calories: int | None = Field(None, ge=0, le=10000)
    distance_km: float | None = Field(None, ge=0, le=500)
    url: str | None = Field(
        None, max_length=500
    )  # External link (Strava, Hevy, Garmin)
    notes: str | None = Field(None, max_length=2000)
    tags: str | None = Field(None, max_length=255)
    icon: str | None = Field(
        None, max_length=50
    )  # Icon name (e.g., 'dumbbell', 'bike')
    exercises: list[ExerciseCreate] = Field(default_factory=list, max_length=50)


class ActivityResponse(BaseModel):
    id: int
    user_id: int
    date: date
    name: str
    activity_type: ActivityType
    time_of_day: TimeOfDay | None
    duration_mins: int | None
    calories: int | None
    distance_km: float | None
    url: str | None
    notes: str | None
    tags: str | None
    icon: str | None
    # Importer provenance, read-only. `source` is None for anything typed in;
    # note this is a different claim from `url` containing "garmin.com", which
    # only means the user pasted a link.
    source: str | None = None
    external_id: str | None = None
    exercises: list[ExerciseResponse]

    class Config:
        from_attributes = True


def _write_exercises(db: Session, activity_id: int, exercises) -> None:
    """Insert exercises and their sets for one activity.

    Shared by create and update on purpose: these two paths have historically
    drifted apart in this codebase (the offline sync path still guards its
    replace with `if exercises_data:` while the REST path does not), and one
    writer is the cheapest way to stop that happening again here.
    """
    for order, ex in enumerate(exercises):
        payload = ex.model_dump(exclude={"sets_detail"})
        # Trust the list order over a client-supplied position: the UI reorders
        # by moving array elements, and a stale index would scramble the session.
        payload["position"] = order
        exercise = Exercise(activity_id=activity_id, **payload)
        db.add(exercise)
        db.flush()
        for number, st in enumerate(ex.sets_detail, start=1):
            data = st.model_dump()
            data["set_number"] = number
            db.add(ExerciseSet(exercise_id=exercise.id, **data))


@router.get("/", response_model=list[ActivityResponse])
def get_activities(
    start_date: date | None = None,
    end_date: date | None = None,
    activity_type: ActivityType | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "activities", db, current_user)
    query = (
        db.query(Activity)
        .filter(Activity.user_id == target_user.id)
        .filter(Activity.deleted_at.is_(None))
    )

    if start_date:
        query = query.filter(Activity.date >= start_date)
    if end_date:
        query = query.filter(Activity.date <= end_date)
    if activity_type:
        query = query.filter(Activity.activity_type == activity_type)

    return query.order_by(Activity.date.desc()).offset(offset).limit(limit).all()


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(
    activity_id: int,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "activities", db, current_user)
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == target_user.id)
        .filter(Activity.deleted_at.is_(None))
        .first()
    )

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    return activity


@router.post("/", response_model=ActivityResponse)
def create_activity(
    activity_data: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exercises = activity_data.exercises
    activity_dict = activity_data.model_dump(exclude={"exercises"})

    activity = Activity(user_id=current_user.id, **activity_dict)
    db.add(activity)
    db.flush()

    _write_exercises(db, activity.id, exercises)

    db.commit()
    db.refresh(activity)
    return activity


@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    activity_data: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == current_user.id)
        .filter(Activity.deleted_at.is_(None))
        .first()
    )

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Update activity fields
    for key, value in activity_data.model_dump(exclude={"exercises"}).items():
        setattr(activity, key, value)

    # Replace exercises. The ORM cascade removes the child sets with them, which
    # a bulk `.delete()` would not -- that emits one DELETE and bypasses the
    # relationship entirely, orphaning every set row.
    for existing in (
        db.query(Exercise).filter(Exercise.activity_id == activity_id).all()
    ):
        db.delete(existing)
    db.flush()
    _write_exercises(db, activity.id, activity_data.exercises)

    db.commit()
    db.refresh(activity)
    return activity


@router.delete("/{activity_id}")
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == current_user.id)
        .filter(Activity.deleted_at.is_(None))
        .first()
    )

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# Calendar view
@router.get("/calendar/{year}/{month}")
def get_calendar(
    year: int,
    month: int,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from calendar import monthrange

    target_user = check_view_permission(user_id, "activities", db, current_user)
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == target_user.id,
            Activity.date >= start,
            Activity.date <= end,
        )
        .filter(Activity.deleted_at.is_(None))
        .all()
    )

    # Group by date
    calendar = {}
    for a in activities:
        date_str = a.date.isoformat()
        if date_str not in calendar:
            calendar[date_str] = []
        calendar[date_str].append(
            {
                "id": a.id,
                "name": a.name,
                "type": a.activity_type.value,
                "duration_mins": a.duration_mins,
                "icon": a.icon,
            }
        )

    return calendar
