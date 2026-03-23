"""Google Sheets sync service for exporting app data.

Syncs data to user's Google Sheet with tabs:
- Daily_Log: weight, meals, water, steps, macros
- Activities: workouts with duration, distance, calories
- Measurements: body measurements
- Photos: progress photos as embedded images
"""

import logging
import os
from datetime import date
from collections import defaultdict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    User,
    DailyLog,
    Meal,
    DailyNutrition,
    Activity,
    BodyMeasurement,
    ProgressPhoto,
)
from app.google_drive import get_drive_service, get_or_create_app_folder

logger = logging.getLogger("askesis.google_sheets")

# Sheet tab names
DAILY_LOG_TAB = "Daily_Log"
ACTIVITIES_TAB = "Activities"
MEASUREMENTS_TAB = "Measurements"
PHOTOS_TAB = "Photos"


def get_sheets_service(refresh_token: str):
    """Build Google Sheets service using refresh token."""
    settings = get_settings()

    logger.info("Building Sheets service with refresh token")

    credentials = Credentials(
        token=None,  # Will be refreshed
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    try:
        service = build("sheets", "v4", credentials=credentials)
        logger.info("Sheets service built successfully")
        return service
    except Exception as e:
        logger.error(f"Failed to build Sheets service: {e}")
        raise


def _ensure_worksheet(service, spreadsheet_id: str, tab_name: str) -> int:
    """Ensure a worksheet tab exists. Returns the sheet ID."""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get("sheets", [])

        for sheet in sheets:
            if sheet["properties"]["title"] == tab_name:
                return sheet["properties"]["sheetId"]

        # Create the tab
        request = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
        response = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=request)
            .execute()
        )
        return response["replies"][0]["addSheet"]["properties"]["sheetId"]

    except HttpError as e:
        logger.error(f"Failed to ensure worksheet {tab_name}: {e}")
        raise


def _clear_and_write(
    service, spreadsheet_id: str, tab_name: str, data: list[list]
) -> int:
    """Clear a tab and write new data. Returns number of data rows (excluding header)."""
    range_name = f"{tab_name}!A1"

    # Clear existing content
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A:ZZ",
    ).execute()

    # Write new data
    if data:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": data},
        ).execute()

    row_count = len(data) - 1 if len(data) > 1 else 0  # Exclude header
    logger.info(f"Wrote {row_count} data rows to {tab_name}")
    return row_count


def _sync_daily_log(service, spreadsheet_id: str, user_id: int, db: Session) -> int:
    """Sync Daily_Log tab with columns matching user's format. Returns row count."""
    _ensure_worksheet(service, spreadsheet_id, DAILY_LOG_TAB)

    # Header row
    headers = [
        "date",
        "Weight (kg)",
        "Breakfast",
        "Lunch",
        "Dinner",
        "Snacks",
        "Water (L)",
        "Total Cals",
        "Protein (g)",
        "Steps",
        "Carbs (g)",
        "Fat (g)",
        "Active Cals",
        "Sleep (hrs)",
        "Missed Out",
    ]

    # Get all daily logs
    daily_logs = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == user_id)
        .filter(DailyLog.deleted_at == None)
        .order_by(DailyLog.date.desc())
        .all()
    )

    # Get all meals grouped by date
    meals = db.query(Meal).filter(Meal.user_id == user_id).filter(Meal.deleted_at == None).all()
    meals_by_date: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_cals_by_date: dict[date, int] = defaultdict(int)

    for meal in meals:
        if meal.calories:
            # Map meal labels to columns
            label = meal.label.lower()
            if "breakfast" in label or "meal 1" in label:
                col = "Breakfast"
            elif "lunch" in label or "meal 2" in label:
                col = "Lunch"
            elif "dinner" in label or "meal 3" in label:
                col = "Dinner"
            else:
                col = "Snacks"
            meals_by_date[meal.date][col] += meal.calories
            total_cals_by_date[meal.date] += meal.calories

    # Get nutrition (macros) by date
    nutrition = db.query(DailyNutrition).filter(DailyNutrition.user_id == user_id).all()
    nutrition_by_date: dict[date, DailyNutrition] = {n.date: n for n in nutrition}

    # Get activities for active calories
    activities = db.query(Activity).filter(Activity.user_id == user_id).filter(Activity.deleted_at == None).all()
    active_cals_by_date: dict[date, int] = defaultdict(int)
    for activity in activities:
        if activity.calories:
            active_cals_by_date[activity.date] += activity.calories

    # Collect all dates
    all_dates = set()
    for log in daily_logs:
        all_dates.add(log.date)
    for meal in meals:
        all_dates.add(meal.date)
    for n in nutrition:
        all_dates.add(n.date)
    for a in activities:
        all_dates.add(a.date)

    # Build data rows
    data = [headers]
    logs_by_date = {log.date: log for log in daily_logs}

    for d in sorted(all_dates, reverse=True):
        log = logs_by_date.get(d)
        nutr = nutrition_by_date.get(d)
        meal_data = meals_by_date.get(d, {})

        row = [
            d.isoformat(),
            log.weight if log and log.weight else "",
            meal_data.get("Breakfast", "") or "",
            meal_data.get("Lunch", "") or "",
            meal_data.get("Dinner", "") or "",
            meal_data.get("Snacks", "") or "",
            round(log.water_ml / 1000, 2) if log and log.water_ml else "",
            total_cals_by_date.get(d, "") or "",
            nutr.protein_g if nutr and nutr.protein_g else "",
            log.steps if log and log.steps else "",
            nutr.carbs_g if nutr and nutr.carbs_g else "",
            nutr.fat_g if nutr and nutr.fat_g else "",
            active_cals_by_date.get(d, "") or "",
            log.sleep_hours if log and log.sleep_hours else "",
            log.notes if log and log.notes else "",
        ]
        data.append(row)

    return _clear_and_write(service, spreadsheet_id, DAILY_LOG_TAB, data)


def _sync_activities(service, spreadsheet_id: str, user_id: int, db: Session) -> int:
    """Sync Activities tab. Returns row count."""
    _ensure_worksheet(service, spreadsheet_id, ACTIVITIES_TAB)

    headers = [
        "date",
        "activity_name",
        "form_type",
        "duration_seconds",
        "distance_miles",
        "calories_kcal",
        "notes",
        "tags",
    ]

    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .filter(Activity.deleted_at == None)
        .order_by(Activity.date.desc())
        .all()
    )

    data = [headers]
    for a in activities:
        # Convert km to miles
        distance_miles = round(a.distance_km * 0.621371, 2) if a.distance_km else ""
        # Convert mins to seconds
        duration_secs = a.duration_mins * 60 if a.duration_mins else ""

        row = [
            a.date.isoformat(),
            a.name,
            a.activity_type.value if a.activity_type else "",
            duration_secs,
            distance_miles,
            a.calories or "",
            a.notes or "",
            a.tags or "",
        ]
        data.append(row)

    return _clear_and_write(service, spreadsheet_id, ACTIVITIES_TAB, data)


def _sync_measurements(service, spreadsheet_id: str, user_id: int, db: Session) -> int:
    """Sync Measurements tab with inches conversion. Returns row count."""
    _ensure_worksheet(service, spreadsheet_id, MEASUREMENTS_TAB)

    headers = [
        "date",
        "Waist (in)",
        "Chest (in)",
        "Right Bicep (in)",
        "Left Bicep (in)",
        "Right Thigh (in)",
        "Left Thigh (in)",
    ]

    measurements = (
        db.query(BodyMeasurement)
        .filter(BodyMeasurement.user_id == user_id)
        .filter(BodyMeasurement.deleted_at == None)
        .order_by(BodyMeasurement.date.desc())
        .all()
    )

    def cm_to_in(val):
        """Convert cm to inches."""
        return round(val / 2.54, 2) if val else ""

    data = [headers]
    for m in measurements:
        row = [
            m.date.isoformat(),
            cm_to_in(m.waist),
            cm_to_in(m.chest),
            cm_to_in(m.bicep_right),
            cm_to_in(m.bicep_left),
            cm_to_in(m.thigh_right),
            cm_to_in(m.thigh_left),
        ]
        data.append(row)

    return _clear_and_write(service, spreadsheet_id, MEASUREMENTS_TAB, data)


def _upload_local_photo_to_drive(
    refresh_token: str,
    file_path: str,
    parent_folder_id: str | None = None,
) -> str | None:
    """Upload a local photo to Drive and return the file_id."""
    if not os.path.exists(file_path):
        logger.warning(f"Local photo file not found: {file_path}")
        return None

    try:
        drive_service = get_drive_service(refresh_token)
        folder_id = get_or_create_app_folder(drive_service, parent_folder_id)

        filename = os.path.basename(file_path)
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }

        media = MediaFileUpload(file_path, mimetype="image/jpeg", resumable=True)
        file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        file_id = file.get("id")
        logger.info(f"Uploaded {filename} to Drive: {file_id}")

        # Set permissions to "anyone with link can view" for IMAGE formula to work
        _make_file_public(drive_service, file_id)

        return file_id

    except Exception as e:
        logger.error(f"Failed to upload photo {file_path}: {e}")
        return None


def _make_file_public(drive_service, file_id: str):
    """Set file permissions so anyone with link can view (required for =IMAGE())."""
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        logger.info(f"Set public permissions for file {file_id}")
    except Exception as e:
        logger.warning(f"Failed to set public permissions for {file_id}: {e}")


def _sync_photos(
    service,
    spreadsheet_id: str,
    user_id: int,
    db: Session,
    refresh_token: str,
    parent_folder_id: str | None = None,
) -> int:
    """Sync Photos tab with embedded IMAGE formulas. Returns row count."""
    _ensure_worksheet(service, spreadsheet_id, PHOTOS_TAB)

    headers = ["date", "Front", "Side", "Back"]

    photos = (
        db.query(ProgressPhoto)
        .filter(ProgressPhoto.user_id == user_id)
        .filter(ProgressPhoto.deleted_at == None)
        .order_by(ProgressPhoto.date.desc())
        .all()
    )

    logger.info(f"Found {len(photos)} photos for user {user_id}")

    # Group photos by date
    photos_by_date: dict[date, dict[str, str]] = defaultdict(dict)
    for photo in photos:
        drive_file_id = photo.drive_file_id

        # If no drive_file_id but has local file_path, upload to Drive
        if not drive_file_id and photo.file_path:
            logger.info(f"Photo {photo.id} has local path, uploading to Drive...")
            drive_file_id = _upload_local_photo_to_drive(
                refresh_token, photo.file_path, parent_folder_id
            )
            if drive_file_id:
                # Save the drive_file_id to the database
                photo.drive_file_id = drive_file_id
                db.commit()
                logger.info(f"Saved drive_file_id {drive_file_id} for photo {photo.id}")

        if drive_file_id:
            # Ensure the file is publicly viewable for =IMAGE() to work
            try:
                drive_service = get_drive_service(refresh_token)
                _make_file_public(drive_service, drive_file_id)
            except Exception as e:
                logger.warning(
                    f"Could not set public permissions for {drive_file_id}: {e}"
                )

            # Normalize view to capitalized form (front -> Front)
            view_value = (
                photo.view.value if hasattr(photo.view, "value") else str(photo.view)
            )
            view = view_value.lower().capitalize()  # Ensure "Front", "Side", "Back"
            image_formula = (
                f'=IMAGE("https://drive.google.com/uc?export=view&id={drive_file_id}")'
            )
            photos_by_date[photo.date][view] = image_formula
            logger.info(
                f"Photo {photo.id}: date={photo.date}, view={view}, drive_id={drive_file_id}"
            )
        else:
            logger.warning(
                f"Photo {photo.id} has no drive_file_id and no local file, skipping"
            )

    data = [headers]
    for d in sorted(photos_by_date.keys(), reverse=True):
        photo_data = photos_by_date[d]
        row = [
            d.isoformat(),
            photo_data.get("Front", ""),
            photo_data.get("Side", ""),
            photo_data.get("Back", ""),
        ]
        data.append(row)

    logger.info(f"Writing {len(data) - 1} photo rows to sheet")
    return _clear_and_write(service, spreadsheet_id, PHOTOS_TAB, data)


def sync_to_sheet(sheet_id: str, user: User, db: Session) -> dict:
    """
    Sync all user data to a Google Sheet.

    Args:
        sheet_id: The Google Spreadsheet ID
        user: The user whose data to sync
        db: Database session

    Returns:
        Dict with sync results
    """
    from app.models import UserSettings

    if not user.google_refresh_token:
        raise ValueError("User has no Google refresh token")

    # Get user settings for Drive parent folder
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    parent_folder_id = settings.drive_parent_folder_id if settings else None

    logger.info(f"Syncing to sheet ID: {sheet_id} for user {user.id}")
    service = get_sheets_service(user.google_refresh_token)

    try:
        # Sync each tab and capture row counts
        daily_rows = _sync_daily_log(service, sheet_id, user.id, db)
        activity_rows = _sync_activities(service, sheet_id, user.id, db)
        measurement_rows = _sync_measurements(service, sheet_id, user.id, db)
        photo_rows = _sync_photos(
            service,
            sheet_id,
            user.id,
            db,
            user.google_refresh_token,
            parent_folder_id,
        )

        total_rows = daily_rows + activity_rows + measurement_rows + photo_rows
        row_summary = f"Daily_Log: {daily_rows}, Activities: {activity_rows}, Measurements: {measurement_rows}, Photos: {photo_rows}"

        return {
            "success": True,
            "message": f"Synced {total_rows} rows ({row_summary})",
            "tabs": [DAILY_LOG_TAB, ACTIVITIES_TAB, MEASUREMENTS_TAB, PHOTOS_TAB],
            "row_counts": {
                DAILY_LOG_TAB: daily_rows,
                ACTIVITIES_TAB: activity_rows,
                MEASUREMENTS_TAB: measurement_rows,
                PHOTOS_TAB: photo_rows,
            },
        }

    except HttpError as e:
        logger.error(f"Google Sheets API error: {e.status_code} - {e.reason}")
        raise
    except Exception as e:
        logger.error(f"Sync failed: {type(e).__name__}: {e}")
        raise
