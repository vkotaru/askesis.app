import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User,
    Activity,
    TrainingPlan,
    PlannedWorkout,
    TrainingPlanStatus,
)
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Supported race distances
RACE_DISTANCES = {
    "5k": {"km": 5.0, "label": "5K", "min_weeks": 6, "max_weeks": 12},
    "10k": {"km": 10.0, "label": "10K", "min_weeks": 8, "max_weeks": 16},
    "half": {"km": 21.0975, "label": "Half Marathon", "min_weeks": 10, "max_weeks": 20},
    "marathon": {"km": 42.195, "label": "Marathon", "min_weeks": 12, "max_weeks": 24},
    "50k": {"km": 50.0, "label": "Ultra 50K", "min_weeks": 14, "max_weeks": 28},
    "50mi": {"km": 80.467, "label": "Ultra 50 Mile", "min_weeks": 16, "max_weeks": 30},
    "100k": {"km": 100.0, "label": "Ultra 100K", "min_weeks": 20, "max_weeks": 36},
    "100mi": {
        "km": 160.934,
        "label": "Ultra 100 Mile",
        "min_weeks": 24,
        "max_weeks": 40,
    },
}

# Race terrain types
RACE_TERRAINS = ["road", "trail", "mixed"]


def _generate_workouts(
    total_weeks: int,
    race_distance_km: float,
    race_distance: str,
    terrain: str = "road",
    include_bike: bool = True,
    bike_intensity: int = 50,
    rest_days: int = 2,
) -> list[dict]:
    """Generate a progressive training schedule.

    Args:
        terrain: "road", "trail", or "mixed"
        include_bike: whether to add bike cross-training
        bike_intensity: 0-100, how much biking (affects distance)
        rest_days: 1, 2, or 3 rest days per week
    """
    workouts = []
    is_ultra = race_distance in ("50k", "50mi", "100k", "100mi")

    # Peak long run is ~60-75% of race distance (capped), reached ~2-3 weeks before race
    peak_long_km = min(race_distance_km * 0.75, 32.0)  # cap at 20mi for marathon
    if race_distance == "5k":
        peak_long_km = min(race_distance_km * 1.5, 10.0)
    elif race_distance == "10k":
        peak_long_km = min(race_distance_km * 1.2, 16.0)
    elif race_distance == "half":
        peak_long_km = min(race_distance_km * 0.85, 24.0)

    # Starting long run ~30-40% of peak
    start_long_km = max(peak_long_km * 0.35, 3.0)

    # Build phase ends 3 weeks before race (then taper)
    taper_weeks = min(3, max(1, total_weeks // 6))
    build_weeks = total_weeks - taper_weeks - 1  # -1 for race week

    for week in range(1, total_weeks + 1):
        is_race_week = week == total_weeks
        is_taper = week > build_weeks and not is_race_week

        # Calculate long run distance for this week
        if is_race_week:
            long_km = 0  # Race day replaces long run
        elif is_taper:
            # Taper: reduce from peak
            taper_week = week - build_weeks
            taper_pct = 1.0 - (taper_week * 0.25)
            long_km = peak_long_km * max(taper_pct, 0.3)
        else:
            # Progressive build with step-back every 4th week
            progress = week / build_weeks
            cycle_pos = (week - 1) % 4
            if cycle_pos == 3 and week > 4:
                # Step-back week: ~70% of what it would be
                long_km = (
                    start_long_km + (peak_long_km - start_long_km) * progress * 0.7
                )
            else:
                long_km = start_long_km + (peak_long_km - start_long_km) * progress

        long_km = round(long_km, 1)

        # Weekday run distance: ~40-60% of long run
        easy_km = round(max(long_km * 0.5, 3.0) if not is_race_week else 3.0, 1)
        mid_km = round(max(long_km * 0.6, 4.0) if not is_race_week else 3.0, 1)

        # Pace description based on week position
        if is_taper:
            mid_pace = "easy"
        elif week > build_weeks // 2:
            mid_pace = "tempo"
        else:
            mid_pace = "easy"

        # Run type based on terrain
        def _run_type(preferred: str) -> str:
            if terrain == "road":
                return "road_run" if preferred != "trail_run" else "road_run"
            elif terrain == "trail":
                return "trail_run" if preferred != "treadmill_run" else "trail_run"
            else:  # mixed
                return preferred

        easy_type = _run_type("road_run")
        mid_type = _run_type("trail_run" if mid_pace == "easy" else "road_run")
        alt_type = _run_type("treadmill_run" if week % 3 == 0 else "road_run")
        long_type = (
            _run_type("trail_run") if terrain == "trail" else _run_type("road_run")
        )

        easy_label = easy_type.replace("_", " ").title()
        mid_label = mid_type.replace("_", " ").title()
        alt_label = alt_type.replace("_", " ").title()
        long_label = long_type.replace("_", " ").title()

        # Bike cross-training: scale with intensity
        bike_factor = bike_intensity / 100
        recovery_bike_km = round(easy_km * 1.5 * bike_factor, 1)
        endurance_bike_km = round(easy_km * 3.0 * bike_factor, 1)
        long_bike_km = (
            round(long_km * 2.0 * bike_factor, 1) if long_km > 0 else recovery_bike_km
        )

        # Ultra: back-to-back long runs on some weeks
        sunday_long = is_ultra and not is_race_week and not is_taper and week % 3 == 0
        sunday_km = round(long_km * 0.5, 1) if sunday_long else None

        # Build 7-day schedule, then assign rest days
        # Fixed slots: Sat=long run/race, Sun=rest or b2b
        # Flexible slots: Mon-Fri — fill with runs, bike, cross-train, rest

        # Saturday (day 5): always long run or race
        saturday = {
            "day": 5,
            "type": "race" if is_race_week else long_type if long_km > 0 else "rest",
            "description": "Race Day!"
            if is_race_week
            else f"Long {long_label}"
            if long_km > 0
            else "Rest",
            "distance_km": race_distance_km
            if is_race_week
            else (long_km if long_km > 0 else None),
            "pace": "race" if is_race_week else "easy",
        }

        # Sunday (day 6): rest or back-to-back
        sunday = {
            "day": 6,
            "type": long_type if sunday_long else "rest",
            "description": f"Back-to-Back {long_label}" if sunday_long else "Rest",
            "distance_km": sunday_km,
            "pace": "easy" if sunday_long else None,
        }

        # Mon-Fri activity pool (ordered by priority)
        # We'll pick (5 - rest_days_weekday) activities from this pool
        sunday_is_rest = not sunday_long
        rest_days_weekday = rest_days - (1 if sunday_is_rest else 0)
        rest_days_weekday = max(0, min(rest_days_weekday, 4))  # 0-4 rest days Mon-Fri
        active_days = 5 - rest_days_weekday

        # Activity slots in priority order
        activities = []
        # 1. Tempo/mid run (most important quality session)
        activities.append(
            {
                "type": mid_type if mid_pace == "easy" else "road_run",
                "description": "Tempo Run"
                if mid_pace == "tempo"
                else f"Easy {mid_label}",
                "distance_km": mid_km,
                "pace": mid_pace,
            }
        )
        # 2. Easy run
        activities.append(
            {
                "type": easy_type,
                "description": f"Easy {easy_label}",
                "distance_km": easy_km,
                "pace": "easy",
            }
        )
        # 3. Bike or cross-train
        if include_bike:
            activities.append(
                {
                    "type": "bike",
                    "description": "Recovery Bike",
                    "distance_km": recovery_bike_km,
                    "pace": "easy",
                }
            )
        else:
            activities.append(
                {
                    "type": "cross_train",
                    "description": "Cross Training",
                    "distance_km": None,
                    "pace": None,
                }
            )
        # 4. Second easy run or endurance bike
        if include_bike and bike_intensity >= 40:
            activities.append(
                {
                    "type": "bike",
                    "description": "Endurance Bike",
                    "distance_km": endurance_bike_km,
                    "pace": "easy",
                }
            )
        else:
            activities.append(
                {
                    "type": alt_type,
                    "description": f"Easy {alt_label}",
                    "distance_km": easy_km,
                    "pace": "easy",
                }
            )
        # 5. Long bike (high intensity) or another easy run
        if include_bike and bike_intensity >= 70 and not is_taper:
            activities.append(
                {
                    "type": "bike",
                    "description": "Long Bike",
                    "distance_km": long_bike_km,
                    "pace": "easy",
                }
            )
        else:
            activities.append(
                {
                    "type": easy_type,
                    "description": f"Easy {easy_label}",
                    "distance_km": easy_km,
                    "pace": "easy",
                }
            )

        # Pick top N activities, fill remaining with rest
        selected = activities[:active_days]
        # Assign to Mon(0)-Fri(4): activities spread out, rest fills gaps
        # Put quality run on Wed(2), easy runs on Tue(1)/Fri(4), bike/xt on Mon(0)/Thu(3)
        day_order = [2, 1, 0, 3, 4]  # Priority assignment order
        weekday_slots: dict[int, dict] = {}
        for i, day_idx in enumerate(day_order):
            if i < len(selected):
                weekday_slots[day_idx] = {**selected[i], "day": day_idx}
            else:
                weekday_slots[day_idx] = {
                    "day": day_idx,
                    "type": "rest",
                    "description": "Rest",
                    "distance_km": None,
                    "pace": None,
                }

        week_schedule = [weekday_slots[d] for d in range(5)] + [saturday, sunday]

        for w in week_schedule:
            w["week"] = week

        workouts.extend(week_schedule)

    return workouts


# --- Schemas ---


class PlanCreate(BaseModel):
    race_date: date  # Always required
    total_weeks: int | None = Field(None, ge=4, le=52)  # Optional: override # of weeks
    start_date: date | None = None  # Optional: override start date
    race_distance: str = Field(
        ..., pattern="^(5k|10k|half|marathon|50k|50mi|100k|100mi)$"
    )
    terrain: str = Field("road", pattern="^(road|trail|mixed)$")
    include_bike: bool = True
    bike_intensity: int = Field(50, ge=0, le=100)  # 0-100%
    rest_days: int = Field(2, ge=1, le=3)  # 1, 2, or 3 rest days per week


class PlanStatusUpdate(BaseModel):
    status: str


class WorkoutComplete(BaseModel):
    activity_id: int | None = None


class WorkoutUpdate(BaseModel):
    workout_type: str | None = None
    description: str | None = None
    target_distance_km: float | None = None
    target_pace_description: str | None = None


class PlannedWorkoutResponse(BaseModel):
    id: int
    plan_id: int
    week_number: int
    day_of_week: int
    date: date
    workout_type: str
    description: str
    target_distance_km: float | None
    target_pace_description: str | None
    completed: bool
    activity_id: int | None
    actual_distance_km: float | None = None

    class Config:
        from_attributes = True


class TrainingPlanResponse(BaseModel):
    id: int
    plan_name: str
    plan_display_name: str
    race_date: date
    race_distance_km: float
    start_date: date
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TrainingPlanDetail(TrainingPlanResponse):
    planned_workouts: list[PlannedWorkoutResponse]


class WeeklyProgress(BaseModel):
    week_number: int
    week_start: date
    planned_distance_km: float
    actual_distance_km: float
    workouts_planned: int
    workouts_completed: int


class RaceDistanceInfo(BaseModel):
    id: str
    label: str
    km: float
    min_weeks: int
    max_weeks: int


# --- Endpoints ---


@router.get("/distances", response_model=list[RaceDistanceInfo])
def get_distances():
    """List supported race distances."""
    return [
        RaceDistanceInfo(
            id=k,
            label=v["label"],
            km=v["km"],
            min_weeks=v["min_weeks"],
            max_weeks=v["max_weeks"],
        )
        for k, v in RACE_DISTANCES.items()
    ]


@router.post("/plans", response_model=TrainingPlanResponse)
def create_plan(
    data: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a training plan. Race date is required. Optionally specify
    total_weeks or start_date to control the training period."""
    # Validate distance
    dist_info = RACE_DISTANCES.get(data.race_distance)
    if not dist_info:
        raise HTTPException(status_code=400, detail="Unsupported race distance.")

    # Check for existing active plan
    existing = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == current_user.id,
            TrainingPlan.status == TrainingPlanStatus.ACTIVE,
            TrainingPlan.deleted_at.is_(None),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already have an active training plan. Cancel it first.",
        )

    today = date.today()
    race_date = data.race_date
    days_until_race = (race_date - today).days
    if days_until_race < 7:
        raise HTTPException(
            status_code=400, detail="Race date must be at least 1 week away."
        )

    if data.total_weeks:
        # User specified # of weeks → compute start_date backward from race
        total_weeks = max(
            dist_info["min_weeks"], min(data.total_weeks, dist_info["max_weeks"])
        )
    elif data.start_date:
        # User specified start date → compute weeks between start and race
        days_in_plan = (race_date - data.start_date).days
        if days_in_plan < 7:
            raise HTTPException(
                status_code=400,
                detail="Start date must be at least 1 week before race.",
            )
        weeks_available = days_in_plan // 7
        total_weeks = max(
            dist_info["min_weeks"], min(weeks_available, dist_info["max_weeks"])
        )
    else:
        # Default: auto-calculate from today to race date
        weeks_available = days_until_race // 7
        total_weeks = max(
            dist_info["min_weeks"], min(weeks_available, dist_info["max_weeks"])
        )
    # Compute start_date: work backward from race_date, align to Monday
    if data.start_date:
        start_date = data.start_date - timedelta(days=data.start_date.weekday())
    else:
        start_date = race_date - timedelta(days=total_weeks * 7 - 1)
        start_date = start_date - timedelta(days=start_date.weekday())

    terrain_label = data.terrain.title() if data.terrain != "road" else ""
    plan_label = f"{terrain_label + ' ' if terrain_label else ''}{dist_info['label']} Training ({total_weeks} weeks)"

    plan = TrainingPlan(
        user_id=current_user.id,
        plan_name=data.race_distance,
        plan_display_name=plan_label,
        race_date=race_date,
        race_distance_km=dist_info["km"],
        start_date=start_date,
        status=TrainingPlanStatus.ACTIVE,
    )
    db.add(plan)
    db.flush()

    # Generate workouts
    generated = _generate_workouts(
        total_weeks,
        dist_info["km"],
        data.race_distance,
        terrain=data.terrain,
        include_bike=data.include_bike,
        bike_intensity=data.bike_intensity,
        rest_days=data.rest_days,
    )
    for w in generated:
        workout_date = start_date + timedelta(weeks=w["week"] - 1, days=w["day"])
        pw = PlannedWorkout(
            plan_id=plan.id,
            week_number=w["week"],
            day_of_week=w["day"],
            date=workout_date,
            workout_type=w["type"],
            description=w["description"],
            target_distance_km=w.get("distance_km"),
            target_pace_description=w.get("pace"),
            completed=False,
        )
        db.add(pw)

    db.commit()
    db.refresh(plan)
    return _plan_response(plan)


@router.get("/plans", response_model=list[TrainingPlanResponse])
def get_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's training plans."""
    plans = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == current_user.id,
            TrainingPlan.deleted_at.is_(None),
        )
        .order_by(TrainingPlan.created_at.desc())
        .all()
    )
    return [_plan_response(p) for p in plans]


@router.get("/plans/{plan_id}", response_model=TrainingPlanDetail)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a training plan with all planned workouts.
    Auto-matches unlinked workouts to activities and enriches with actual distance."""
    plan = _get_user_plan(plan_id, current_user.id, db)
    resp = _plan_response(plan)
    enriched = _auto_match_and_enrich(plan, current_user.id, db)
    return TrainingPlanDetail(
        **resp.model_dump(),
        planned_workouts=enriched,
    )


@router.delete("/plans/{plan_id}")
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a training plan."""
    plan = _get_user_plan(plan_id, current_user.id, db)
    plan.deleted_at = datetime.utcnow()
    db.commit()
    return {"message": "Plan deleted"}


@router.put("/plans/{plan_id}/status", response_model=TrainingPlanResponse)
def update_plan_status(
    plan_id: int,
    data: PlanStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update plan status (active/completed/cancelled)."""
    plan = _get_user_plan(plan_id, current_user.id, db)
    try:
        plan.status = TrainingPlanStatus(data.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status.")
    db.commit()
    db.refresh(plan)
    return _plan_response(plan)


@router.put("/workouts/{workout_id}/complete", response_model=PlannedWorkoutResponse)
def complete_workout(
    workout_id: int,
    data: WorkoutComplete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a planned workout as completed."""
    pw = _get_user_workout(workout_id, current_user.id, db)
    pw.completed = True
    if data.activity_id:
        activity = (
            db.query(Activity)
            .filter(
                Activity.id == data.activity_id,
                Activity.user_id == current_user.id,
            )
            .first()
        )
        if activity:
            pw.activity_id = activity.id
    db.commit()
    db.refresh(pw)
    return PlannedWorkoutResponse.model_validate(pw)


@router.put("/workouts/{workout_id}/uncomplete", response_model=PlannedWorkoutResponse)
def uncomplete_workout(
    workout_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unmark a planned workout."""
    pw = _get_user_workout(workout_id, current_user.id, db)
    pw.completed = False
    pw.activity_id = None
    db.commit()
    db.refresh(pw)
    return PlannedWorkoutResponse.model_validate(pw)


@router.put("/workouts/{workout_id}", response_model=PlannedWorkoutResponse)
def update_workout(
    workout_id: int,
    data: WorkoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a planned workout's details."""
    pw = _get_user_workout(workout_id, current_user.id, db)
    if data.workout_type is not None:
        pw.workout_type = data.workout_type
    if data.description is not None:
        pw.description = data.description
    if data.target_distance_km is not None:
        pw.target_distance_km = (
            data.target_distance_km if data.target_distance_km > 0 else None
        )
    if data.target_pace_description is not None:
        pw.target_pace_description = data.target_pace_description or None
    db.commit()
    db.refresh(pw)
    return PlannedWorkoutResponse.model_validate(pw)


@router.get("/plans/{plan_id}/progress", response_model=list[WeeklyProgress])
def get_progress(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get weekly progress (planned vs actual distance)."""
    plan = _get_user_plan(plan_id, current_user.id, db)
    workouts = sorted(plan.planned_workouts, key=lambda w: w.date)

    weeks: dict[int, list[PlannedWorkout]] = {}
    for pw in workouts:
        weeks.setdefault(pw.week_number, []).append(pw)

    activity_ids = [pw.activity_id for pw in workouts if pw.activity_id]
    activities_by_id = {}
    if activity_ids:
        activities = db.query(Activity).filter(Activity.id.in_(activity_ids)).all()
        activities_by_id = {a.id: a for a in activities}

    result = []
    for week_num in sorted(weeks.keys()):
        week_workouts = weeks[week_num]
        week_start = min(pw.date for pw in week_workouts)
        planned_km = sum(pw.target_distance_km or 0 for pw in week_workouts)
        actual_km = 0.0
        completed = 0
        for pw in week_workouts:
            if pw.completed:
                completed += 1
            if pw.activity_id and pw.activity_id in activities_by_id:
                act = activities_by_id[pw.activity_id]
                actual_km += act.distance_km or 0

        result.append(
            WeeklyProgress(
                week_number=week_num,
                week_start=week_start,
                planned_distance_km=round(planned_km, 2),
                actual_distance_km=round(actual_km, 2),
                workouts_planned=len(week_workouts),
                workouts_completed=completed,
            )
        )

    return result


@router.get("/calendar/{year}/{month}")
def get_training_calendar(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get planned workouts for a calendar month."""
    from calendar import monthrange

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    plan = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == current_user.id,
            TrainingPlan.status == TrainingPlanStatus.ACTIVE,
            TrainingPlan.deleted_at.is_(None),
        )
        .first()
    )
    if not plan:
        return {}

    workouts = (
        db.query(PlannedWorkout)
        .filter(
            PlannedWorkout.plan_id == plan.id,
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= end,
        )
        .all()
    )

    result: dict[str, list[dict]] = {}
    for pw in workouts:
        date_str = pw.date.isoformat()
        if date_str not in result:
            result[date_str] = []
        result[date_str].append(
            {
                "id": pw.id,
                "workout_type": pw.workout_type,
                "description": pw.description,
                "target_distance_km": pw.target_distance_km,
                "completed": pw.completed,
                "activity_id": pw.activity_id,
            }
        )

    return result


# --- Helpers ---

# Workout type to activity type mapping for auto-matching
_RUN_TYPES = {"road_run", "trail_run", "treadmill_run", "long_run", "run", "race"}
_BIKE_TYPES = {"bike"}


def _auto_match_and_enrich(
    plan: TrainingPlan, user_id: int, db: Session
) -> list[PlannedWorkoutResponse]:
    """Auto-match unlinked workouts to activities by date+type,
    and enrich responses with actual distance from linked activities."""
    workouts = sorted(plan.planned_workouts, key=lambda w: w.date)
    if not workouts:
        return []

    # Get all user activities in the plan's date range
    min_date = workouts[0].date
    max_date = workouts[-1].date
    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= min_date,
            Activity.date <= max_date,
            Activity.deleted_at.is_(None),
        )
        .all()
    )

    # Index activities by date
    from collections import defaultdict

    activities_by_date: dict[date, list[Activity]] = defaultdict(list)
    for a in activities:
        activities_by_date[a.date].append(a)

    # Also index by id for already-linked ones
    activities_by_id = {a.id: a for a in activities}

    # Track which activities are already claimed
    claimed_ids: set[int] = {pw.activity_id for pw in workouts if pw.activity_id}

    changed = False
    results = []
    for pw in workouts:
        actual_km: float | None = None

        # If already linked, get actual distance
        if pw.activity_id and pw.activity_id in activities_by_id:
            act = activities_by_id[pw.activity_id]
            actual_km = act.distance_km

        # Auto-match: if not completed and not linked, try to find a matching activity
        elif not pw.completed and pw.workout_type not in ("rest", "cross_train"):
            candidates = activities_by_date.get(pw.date, [])
            for act in candidates:
                if act.id in claimed_ids:
                    continue
                name_lower = (act.name or "").lower()
                is_bike_activity = any(
                    kw in name_lower for kw in ("bike", "cycling", "ride", "cycle")
                )
                is_run_activity = (
                    not is_bike_activity and act.activity_type.value == "cardio"
                )

                # Match bike planned → bike activity only
                if pw.workout_type in _BIKE_TYPES and is_bike_activity:
                    pw.activity_id = act.id
                    pw.completed = True
                    actual_km = act.distance_km
                    claimed_ids.add(act.id)
                    changed = True
                    break
                # Match run planned → run/cardio activity (not bike)
                if pw.workout_type in _RUN_TYPES and is_run_activity:
                    pw.activity_id = act.id
                    pw.completed = True
                    actual_km = act.distance_km
                    claimed_ids.add(act.id)
                    changed = True
                    break

        resp = PlannedWorkoutResponse.model_validate(pw)
        resp.actual_distance_km = actual_km
        results.append(resp)

    if changed:
        db.commit()

    return results


def _get_user_plan(plan_id: int, user_id: int, db: Session) -> TrainingPlan:
    plan = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
            TrainingPlan.deleted_at.is_(None),
        )
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Training plan not found.")
    return plan


def _get_user_workout(workout_id: int, user_id: int, db: Session) -> PlannedWorkout:
    pw = (
        db.query(PlannedWorkout)
        .join(TrainingPlan)
        .filter(
            PlannedWorkout.id == workout_id,
            TrainingPlan.user_id == user_id,
            TrainingPlan.deleted_at.is_(None),
        )
        .first()
    )
    if not pw:
        raise HTTPException(status_code=404, detail="Planned workout not found.")
    return pw


def _plan_response(plan: TrainingPlan) -> TrainingPlanResponse:
    return TrainingPlanResponse(
        id=plan.id,
        plan_name=plan.plan_name,
        plan_display_name=plan.plan_display_name,
        race_date=plan.race_date,
        race_distance_km=plan.race_distance_km,
        start_date=plan.start_date,
        status=plan.status.value,
        created_at=plan.created_at,
    )
