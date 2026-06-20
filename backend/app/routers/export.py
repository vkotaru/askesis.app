"""Export user data to SQLite database file or Google Sheets."""

import logging
import sqlite3
import tempfile
from datetime import datetime, date as date_type
from pathlib import Path

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User,
    DailyLog,
    Meal,
    Activity,
    ActivityType,
    TimeOfDay,
    Exercise,
    BodyMeasurement,
    ProgressPhoto,
    UserSettings,
)
from app.routers.auth import get_current_user
from app.routers.settings import get_or_create_settings
from app.google_sheets import sync_to_sheet

logger = logging.getLogger("askesis.export")

router = APIRouter()

# Schema version - increment when table structure changes
SCHEMA_VERSION = 1


def create_sqlite_export(db: Session, user: User) -> Path:
    """Create a SQLite database with all user data."""
    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".db", prefix=f"askesis-{user.id}-", delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    # Connect to SQLite
    conn = sqlite3.connect(str(temp_path))
    cursor = conn.cursor()

    # Create metadata table
    cursor.execute("""
        CREATE TABLE _export_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.executemany(
        "INSERT INTO _export_meta (key, value) VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("exported_at", datetime.utcnow().isoformat()),
            ("user_id", str(user.id)),
            ("user_email", user.email),
            ("user_name", user.name),
        ],
    )

    # Export daily_logs
    cursor.execute("""
        CREATE TABLE daily_logs (
            id INTEGER PRIMARY KEY,
            date TEXT,
            weight REAL,
            sleep_hours REAL,
            steps INTEGER,
            water_ml INTEGER,
            feelings TEXT,
            caffeine_mg INTEGER,
            ate_outside INTEGER,
            notes TEXT,
            created_at TEXT
        )
    """)
    logs = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == user.id)
        .filter(DailyLog.deleted_at.is_(None))
        .all()
    )
    cursor.executemany(
        """INSERT INTO daily_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                log.id,
                str(log.date),
                log.weight,
                log.sleep_hours,
                log.steps,
                log.water_ml,
                log.feelings,
                log.caffeine_mg,
                1 if log.ate_outside else 0,
                log.notes,
                log.created_at.isoformat() if log.created_at else None,
            )
            for log in logs
        ],
    )

    # Export meals
    cursor.execute("""
        CREATE TABLE meals (
            id INTEGER PRIMARY KEY,
            date TEXT,
            label TEXT,
            time TEXT,
            calories INTEGER,
            description TEXT,
            photo_path TEXT,
            ai_analysis TEXT,
            created_at TEXT
        )
    """)
    meals = (
        db.query(Meal)
        .filter(Meal.user_id == user.id)
        .filter(Meal.deleted_at.is_(None))
        .all()
    )
    cursor.executemany(
        """INSERT INTO meals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                meal.id,
                str(meal.date),
                meal.label,
                meal.time,
                meal.calories,
                meal.description,
                meal.photo_path,
                meal.ai_analysis,
                meal.created_at.isoformat() if meal.created_at else None,
            )
            for meal in meals
        ],
    )

    # Export activities
    cursor.execute("""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            date TEXT,
            name TEXT,
            activity_type TEXT,
            time_of_day TEXT,
            duration_mins INTEGER,
            calories INTEGER,
            distance_km REAL,
            url TEXT,
            notes TEXT,
            tags TEXT,
            created_at TEXT
        )
    """)
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user.id)
        .filter(Activity.deleted_at.is_(None))
        .all()
    )
    cursor.executemany(
        """INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                act.id,
                str(act.date),
                act.name,
                act.activity_type.value if act.activity_type else None,
                act.time_of_day.value if act.time_of_day else None,
                act.duration_mins,
                act.calories,
                act.distance_km,
                act.url,
                act.notes,
                act.tags,
                act.created_at.isoformat() if act.created_at else None,
            )
            for act in activities
        ],
    )

    # Export exercises
    cursor.execute("""
        CREATE TABLE exercises (
            id INTEGER PRIMARY KEY,
            activity_id INTEGER,
            name TEXT,
            sets INTEGER,
            reps TEXT,
            weight_kg REAL,
            notes TEXT,
            FOREIGN KEY (activity_id) REFERENCES activities(id)
        )
    """)
    # Get exercises for user's activities
    activity_ids = [a.id for a in activities]
    if activity_ids:
        exercises = (
            db.query(Exercise).filter(Exercise.activity_id.in_(activity_ids)).all()
        )
        cursor.executemany(
            """INSERT INTO exercises VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    ex.id,
                    ex.activity_id,
                    ex.name,
                    ex.sets,
                    ex.reps,
                    ex.weight_kg,
                    ex.notes,
                )
                for ex in exercises
            ],
        )

    # Export body_measurements
    cursor.execute("""
        CREATE TABLE body_measurements (
            id INTEGER PRIMARY KEY,
            date TEXT,
            neck REAL,
            shoulders REAL,
            chest REAL,
            bicep_left REAL,
            bicep_right REAL,
            forearm_left REAL,
            forearm_right REAL,
            waist REAL,
            abdomen REAL,
            hips REAL,
            thigh_left REAL,
            thigh_right REAL,
            calf_left REAL,
            calf_right REAL,
            notes TEXT,
            created_at TEXT
        )
    """)
    measurements = (
        db.query(BodyMeasurement)
        .filter(BodyMeasurement.user_id == user.id)
        .filter(BodyMeasurement.deleted_at.is_(None))
        .all()
    )
    cursor.executemany(
        """INSERT INTO body_measurements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                m.id,
                str(m.date),
                m.neck,
                m.shoulders,
                m.chest,
                m.bicep_left,
                m.bicep_right,
                m.forearm_left,
                m.forearm_right,
                m.waist,
                m.abdomen,
                m.hips,
                m.thigh_left,
                m.thigh_right,
                m.calf_left,
                m.calf_right,
                m.notes,
                m.created_at.isoformat() if m.created_at else None,
            )
            for m in measurements
        ],
    )

    # Export progress_photos (metadata only, not the actual files)
    cursor.execute("""
        CREATE TABLE progress_photos (
            id INTEGER PRIMARY KEY,
            date TEXT,
            view TEXT,
            file_path TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    photos = (
        db.query(ProgressPhoto)
        .filter(ProgressPhoto.user_id == user.id)
        .filter(ProgressPhoto.deleted_at.is_(None))
        .all()
    )
    cursor.executemany(
        """INSERT INTO progress_photos VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                p.id,
                str(p.date),
                p.view.value if p.view else None,
                p.file_path,
                p.notes,
                p.created_at.isoformat() if p.created_at else None,
            )
            for p in photos
        ],
    )

    # Export user_settings
    cursor.execute("""
        CREATE TABLE user_settings (
            id INTEGER PRIMARY KEY,
            theme TEXT,
            font_size TEXT,
            font_family TEXT,
            content_width TEXT,
            color_scheme TEXT,
            distance_unit TEXT,
            measurement_unit TEXT,
            weight_unit TEXT,
            water_unit TEXT
        )
    """)
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if settings:
        cursor.execute(
            """INSERT INTO user_settings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                settings.id,
                settings.theme,
                settings.font_size,
                settings.font_family,
                settings.content_width,
                settings.color_scheme,
                settings.distance_unit,
                settings.measurement_unit,
                settings.weight_unit,
                settings.water_unit,
            ),
        )

    # Create indexes for common queries
    cursor.execute("CREATE INDEX idx_daily_logs_date ON daily_logs(date)")
    cursor.execute("CREATE INDEX idx_meals_date ON meals(date)")
    cursor.execute("CREATE INDEX idx_activities_date ON activities(date)")
    cursor.execute("CREATE INDEX idx_measurements_date ON body_measurements(date)")

    conn.commit()
    conn.close()

    return temp_path


def cleanup_temp_file(path: Path):
    """Background task to clean up temp file after response is sent."""
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass  # Best effort cleanup


@router.get("/sqlite")
def export_sqlite(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all user data to a SQLite database file."""
    db_path = create_sqlite_export(db, current_user)

    # Schedule cleanup after response is sent
    background_tasks.add_task(cleanup_temp_file, db_path)

    # Generate filename with date
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"askesis-{date_str}.db"

    return FileResponse(
        path=str(db_path),
        filename=filename,
        media_type="application/x-sqlite3",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdate(s: str | None):
    return date_type.fromisoformat(s) if s else None


def import_sqlite_export(db: Session, user: User, sqlite_path: Path) -> dict:
    """Import an Askesis '.db' analysis export into the current user's account.

    The export is a flattened, per-user SQLite file (see create_sqlite_export).
    Rows are inserted as NEW records owned by `user` (old IDs are not reused;
    exercise->activity links are remapped). This is ADDITIVE — intended for a
    fresh account. Foods, meal-food links, training plans, sharing and photo
    files are not part of the export and are skipped.
    """
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    present = {
        r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    summary: dict[str, int] = {}

    if "daily_logs" in present:
        n = 0
        for r in cur.execute("SELECT * FROM daily_logs"):
            db.add(
                DailyLog(
                    user_id=user.id,
                    date=_pdate(r["date"]),
                    weight=r["weight"],
                    sleep_hours=r["sleep_hours"],
                    steps=r["steps"],
                    water_ml=r["water_ml"],
                    feelings=r["feelings"],
                    caffeine_mg=r["caffeine_mg"],
                    ate_outside=bool(r["ate_outside"])
                    if r["ate_outside"] is not None
                    else None,
                    notes=r["notes"],
                )
            )
            n += 1
        summary["daily_logs"] = n

    if "meals" in present:
        n = 0
        for r in cur.execute("SELECT * FROM meals"):
            db.add(
                Meal(
                    user_id=user.id,
                    date=_pdate(r["date"]),
                    label=r["label"] or "Meal",
                    time=r["time"],
                    calories=r["calories"],
                    description=r["description"],
                    ai_analysis=r["ai_analysis"],
                )
            )
            n += 1
        summary["meals"] = n

    if "activities" in present:
        n = 0
        old_to_new: dict[int, int] = {}
        for r in cur.execute("SELECT * FROM activities"):
            act = Activity(
                user_id=user.id,
                date=_pdate(r["date"]),
                name=r["name"] or "Activity",
                activity_type=ActivityType(r["activity_type"])
                if r["activity_type"]
                else ActivityType.CARDIO,
                time_of_day=TimeOfDay(r["time_of_day"]) if r["time_of_day"] else None,
                duration_mins=r["duration_mins"],
                calories=r["calories"],
                distance_km=r["distance_km"],
                url=r["url"],
                notes=r["notes"],
                tags=r["tags"],
            )
            db.add(act)
            db.flush()  # assign new id
            old_to_new[r["id"]] = act.id
            n += 1
        summary["activities"] = n

        if "exercises" in present:
            en = 0
            for r in cur.execute("SELECT * FROM exercises"):
                new_aid = old_to_new.get(r["activity_id"])
                if new_aid is None:
                    continue
                db.add(
                    Exercise(
                        activity_id=new_aid,
                        name=r["name"] or "",
                        sets=r["sets"],
                        reps=r["reps"],
                        weight_kg=r["weight_kg"],
                        notes=r["notes"],
                    )
                )
                en += 1
            summary["exercises"] = en

    if "body_measurements" in present:
        n = 0
        for r in cur.execute("SELECT * FROM body_measurements"):
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    date=_pdate(r["date"]),
                    neck=r["neck"],
                    shoulders=r["shoulders"],
                    chest=r["chest"],
                    bicep_left=r["bicep_left"],
                    bicep_right=r["bicep_right"],
                    forearm_left=r["forearm_left"],
                    forearm_right=r["forearm_right"],
                    waist=r["waist"],
                    abdomen=r["abdomen"],
                    hips=r["hips"],
                    thigh_left=r["thigh_left"],
                    thigh_right=r["thigh_right"],
                    calf_left=r["calf_left"],
                    calf_right=r["calf_right"],
                    notes=r["notes"],
                )
            )
            n += 1
        summary["body_measurements"] = n

    if "user_settings" in present:
        row = cur.execute("SELECT * FROM user_settings LIMIT 1").fetchone()
        if row:
            s = get_or_create_settings(db, user.id)
            for f in (
                "theme",
                "font_size",
                "font_family",
                "content_width",
                "color_scheme",
                "distance_unit",
                "measurement_unit",
                "weight_unit",
                "water_unit",
            ):
                if f in row.keys() and row[f] is not None:
                    setattr(s, f, row[f])
            summary["user_settings"] = 1

    db.commit()
    conn.close()
    return summary


class ImportDbResponse(BaseModel):
    success: bool
    message: str
    imported: dict[str, int] = {}


@router.post("/import-db", response_model=ImportDbResponse)
async def import_db(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore from an Askesis '.db' export (additive — use on a fresh account)."""
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(
            status_code=400, detail="Please upload an Askesis .db export file."
        )

    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(
        suffix=".db", prefix="askesis-import-", delete=False
    )
    tmp.write(content)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        try:
            check = sqlite3.connect(str(tmp_path))
            names = {
                r[0]
                for r in check.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            check.close()
        except sqlite3.DatabaseError:
            raise HTTPException(
                status_code=400, detail="File is not a valid SQLite database."
            )
        if "daily_logs" not in names and "_export_meta" not in names:
            raise HTTPException(
                status_code=400, detail="This doesn't look like an Askesis .db export."
            )

        try:
            imported = import_sqlite_export(db, current_user, tmp_path)
        except Exception as e:
            db.rollback()
            logger.exception("Import failed")
            raise HTTPException(status_code=500, detail=f"Import failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    total = sum(imported.values())
    parts = ", ".join(f"{k}: {v}" for k, v in imported.items())
    return ImportDbResponse(
        success=True, message=f"Imported {total} records ({parts}).", imported=imported
    )


class GSheetSyncResponse(BaseModel):
    success: bool
    message: str
    last_sync: str | None = None
    tabs: list[str] = []
    sheet_id: str | None = None


@router.post("/gsheet/sync", response_model=GSheetSyncResponse)
def sync_to_gsheet(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync all user data to their configured Google Sheet."""
    # Get user settings
    settings = get_or_create_settings(db, current_user.id)

    if not settings.google_sheet_id:
        raise HTTPException(
            status_code=400,
            detail="No Google Sheet ID configured. Please set a Sheet ID in settings.",
        )

    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google account not connected. Please re-login to grant access.",
        )

    try:
        logger.info(f"Starting sync to sheet: {settings.google_sheet_id}")
        result = sync_to_sheet(settings.google_sheet_id, current_user, db)

        # Update last sync timestamp
        settings.last_gsheet_sync = datetime.utcnow()
        db.commit()

        return GSheetSyncResponse(
            success=True,
            message=result["message"],
            last_sync=settings.last_gsheet_sync.isoformat(),
            tabs=result["tabs"],
            sheet_id=settings.google_sheet_id,
        )

    except Exception as e:
        logger.exception("Google Sheets sync failed")
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}",
        )
