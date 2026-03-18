import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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
    # Google Sheets sync settings
    google_sheet_id: str | None = None
    gsheet_sync_interval_hours: int | None = None
    last_gsheet_sync: datetime | None = None

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
    google_sheet_id: str | None = None
    gsheet_sync_interval_hours: int | None = None


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
    if settings_data.google_sheet_id is not None:
        settings.google_sheet_id = settings_data.google_sheet_id
    if settings_data.gsheet_sync_interval_hours is not None:
        settings.gsheet_sync_interval_hours = settings_data.gsheet_sync_interval_hours

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


def _backup_postgres(db: Session) -> tuple[bytes, str]:
    """Backup PostgreSQL database using pure Python. Returns (content, filename).

    Exports all tables as JSON for portability - no pg_dump version issues.
    """
    import json
    from sqlalchemy import inspect, text

    inspector = inspect(db.bind)
    tables = inspector.get_table_names()

    backup_data = {"version": 1, "created_at": datetime.now().isoformat(), "tables": {}}

    for table_name in tables:
        # Skip alembic version table
        if table_name == "alembic_version":
            continue

        result = db.execute(text(f'SELECT * FROM "{table_name}"'))
        columns = result.keys()
        rows = []
        for row in result.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert non-JSON-serializable types
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                elif isinstance(value, bytes):
                    value = value.hex()
                row_dict[col] = value
            rows.append(row_dict)

        backup_data["tables"][table_name] = {"columns": list(columns), "rows": rows}
        logger.info(f"Backed up {len(rows)} rows from {table_name}")

    json_content = json.dumps(backup_data, indent=2, default=str)
    return json_content.encode("utf-8"), "askesis_backup.json"


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
            db_content, filename = _backup_postgres(db)
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


class RestoreResponse(BaseModel):
    success: bool
    message: str
    tables_restored: list[str] = []
    rows_restored: int = 0


@router.post("/restore", response_model=RestoreResponse)
async def restore_database(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore database from a JSON backup file.

    WARNING: This will insert data into the database.
    Existing records with matching IDs will be skipped.
    """
    import json
    from datetime import date as date_type
    from sqlalchemy import text

    logger.info(f"Restore requested by user {current_user.email}")

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a JSON backup file.",
        )

    try:
        content = await file.read()
        backup_data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON file: {str(e)}",
        )

    if "tables" not in backup_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid backup format: missing 'tables' key.",
        )

    tables_restored = []
    total_rows = 0

    def parse_value(value, col_name: str):
        """Convert JSON values back to Python types."""
        if value is None:
            return None
        if isinstance(value, str):
            # Try datetime first
            if "T" in value and len(value) >= 19:
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    pass
            # Try date
            if len(value) == 10 and value.count("-") == 2:
                try:
                    return date_type.fromisoformat(value)
                except ValueError:
                    pass
        return value

    try:
        for table_name, table_data in backup_data["tables"].items():
            columns = table_data.get("columns", [])
            rows = table_data.get("rows", [])

            if not rows:
                continue

            col_list = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(f":{c}" for c in columns)
            insert_sql = (
                f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
            )

            inserted = 0
            for row in rows:
                parsed_row = {col: parse_value(row.get(col), col) for col in columns}
                try:
                    db.execute(text(insert_sql), parsed_row)
                    inserted += 1
                except Exception as e:
                    # Skip duplicates and constraint violations
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                        db.rollback()
                    else:
                        logger.warning(f"Skipping row in {table_name}: {e}")
                        db.rollback()

            if inserted > 0:
                db.commit()
                tables_restored.append(f"{table_name} ({inserted} rows)")
                total_rows += inserted
                logger.info(f"Restored {inserted} rows to {table_name}")

        return RestoreResponse(
            success=True,
            message=f"Restore completed. {total_rows} total rows restored.",
            tables_restored=tables_restored,
            rows_restored=total_rows,
        )

    except Exception as e:
        db.rollback()
        logger.exception("Restore failed")
        raise HTTPException(
            status_code=500,
            detail=f"Restore failed: {str(e)}",
        )
