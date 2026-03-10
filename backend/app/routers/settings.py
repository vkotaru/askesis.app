from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.database import get_db
from app.models import User, UserSettings
from app.routers.auth import get_current_user

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


def get_or_create_settings(db: Session, user_id: int) -> UserSettings:
    """Get existing settings or create with defaults."""
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == user_id
    ).first()

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
            settings = db.query(UserSettings).filter(
                UserSettings.user_id == user_id
            ).first()

    return settings


@router.get("/", response_model=UserSettingsSchema)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()

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

    db.commit()
    db.refresh(settings)
    return settings
