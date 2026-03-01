from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date

from app.database import get_db
from app.models import User, DailyLog
from app.routers.auth import get_current_user

router = APIRouter()


class DailyLogCreate(BaseModel):
    date: date
    weight: float | None = None
    sleep_hours: float | None = None
    steps: int | None = None
    water_ml: int | None = None
    feelings: list[str] | None = None  # Multiple feelings like happy, tired, etc.
    caffeine_mg: int | None = None
    ate_outside: bool | None = None
    notes: str | None = None


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
        )


@router.get("/", response_model=list[DailyLogResponse])
def get_logs(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(DailyLog).filter(DailyLog.user_id == current_user.id)

    if start_date:
        query = query.filter(DailyLog.date >= start_date)
    if end_date:
        query = query.filter(DailyLog.date <= end_date)

    logs = query.order_by(DailyLog.date.desc()).all()
    return [DailyLogResponse.from_orm_with_feelings(log) for log in logs]


@router.get("/{log_date}", response_model=DailyLogResponse)
def get_log_by_date(
    log_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = db.query(DailyLog).filter(
        DailyLog.user_id == current_user.id,
        DailyLog.date == log_date
    ).first()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return DailyLogResponse.from_orm_with_feelings(log)


@router.post("/", response_model=DailyLogResponse)
def create_or_update_log(
    log_data: DailyLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Convert feelings list to comma-separated string
    data = log_data.model_dump()
    if data.get("feelings"):
        data["feelings"] = ",".join(data["feelings"])

    # Check if log exists for this date
    existing = db.query(DailyLog).filter(
        DailyLog.user_id == current_user.id,
        DailyLog.date == log_data.date
    ).first()

    if existing:
        # Update existing
        for key, value in data.items():
            if key != "date":  # Don't update date
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return DailyLogResponse.from_orm_with_feelings(existing)

    # Create new
    log = DailyLog(user_id=current_user.id, **data)
    db.add(log)
    db.commit()
    db.refresh(log)
    return DailyLogResponse.from_orm_with_feelings(log)
