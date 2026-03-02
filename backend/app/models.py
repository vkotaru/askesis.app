from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Date, DateTime, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class ActivityType(enum.Enum):
    CARDIO = "cardio"
    STRENGTH = "strength"


class PhotoView(enum.Enum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    daily_logs: Mapped[list["DailyLog"]] = relationship(back_populates="user")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user")
    activities: Mapped[list["Activity"]] = relationship(back_populates="user")
    settings: Mapped["UserSettings | None"] = relationship(back_populates="user", uselist=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    theme: Mapped[str] = mapped_column(String(20), default="system")  # light, dark, system
    font_size: Mapped[str] = mapped_column(String(20), default="medium")  # small, medium, large
    font_family: Mapped[str] = mapped_column(String(50), default="space-grotesk")
    content_width: Mapped[str] = mapped_column(String(20), default="medium")  # narrow, medium, wide, full
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="settings")


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    weight: Mapped[float | None] = mapped_column(Float)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    water_ml: Mapped[int | None] = mapped_column(Integer)
    feelings: Mapped[str | None] = mapped_column(String(255))  # Comma-separated feelings
    caffeine_mg: Mapped[int | None] = mapped_column(Integer)
    ate_outside: Mapped[bool | None] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="daily_logs")


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(50))  # Breakfast, Lunch, etc.
    time: Mapped[str | None] = mapped_column(String(10))  # HH:MM format
    calories: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))  # Path to meal photo
    ai_analysis: Mapped[str | None] = mapped_column(Text)  # Gemini analysis result
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="meals")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(100))
    activity_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType))
    duration_mins: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(255))  # Comma-separated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="activities")
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="activity")


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    name: Mapped[str] = mapped_column(String(100))
    sets: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[str | None] = mapped_column(String(50))  # "10,10,8" format
    weight_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    activity: Mapped["Activity"] = relationship(back_populates="exercises")


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    # Upper body
    neck: Mapped[float | None] = mapped_column(Float)
    shoulders: Mapped[float | None] = mapped_column(Float)
    chest: Mapped[float | None] = mapped_column(Float)
    bicep_left: Mapped[float | None] = mapped_column(Float)
    bicep_right: Mapped[float | None] = mapped_column(Float)
    forearm_left: Mapped[float | None] = mapped_column(Float)
    forearm_right: Mapped[float | None] = mapped_column(Float)
    # Core
    waist: Mapped[float | None] = mapped_column(Float)
    abdomen: Mapped[float | None] = mapped_column(Float)
    hips: Mapped[float | None] = mapped_column(Float)
    # Lower body
    thigh_left: Mapped[float | None] = mapped_column(Float)
    thigh_right: Mapped[float | None] = mapped_column(Float)
    calf_left: Mapped[float | None] = mapped_column(Float)
    calf_right: Mapped[float | None] = mapped_column(Float)
    # Notes
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")


class MealTemplate(Base):
    __tablename__ = "meal_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(50))
    calories: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)


class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    activity_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType))
    default_duration_mins: Mapped[int | None] = mapped_column(Integer)
    default_tags: Mapped[str | None] = mapped_column(String(255))
    exercises_json: Mapped[str | None] = mapped_column(Text)  # JSON for strength templates


class ProgressPhoto(Base):
    __tablename__ = "progress_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    view: Mapped[PhotoView] = mapped_column(Enum(PhotoView))  # front, side, back
    file_path: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")
