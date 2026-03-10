"""CSV import router for bulk data import."""

import csv
import io
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Activity, Exercise, DailyLog, BodyMeasurement, ActivityType, TimeOfDay
from app.routers.auth import get_current_user
from app.units import (
    to_metric_distance,
    to_metric_measurement,
    to_metric_weight,
    to_metric_water,
)

router = APIRouter()


class PreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, str]]
    total_rows: int


class ColumnMapping(BaseModel):
    """Maps a CSV column to a data field."""
    csv_column: str
    field: str
    unit: str | None = None  # For numeric fields that need conversion


class ImportRequest(BaseModel):
    """Request body for import endpoints."""
    data: list[dict[str, Any]]
    column_mapping: list[ColumnMapping]
    unit_mapping: dict[str, str] = Field(default_factory=dict)  # field -> unit


class ImportResult(BaseModel):
    success_count: int
    error_count: int
    errors: list[str]


def parse_date(value: str) -> date | None:
    """Parse date from common formats."""
    if not value:
        return None

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {value}")


def parse_float(value: str) -> float | None:
    """Parse float, returning None for empty values."""
    if not value or value.strip() == "":
        return None
    return float(value.strip().replace(",", ""))


def parse_int(value: str) -> int | None:
    """Parse int, returning None for empty values."""
    if not value or value.strip() == "":
        return None
    return int(float(value.strip().replace(",", "")))


def parse_bool(value: str) -> bool | None:
    """Parse boolean from various formats."""
    if not value or value.strip() == "":
        return None

    v = value.strip().lower()
    if v in ("true", "yes", "1", "y"):
        return True
    if v in ("false", "no", "0", "n"):
        return False
    return None


def apply_column_mapping(row: dict[str, str], mappings: list[ColumnMapping]) -> dict[str, Any]:
    """Apply column mapping to convert CSV row to field dict."""
    result = {}
    for mapping in mappings:
        if mapping.csv_column in row:
            result[mapping.field] = row[mapping.csv_column]
    return result


def convert_units(data: dict[str, Any], unit_mapping: dict[str, str], field_types: dict[str, str]) -> dict[str, Any]:
    """Convert values to metric based on unit mapping.

    field_types maps field names to their type: 'distance', 'measurement', 'weight', 'water'
    """
    result = data.copy()

    for field, unit in unit_mapping.items():
        if field not in result or result[field] is None:
            continue

        value = parse_float(str(result[field])) if isinstance(result[field], str) else result[field]
        if value is None:
            continue

        field_type = field_types.get(field)
        if field_type == "distance":
            result[field] = to_metric_distance(value, unit)
        elif field_type == "measurement":
            result[field] = to_metric_measurement(value, unit)
        elif field_type == "weight":
            result[field] = to_metric_weight(value, unit)
        elif field_type == "water":
            result[field] = to_metric_water(value, unit)

    return result


@router.post("/preview", response_model=PreviewResponse)
async def preview_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a CSV file and preview its structure."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []

    # Read all rows to count, but only return first 5 for preview
    all_rows = list(reader)
    preview_rows = all_rows[:5]

    return PreviewResponse(
        columns=list(columns),
        rows=preview_rows,
        total_rows=len(all_rows),
    )


@router.post("/activities", response_model=ImportResult)
def import_activities(
    request: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import activities from mapped CSV data."""
    # Field types for unit conversion
    field_types = {
        "distance_km": "distance",
    }

    success_count = 0
    errors = []

    for i, row in enumerate(request.data):
        try:
            # Apply column mapping
            mapped = apply_column_mapping(row, request.column_mapping)

            # Convert units
            mapped = convert_units(mapped, request.unit_mapping, field_types)

            # Parse fields
            activity_date = parse_date(mapped.get("date", ""))
            if not activity_date:
                raise ValueError("Date is required")

            name = mapped.get("name", "").strip()
            if not name:
                raise ValueError("Name is required")

            # Parse activity type
            activity_type_str = mapped.get("activity_type", "cardio").lower().strip()
            try:
                activity_type = ActivityType(activity_type_str)
            except ValueError:
                activity_type = ActivityType.CARDIO

            # Parse time of day
            time_of_day = None
            tod_str = mapped.get("time_of_day", "").lower().strip()
            if tod_str:
                try:
                    time_of_day = TimeOfDay(tod_str)
                except ValueError:
                    pass

            activity = Activity(
                user_id=current_user.id,
                date=activity_date,
                name=name,
                activity_type=activity_type,
                time_of_day=time_of_day,
                duration_mins=parse_int(str(mapped.get("duration_mins", ""))),
                calories=parse_int(str(mapped.get("calories", ""))),
                distance_km=parse_float(str(mapped.get("distance_km", ""))),
                url=mapped.get("url", "").strip() or None,
                notes=mapped.get("notes", "").strip() or None,
                tags=mapped.get("tags", "").strip() or None,
            )

            db.add(activity)
            success_count += 1

        except Exception as e:
            errors.append(f"Row {i + 1}: {str(e)}")

    if success_count > 0:
        db.commit()

    return ImportResult(
        success_count=success_count,
        error_count=len(errors),
        errors=errors[:20],  # Limit errors shown
    )


@router.post("/daily-logs", response_model=ImportResult)
def import_daily_logs(
    request: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import daily logs from mapped CSV data."""
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"Import daily logs: {len(request.data)} rows, user={current_user.id}")
    logger.info(f"Column mapping: {request.column_mapping}")
    logger.info(f"Unit mapping: {request.unit_mapping}")
    if request.data:
        logger.info(f"Sample row: {request.data[0]}")

    field_types = {
        "weight": "weight",
        "water_ml": "water",
    }

    success_count = 0
    errors = []

    for i, row in enumerate(request.data):
        try:
            mapped = apply_column_mapping(row, request.column_mapping)
            if i == 0:
                logger.info(f"Row 0 after column mapping: {mapped}")
            mapped = convert_units(mapped, request.unit_mapping, field_types)
            if i == 0:
                logger.info(f"Row 0 after unit conversion: {mapped}")

            log_date = parse_date(mapped.get("date", ""))
            if not log_date:
                raise ValueError("Date is required")

            if i == 0:
                logger.info(f"Row 0 parsed date: {log_date}")

            # Check for existing log on this date
            existing = db.query(DailyLog).filter(
                DailyLog.user_id == current_user.id,
                DailyLog.date == log_date
            ).first()

            if existing:
                logger.info(f"Row {i}: Updating existing log for {log_date}")
                # Update existing log
                if mapped.get("weight"):
                    existing.weight = parse_float(str(mapped["weight"]))
                if mapped.get("sleep_hours"):
                    existing.sleep_hours = parse_float(str(mapped["sleep_hours"]))
                if mapped.get("steps"):
                    existing.steps = parse_int(str(mapped["steps"]))
                if mapped.get("water_ml"):
                    existing.water_ml = parse_int(str(mapped["water_ml"]))
                if mapped.get("caffeine_mg"):
                    existing.caffeine_mg = parse_int(str(mapped["caffeine_mg"]))
                if mapped.get("notes"):
                    existing.notes = mapped["notes"].strip() or None
            else:
                # Create new log
                weight_val = parse_float(str(mapped.get("weight", "")))
                logger.info(f"Row {i}: Creating new log for {log_date}, weight={weight_val}")
                log = DailyLog(
                    user_id=current_user.id,
                    date=log_date,
                    weight=weight_val,
                    sleep_hours=parse_float(str(mapped.get("sleep_hours", ""))),
                    steps=parse_int(str(mapped.get("steps", ""))),
                    water_ml=parse_int(str(mapped.get("water_ml", ""))),
                    caffeine_mg=parse_int(str(mapped.get("caffeine_mg", ""))),
                    notes=mapped.get("notes", "").strip() or None,
                )
                db.add(log)

            success_count += 1

        except Exception as e:
            logger.error(f"Row {i + 1} error: {str(e)}")
            errors.append(f"Row {i + 1}: {str(e)}")

    if success_count > 0:
        db.commit()
        logger.info(f"Committed {success_count} daily logs to database")

    # Verify the data was saved
    total_logs = db.query(DailyLog).filter(DailyLog.user_id == current_user.id).count()
    logger.info(f"Total daily logs for user {current_user.id}: {total_logs}")

    return ImportResult(
        success_count=success_count,
        error_count=len(errors),
        errors=errors[:20],
    )


@router.post("/measurements", response_model=ImportResult)
def import_measurements(
    request: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import body measurements from mapped CSV data."""
    # All measurement fields use measurement unit conversion
    measurement_fields = [
        "neck", "shoulders", "chest", "bicep_left", "bicep_right",
        "forearm_left", "forearm_right", "waist", "abdomen", "hips",
        "thigh_left", "thigh_right", "calf_left", "calf_right",
    ]
    field_types = {f: "measurement" for f in measurement_fields}

    success_count = 0
    errors = []

    for i, row in enumerate(request.data):
        try:
            mapped = apply_column_mapping(row, request.column_mapping)
            mapped = convert_units(mapped, request.unit_mapping, field_types)

            measurement_date = parse_date(mapped.get("date", ""))
            if not measurement_date:
                raise ValueError("Date is required")

            # Check for existing measurement on this date
            existing = db.query(BodyMeasurement).filter(
                BodyMeasurement.user_id == current_user.id,
                BodyMeasurement.date == measurement_date
            ).first()

            measurement_data = {}
            for field in measurement_fields:
                if mapped.get(field):
                    measurement_data[field] = parse_float(str(mapped[field]))

            if mapped.get("notes"):
                measurement_data["notes"] = mapped["notes"].strip() or None

            if existing:
                # Update existing measurement
                for field, value in measurement_data.items():
                    if value is not None:
                        setattr(existing, field, value)
            else:
                # Create new measurement
                measurement = BodyMeasurement(
                    user_id=current_user.id,
                    date=measurement_date,
                    **measurement_data,
                )
                db.add(measurement)

            success_count += 1

        except Exception as e:
            errors.append(f"Row {i + 1}: {str(e)}")

    if success_count > 0:
        db.commit()

    return ImportResult(
        success_count=success_count,
        error_count=len(errors),
        errors=errors[:20],
    )
