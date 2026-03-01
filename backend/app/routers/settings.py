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
    font_size: str = "medium"
    font_family: str = "space-grotesk"
    content_width: str = "medium"

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    font_size: str | None = None
    font_family: str | None = None
    content_width: str | None = None


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

    db.commit()
    db.refresh(settings)
    return settings
