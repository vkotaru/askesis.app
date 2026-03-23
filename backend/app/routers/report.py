"""
Public report endpoint — shareable health summary via unguessable token.

GET  /api/report/{token}    — public, no auth, returns aggregated data
POST /api/report/token      — authenticated, generate or return existing token
DELETE /api/report/token    — authenticated, revoke token (old links stop working)
"""

import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    User,
    ReportToken,
    DailyLog,
    Activity,
    ActivityType,
    BodyMeasurement,
    Meal,
    DailyNutrition,
)
from app.routers.auth import get_current_user

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    token: str
    url: str


class WeightPoint(BaseModel):
    date: str
    weight: float


class ActivityEntry(BaseModel):
    date: str
    name: str
    activity_type: str
    duration_mins: int | None = None
    calories: int | None = None
    icon: str | None = None


class MeasurementSnapshot(BaseModel):
    date: str
    neck: float | None = None
    shoulders: float | None = None
    chest: float | None = None
    bicep_left: float | None = None
    bicep_right: float | None = None
    waist: float | None = None
    abdomen: float | None = None
    hips: float | None = None
    thigh_left: float | None = None
    thigh_right: float | None = None
    calf_left: float | None = None
    calf_right: float | None = None


class NutritionAverage(BaseModel):
    avg_calories: int | None = None
    avg_protein_g: float | None = None
    avg_carbs_g: float | None = None
    avg_fat_g: float | None = None
    days_tracked: int = 0


class ReportResponse(BaseModel):
    today: str
    latest_weight: float | None = None
    latest_weight_date: str | None = None
    weight_unit: str = "kg"
    weight_trend: list[WeightPoint] = []
    week_activities: list[ActivityEntry] = []
    week_start: str
    week_end: str
    latest_measurements: MeasurementSnapshot | None = None
    nutrition_avg: NutritionAverage | None = None
    generated_at: str


# ── Token management (authenticated) ─────────────────────────────────────────


@router.post("/token", response_model=TokenResponse)
def generate_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate or return existing report token."""
    existing = (
        db.query(ReportToken)
        .filter(ReportToken.user_id == current_user.id)
        .first()
    )

    if existing:
        return TokenResponse(token=existing.token, url=f"/report/{existing.token}")

    token = secrets.token_hex(16)
    rt = ReportToken(user_id=current_user.id, token=token)
    db.add(rt)
    db.commit()
    return TokenResponse(token=token, url=f"/report/{token}")


@router.delete("/token")
def revoke_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke report token — old links stop working."""
    existing = (
        db.query(ReportToken)
        .filter(ReportToken.user_id == current_user.id)
        .first()
    )

    if not existing:
        raise HTTPException(status_code=404, detail="No report token found")

    db.delete(existing)
    db.commit()
    return {"ok": True}


@router.post("/token/regenerate", response_model=TokenResponse)
def regenerate_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke old token and generate a new one."""
    existing = (
        db.query(ReportToken)
        .filter(ReportToken.user_id == current_user.id)
        .first()
    )

    if existing:
        db.delete(existing)
        db.flush()

    token = secrets.token_hex(16)
    rt = ReportToken(user_id=current_user.id, token=token)
    db.add(rt)
    db.commit()
    return TokenResponse(token=token, url=f"/report/{token}")


# ── Public report (no auth) ──────────────────────────────────────────────────


@router.get("/{token}", response_model=ReportResponse)
def get_report(
    token: str,
    db: Session = Depends(get_db),
):
    """Public endpoint — returns aggregated health report. No PII."""
    rt = db.query(ReportToken).filter(ReportToken.token == token).first()
    if not rt:
        raise HTTPException(status_code=404, detail="Report not found")

    user_id = rt.user_id
    today = date.today()

    # ── Weight trend (last 30 days) ───────────────────────────────────────
    thirty_days_ago = today - timedelta(days=30)
    weight_logs = (
        db.query(DailyLog)
        .filter(
            DailyLog.user_id == user_id,
            DailyLog.date >= thirty_days_ago,
            DailyLog.weight != None,
            DailyLog.deleted_at == None,
        )
        .order_by(DailyLog.date.asc())
        .all()
    )

    weight_trend = [
        WeightPoint(date=log.date.isoformat(), weight=log.weight)
        for log in weight_logs
        if log.weight is not None
    ]

    # Latest weight (most recent entry with weight, could be older than 30d)
    latest_weight_log = (
        db.query(DailyLog)
        .filter(
            DailyLog.user_id == user_id,
            DailyLog.weight != None,
            DailyLog.deleted_at == None,
        )
        .order_by(DailyLog.date.desc())
        .first()
    )
    latest_weight = latest_weight_log.weight if latest_weight_log else None

    # ── This week's activities ────────────────────────────────────────────
    # Monday to Sunday
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    week_activities_rows = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= week_start,
            Activity.date <= week_end,
            Activity.deleted_at == None,
        )
        .order_by(Activity.date.asc())
        .all()
    )

    week_activities = [
        ActivityEntry(
            date=a.date.isoformat(),
            name=a.name,
            activity_type=a.activity_type.value,
            duration_mins=a.duration_mins,
            calories=a.calories,
            icon=a.icon,
        )
        for a in week_activities_rows
    ]

    # ── Latest body measurements ─────────────────────────────────────────
    latest_measurement = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == user_id,
            BodyMeasurement.deleted_at == None,
        )
        .order_by(BodyMeasurement.date.desc())
        .first()
    )

    latest_measurements = None
    if latest_measurement:
        latest_measurements = MeasurementSnapshot(
            date=latest_measurement.date.isoformat(),
            neck=latest_measurement.neck,
            shoulders=latest_measurement.shoulders,
            chest=latest_measurement.chest,
            bicep_left=latest_measurement.bicep_left,
            bicep_right=latest_measurement.bicep_right,
            waist=latest_measurement.waist,
            abdomen=latest_measurement.abdomen,
            hips=latest_measurement.hips,
            thigh_left=latest_measurement.thigh_left,
            thigh_right=latest_measurement.thigh_right,
            calf_left=latest_measurement.calf_left,
            calf_right=latest_measurement.calf_right,
        )

    # ── Nutrition averages (last 7 days) ──────────────────────────────────
    seven_days_ago = today - timedelta(days=7)

    # Get calories from meals
    week_meals = (
        db.query(Meal)
        .filter(
            Meal.user_id == user_id,
            Meal.date >= seven_days_ago,
            Meal.deleted_at == None,
        )
        .all()
    )

    # Get macros from daily_nutrition
    week_nutrition = (
        db.query(DailyNutrition)
        .filter(
            DailyNutrition.user_id == user_id,
            DailyNutrition.date >= seven_days_ago,
        )
        .all()
    )

    nutrition_avg = None
    if week_meals or week_nutrition:
        # Sum calories per day from meals
        cals_by_date: dict[date, int] = {}
        for m in week_meals:
            if m.calories:
                cals_by_date[m.date] = cals_by_date.get(m.date, 0) + m.calories

        days_with_cals = len(cals_by_date)
        total_cals = sum(cals_by_date.values())

        # Average macros from daily_nutrition
        days_with_macros = len(week_nutrition)
        total_protein = sum(n.protein_g or 0 for n in week_nutrition)
        total_carbs = sum(n.carbs_g or 0 for n in week_nutrition)
        total_fat = sum(n.fat_g or 0 for n in week_nutrition)

        nutrition_avg = NutritionAverage(
            avg_calories=round(total_cals / days_with_cals) if days_with_cals else None,
            avg_protein_g=round(total_protein / days_with_macros, 1) if days_with_macros else None,
            avg_carbs_g=round(total_carbs / days_with_macros, 1) if days_with_macros else None,
            avg_fat_g=round(total_fat / days_with_macros, 1) if days_with_macros else None,
            days_tracked=max(days_with_cals, days_with_macros),
        )

    return ReportResponse(
        today=today.isoformat(),
        latest_weight=latest_weight,
        latest_weight_date=latest_weight_log.date.isoformat() if latest_weight_log else None,
        weight_trend=weight_trend,
        week_activities=week_activities,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        latest_measurements=latest_measurements,
        nutrition_avg=nutrition_avg,
        generated_at=datetime.utcnow().isoformat(),
    )
