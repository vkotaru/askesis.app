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


class ReportResponse(BaseModel):
    latest_weight: float | None = None
    weight_unit: str = "kg"
    weight_trend: list[WeightPoint] = []
    week_activities: list[ActivityEntry] = []
    week_start: str
    week_end: str
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

    return ReportResponse(
        latest_weight=latest_weight,
        weight_trend=weight_trend,
        week_activities=week_activities,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        generated_at=datetime.utcnow().isoformat(),
    )
