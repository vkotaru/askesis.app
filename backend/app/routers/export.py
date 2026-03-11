"""Export user data to SQLite database file."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User,
    DailyLog,
    Meal,
    Activity,
    Exercise,
    BodyMeasurement,
    ProgressPhoto,
    UserSettings,
)
from app.routers.auth import get_current_user

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
    logs = db.query(DailyLog).filter(DailyLog.user_id == user.id).all()
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
    meals = db.query(Meal).filter(Meal.user_id == user.id).all()
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
    activities = db.query(Activity).filter(Activity.user_id == user.id).all()
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
        db.query(BodyMeasurement).filter(BodyMeasurement.user_id == user.id).all()
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
    photos = db.query(ProgressPhoto).filter(ProgressPhoto.user_id == user.id).all()
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
