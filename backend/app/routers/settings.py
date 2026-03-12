import logging
import os
import subprocess
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.database import get_db
from app.models import User, UserSettings
from app.routers.auth import get_current_user
from app.config import get_settings as get_app_settings
from app.google_drive import upload_backup

logger = logging.getLogger("askesis.settings")

router = APIRouter()


class UserSettingsSchema(BaseModel):
    theme: str = "system"
    font_size: str = "medium"  # xs, sm, medium, lg, xl, 2xl
    font_family: str = "space-grotesk"
    content_width: str = "medium"
    color_scheme: str = "forest"
    # Unit preferences
    distance_unit: str = "km"
    measurement_unit: str = "cm"
    weight_unit: str = "kg"
    water_unit: str = "ml"
    # Google Drive settings
    drive_parent_folder_id: str | None = None

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    font_size: str | None = None  # xs, sm, medium, lg, xl, 2xl
    font_family: str | None = None
    content_width: str | None = None
    color_scheme: str | None = None
    distance_unit: str | None = None
    measurement_unit: str | None = None
    weight_unit: str | None = None
    water_unit: str | None = None
    drive_parent_folder_id: str | None = None


def get_or_create_settings(db: Session, user_id: int) -> UserSettings:
    """Get existing settings or create with defaults."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

    if not settings:
        settings = UserSettings(
            user_id=user_id,
            theme="system",
            font_size="medium",
            font_family="space-grotesk",
            content_width="medium",
            color_scheme="forest",
            distance_unit="km",
            measurement_unit="cm",
            weight_unit="kg",
            water_unit="ml",
        )
        db.add(settings)
        try:
            db.commit()
            db.refresh(settings)
        except IntegrityError:
            # Another request created it, rollback and fetch
            db.rollback()
            settings = (
                db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            )

    return settings


@router.get("/", response_model=UserSettingsSchema)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )

    if not settings:
        return UserSettingsSchema()

    return settings


@router.put("/", response_model=UserSettingsSchema)
def update_settings(
    settings_data: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get or create settings (handles race condition)
    settings = get_or_create_settings(db, current_user.id)

    # Update fields
    if settings_data.theme is not None:
        settings.theme = settings_data.theme
    if settings_data.font_size is not None:
        settings.font_size = settings_data.font_size
    if settings_data.font_family is not None:
        settings.font_family = settings_data.font_family
    if settings_data.content_width is not None:
        settings.content_width = settings_data.content_width
    if settings_data.color_scheme is not None:
        settings.color_scheme = settings_data.color_scheme
    if settings_data.distance_unit is not None:
        settings.distance_unit = settings_data.distance_unit
    if settings_data.measurement_unit is not None:
        settings.measurement_unit = settings_data.measurement_unit
    if settings_data.weight_unit is not None:
        settings.weight_unit = settings_data.weight_unit
    if settings_data.water_unit is not None:
        settings.water_unit = settings_data.water_unit
    if settings_data.drive_parent_folder_id is not None:
        settings.drive_parent_folder_id = settings_data.drive_parent_folder_id

    db.commit()
    db.refresh(settings)
    return settings


class BackupResponse(BaseModel):
    success: bool
    message: str
    file_id: str | None = None


def _backup_sqlite(db_url: str) -> tuple[bytes, str]:
    """Backup SQLite database. Returns (content, filename)."""
    db_path = db_url.replace("sqlite:///", "")

    if not os.path.exists(db_path):
        raise HTTPException(
            status_code=404,
            detail=f"Database file not found: {db_path}",
        )

    with open(db_path, "rb") as f:
        return f.read(), "askesis_backup.db"


def _backup_postgres(db_url: str) -> tuple[bytes, str]:
    """Backup PostgreSQL database using pg_dump. Returns (content, filename)."""
    # Parse the database URL
    # Format: postgresql://user:password@host:port/dbname
    parsed = urlparse(db_url)

    # Build pg_dump environment with password
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    # Build pg_dump command - use plain SQL format for version compatibility
    cmd = ["pg_dump", "--format=plain", "--no-owner", "--no-acl"]

    if parsed.hostname:
        cmd.extend(["--host", parsed.hostname])
    if parsed.port:
        cmd.extend(["--port", str(parsed.port)])
    if parsed.username:
        cmd.extend(["--username", parsed.username])

    # Database name is the path without leading slash
    db_name = parsed.path.lstrip("/")
    cmd.append(db_name)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"pg_dump failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"pg_dump failed: {error_msg}",
            )

        return result.stdout, "askesis_backup.sql"

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="pg_dump not found. Please install PostgreSQL client tools.",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="Backup timed out after 5 minutes.",
        )


@router.post("/backup", response_model=BackupResponse)
def backup_database(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backup the database to Google Drive, overwriting any existing backup."""
    logger.info(f"Backup requested by user {current_user.email}")
    logger.info(f"Refresh token present: {bool(current_user.google_refresh_token)}")

    # Check if user has refresh token for Drive access
    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google Drive access not configured. Please re-login to grant Drive access.",
        )

    # Get user's settings for parent folder
    user_settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )
    parent_folder_id = user_settings.drive_parent_folder_id if user_settings else None

    # Get database URL from config
    app_settings = get_app_settings()
    db_url = app_settings.database_url

    try:
        # Determine database type and backup accordingly
        if db_url.startswith("sqlite"):
            db_content, filename = _backup_sqlite(db_url)
        elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
            db_content, filename = _backup_postgres(db_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Backup only supported for SQLite and PostgreSQL databases.",
            )

        # Upload to Google Drive (overwrites existing)
        file_id = upload_backup(
            refresh_token=current_user.google_refresh_token,
            file_content=db_content,
            filename=filename,
            parent_folder_id=parent_folder_id,
        )

        return BackupResponse(
            success=True,
            message=f"Backup completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            file_id=file_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Backup failed")
        raise HTTPException(
            status_code=500,
            detail=f"Backup failed: {str(e)}",
        )
