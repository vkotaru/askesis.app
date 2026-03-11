from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date

from app.database import get_db
from app.models import User, BodyMeasurement
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# Body measurement range in cm (reasonable human ranges)
CM_MIN, CM_MAX = 10, 200


class MeasurementCreate(BaseModel):
    date: date
    neck: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    shoulders: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    chest: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    bicep_left: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    bicep_right: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    forearm_left: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    forearm_right: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    waist: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    abdomen: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    hips: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    thigh_left: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    thigh_right: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    calf_left: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    calf_right: float | None = Field(None, ge=CM_MIN, le=CM_MAX)
    notes: str | None = Field(None, max_length=2000)


class MeasurementResponse(MeasurementCreate):
    id: int
    user_id: int

    class Config:
        from_attributes = True


@router.get("/", response_model=list[MeasurementResponse])
def get_measurements(
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "measurements", db, current_user)
    query = db.query(BodyMeasurement).filter(BodyMeasurement.user_id == target_user.id)

    if start_date:
        query = query.filter(BodyMeasurement.date >= start_date)
    if end_date:
        query = query.filter(BodyMeasurement.date <= end_date)

    return query.order_by(BodyMeasurement.date.desc()).offset(offset).limit(limit).all()


@router.get("/latest", response_model=MeasurementResponse | None)
def get_latest_measurement(
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "measurements", db, current_user)
    return (
        db.query(BodyMeasurement)
        .filter(BodyMeasurement.user_id == target_user.id)
        .order_by(BodyMeasurement.date.desc())
        .first()
    )


@router.get("/{measurement_date}", response_model=MeasurementResponse)
def get_measurement_by_date(
    measurement_date: date,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "measurements", db, current_user)
    measurement = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == target_user.id,
            BodyMeasurement.date == measurement_date,
        )
        .first()
    )

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    return measurement


@router.post("/", response_model=MeasurementResponse)
def create_or_update_measurement(
    data: MeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check if measurement exists for this date
    existing = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == current_user.id,
            BodyMeasurement.date == data.date,
        )
        .first()
    )

    if existing:
        # Update existing
        for key, value in data.model_dump(exclude_unset=True).items():
            if key != "date":
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    # Create new
    measurement = BodyMeasurement(user_id=current_user.id, **data.model_dump())
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return measurement


@router.delete("/{measurement_id}")
def delete_measurement(
    measurement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    measurement = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.id == measurement_id,
            BodyMeasurement.user_id == current_user.id,
        )
        .first()
    )

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    db.delete(measurement)
    db.commit()
    return {"ok": True}
