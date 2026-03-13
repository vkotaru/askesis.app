from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date

from app.database import get_db
from app.models import User, Activity, Exercise, ActivityType, TimeOfDay
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class ExerciseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sets: int | None = Field(None, ge=1, le=100)
    reps: str | None = Field(None, max_length=50)
    weight_kg: float | None = Field(None, ge=0, le=1000)
    notes: str | None = Field(None, max_length=500)


class ExerciseResponse(ExerciseCreate):
    id: int

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
    icon: str | None = Field(None, max_length=50)  # Icon name (e.g., 'dumbbell', 'bike')
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
    exercises: list[ExerciseResponse]

    class Config:
        from_attributes = True


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
    query = db.query(Activity).filter(Activity.user_id == target_user.id)

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

    for ex in exercises:
        exercise = Exercise(activity_id=activity.id, **ex.model_dump())
        db.add(exercise)

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
        .first()
    )

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Update activity fields
    for key, value in activity_data.model_dump(exclude={"exercises"}).items():
        setattr(activity, key, value)

    # Replace exercises
    db.query(Exercise).filter(Exercise.activity_id == activity_id).delete()
    for ex in activity_data.exercises:
        exercise = Exercise(activity_id=activity.id, **ex.model_dump())
        db.add(exercise)

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
        .first()
    )

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
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
            }
        )

    return calendar
