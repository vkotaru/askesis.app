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


class DailySteps(BaseModel):
    date: str
    steps: int | None = None


class DailyNutritionPoint(BaseModel):
    date: str
    calories: int = 0
    protein_g: float = 0


class ReportResponse(BaseModel):
    today: str
    latest_weight: float | None = None
    latest_weight_date: str | None = None
    weight_unit: str = "kg"
    weight_trend: list[WeightPoint] = []
    week_activities: list[ActivityEntry] = []
    week_start: str
    week_end: str
    week_steps: list[DailySteps] = []
    week_nutrition: list[DailyNutritionPoint] = []
    latest_measurements: MeasurementSnapshot | None = None
    previous_measurements: MeasurementSnapshot | None = None
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

    # ── Steps this week ─────────────────────────────────────────────────
    week_logs = (
        db.query(DailyLog)
        .filter(
            DailyLog.user_id == user_id,
            DailyLog.date >= week_start,
            DailyLog.date <= week_end,
            DailyLog.deleted_at == None,
        )
        .all()
    )
    steps_by_date = {log.date.isoformat(): log.steps for log in week_logs if log.steps}

    week_steps = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        ds = d.isoformat()
        week_steps.append(DailySteps(date=ds, steps=steps_by_date.get(ds)))

    # ── Nutrition this week (daily bar chart data) ────────────────────────
    week_meals = (
        db.query(Meal)
        .filter(
            Meal.user_id == user_id,
            Meal.date >= week_start,
            Meal.date <= week_end,
            Meal.deleted_at == None,
        )
        .all()
    )
    week_daily_nutrition = (
        db.query(DailyNutrition)
        .filter(
            DailyNutrition.user_id == user_id,
            DailyNutrition.date >= week_start,
            DailyNutrition.date <= week_end,
        )
        .all()
    )

    cals_by_date: dict[str, int] = {}
    for m in week_meals:
        if m.calories:
            ds = m.date.isoformat()
            cals_by_date[ds] = cals_by_date.get(ds, 0) + m.calories

    protein_by_date: dict[str, float] = {}
    for n in week_daily_nutrition:
        if n.protein_g:
            protein_by_date[n.date.isoformat()] = n.protein_g

    week_nutrition_data = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        ds = d.isoformat()
        week_nutrition_data.append(DailyNutritionPoint(
            date=ds,
            calories=cals_by_date.get(ds, 0),
            protein_g=protein_by_date.get(ds, 0),
        ))

    # ── Body measurements (latest + previous) ────────────────────────────
    measurement_rows = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == user_id,
            BodyMeasurement.deleted_at == None,
        )
        .order_by(BodyMeasurement.date.desc())
        .limit(2)
        .all()
    )

    def _to_snapshot(m: BodyMeasurement) -> MeasurementSnapshot:
        return MeasurementSnapshot(
            date=m.date.isoformat(),
            neck=m.neck, shoulders=m.shoulders, chest=m.chest,
            bicep_left=m.bicep_left, bicep_right=m.bicep_right,
            waist=m.waist, abdomen=m.abdomen, hips=m.hips,
            thigh_left=m.thigh_left, thigh_right=m.thigh_right,
            calf_left=m.calf_left, calf_right=m.calf_right,
        )

    latest_measurements = _to_snapshot(measurement_rows[0]) if len(measurement_rows) >= 1 else None
    previous_measurements = _to_snapshot(measurement_rows[1]) if len(measurement_rows) >= 2 else None

    return ReportResponse(
        today=today.isoformat(),
        latest_weight=latest_weight,
        latest_weight_date=latest_weight_log.date.isoformat() if latest_weight_log else None,
        weight_trend=weight_trend,
        week_activities=week_activities,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        week_steps=week_steps,
        week_nutrition=week_nutrition_data,
        latest_measurements=latest_measurements,
        previous_measurements=previous_measurements,
        generated_at=datetime.utcnow().isoformat(),
    )
