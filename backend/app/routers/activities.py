from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date

from app.database import get_db
from app.models import User, Activity, Exercise, WorkoutTemplate, ActivityType
from app.routers.auth import get_current_user

router = APIRouter()


class ExerciseCreate(BaseModel):
    name: str
    sets: int | None = None
    reps: str | None = None
    weight_kg: float | None = None
    notes: str | None = None


class ExerciseResponse(ExerciseCreate):
    id: int

    class Config:
        from_attributes = True


class ActivityCreate(BaseModel):
    date: date
    name: str
    activity_type: ActivityType
    duration_mins: int | None = None
    calories: int | None = None
    distance_km: float | None = None
    notes: str | None = None
    tags: str | None = None
    exercises: list[ExerciseCreate] = []


class ActivityResponse(BaseModel):
    id: int
    user_id: int
    date: date
    name: str
    activity_type: ActivityType
    duration_mins: int | None
    calories: int | None
    distance_km: float | None
    notes: str | None
    tags: str | None
    exercises: list[ExerciseResponse]

    class Config:
        from_attributes = True


@router.get("/", response_model=list[ActivityResponse])
def get_activities(
    start_date: date | None = None,
    end_date: date | None = None,
    activity_type: ActivityType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Activity).filter(Activity.user_id == current_user.id)

    if start_date:
        query = query.filter(Activity.date >= start_date)
    if end_date:
        query = query.filter(Activity.date <= end_date)
    if activity_type:
        query = query.filter(Activity.activity_type == activity_type)

    return query.order_by(Activity.date.desc()).all()


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = db.query(Activity).filter(
        Activity.id == activity_id,
        Activity.user_id == current_user.id
    ).first()

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
    activity = db.query(Activity).filter(
        Activity.id == activity_id,
        Activity.user_id == current_user.id
    ).first()

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
    activity = db.query(Activity).filter(
        Activity.id == activity_id,
        Activity.user_id == current_user.id
    ).first()

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from calendar import monthrange

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    activities = db.query(Activity).filter(
        Activity.user_id == current_user.id,
        Activity.date >= start,
        Activity.date <= end
    ).all()

    # Group by date
    calendar = {}
    for a in activities:
        date_str = a.date.isoformat()
        if date_str not in calendar:
            calendar[date_str] = []
        calendar[date_str].append({
            "id": a.id,
            "name": a.name,
            "type": a.activity_type.value,
            "duration_mins": a.duration_mins,
        })

    return calendar
