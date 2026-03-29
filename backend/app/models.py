from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import (
    String,
    Integer,
    Float,
    Text,
    ForeignKey,
    Date,
    DateTime,
    Enum,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class ActivityType(enum.Enum):
    CARDIO = "cardio"
    STRENGTH = "strength"


class TrainingPlanStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PhotoView(enum.Enum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class TimeOfDay(enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(500))
    google_refresh_token: Mapped[str | None] = mapped_column(
        Text
    )  # For Google Drive API access
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    daily_logs: Mapped[list["DailyLog"]] = relationship(back_populates="user")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user")
    daily_nutrition: Mapped[list["DailyNutrition"]] = relationship(
        back_populates="user"
    )
    activities: Mapped[list["Activity"]] = relationship(back_populates="user")
    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", uselist=False
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    theme: Mapped[str] = mapped_column(
        String(20), default="system"
    )  # light, dark, system
    font_size: Mapped[str] = mapped_column(
        String(20), default="medium"
    )  # small, medium, large
    font_family: Mapped[str] = mapped_column(String(50), default="space-grotesk")
    content_width: Mapped[str] = mapped_column(
        String(20), default="medium"
    )  # narrow, medium, wide, full
    color_scheme: Mapped[str] = mapped_column(
        String(30), default="forest"
    )  # forest, ocean, sunset, lavender, slate
    # Unit preferences (stored in metric, converted for display)
    distance_unit: Mapped[str] = mapped_column(String(10), default="km")  # km, mi
    measurement_unit: Mapped[str] = mapped_column(String(10), default="cm")  # cm, in
    weight_unit: Mapped[str] = mapped_column(String(10), default="kg")  # kg, lb
    water_unit: Mapped[str] = mapped_column(String(10), default="ml")  # ml, L, oz, cups
    # Nutrition targets
    calorie_target: Mapped[int | None] = mapped_column(Integer)  # Daily calorie goal
    protein_target: Mapped[int | None] = mapped_column(
        Integer
    )  # Daily protein goal in grams
    # Google Drive settings
    drive_parent_folder_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # Optional: parent folder ID in user's Drive
    # Google Sheets sync settings
    google_sheet_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # Sheet ID for export sync
    gsheet_sync_interval_hours: Mapped[int | None] = mapped_column(
        Integer
    )  # Auto-sync interval in hours (null = disabled)
    last_gsheet_sync: Mapped[datetime | None] = mapped_column(
        DateTime
    )  # Last successful sync timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

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
    feelings: Mapped[str | None] = mapped_column(
        String(255)
    )  # Comma-separated feelings
    caffeine_mg: Mapped[int | None] = mapped_column(Integer)
    ate_outside: Mapped[bool | None] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="daily_logs")

    __table_args__ = (Index("ix_daily_logs_user_date", "user_id", "date"),)


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(50))  # Breakfast, Lunch, etc.
    time: Mapped[str | None] = mapped_column(String(10))  # HH:MM format
    calories: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))  # Legacy local path
    drive_file_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # Google Drive file ID
    ai_analysis: Mapped[str | None] = mapped_column(Text)  # Gemini analysis result
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="meals")
    food_items: Mapped[list["MealFoodItem"]] = relationship(
        back_populates="meal", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_meals_user_date", "user_id", "date"),)


class FoodItem(Base):
    """Custom food database shared across users."""

    __tablename__ = "food_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id")
    )  # NULL = system/seed item
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    # Nutrition per serving
    serving_size: Mapped[float] = mapped_column(Float, default=1.0)
    serving_unit: Mapped[str] = mapped_column(String(20), default="g")
    calories: Mapped[int | None] = mapped_column(Integer)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(String(50))  # manual, ai_analysis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "name", "brand", name="unique_food_item"),
    )


class MealFoodItem(Base):
    """Links food items to meals with quantity."""

    __tablename__ = "meal_food_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(
        ForeignKey("meals.id", ondelete="CASCADE"), index=True
    )
    food_item_id: Mapped[int] = mapped_column(ForeignKey("food_items.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)  # number of servings
    notes: Mapped[str | None] = mapped_column(String(255))

    meal: Mapped["Meal"] = relationship(back_populates="food_items")
    food_item: Mapped["FoodItem"] = relationship("FoodItem")


class DailyNutrition(Base):
    """Daily nutrition totals - separate from meals for manual entry or import."""

    __tablename__ = "daily_nutrition"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="daily_nutrition")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="unique_user_nutrition_date"),
        Index("ix_daily_nutrition_user_date", "user_id", "date"),
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(100))
    activity_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType))
    time_of_day: Mapped[TimeOfDay | None] = mapped_column(
        Enum(TimeOfDay), nullable=True
    )
    duration_mins: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(
        String(500)
    )  # External link (Strava, Hevy, Garmin)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(255))  # Comma-separated
    icon: Mapped[str | None] = mapped_column(
        String(50)
    )  # Icon name (e.g., 'dumbbell', 'bike')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="activities")
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="activity")

    __table_args__ = (Index("ix_activities_user_date", "user_id", "date"),)


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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (Index("ix_body_measurements_user_date", "user_id", "date"),)


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
    exercises_json: Mapped[str | None] = mapped_column(
        Text
    )  # JSON for strength templates


class ProgressPhoto(Base):
    __tablename__ = "progress_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    view: Mapped[PhotoView] = mapped_column(Enum(PhotoView))  # front, side, back
    file_path: Mapped[str | None] = mapped_column(
        String(500)
    )  # Legacy local path (deprecated)
    drive_file_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # Google Drive file ID
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (Index("ix_progress_photos_user_date", "user_id", "date"),)


class ReportToken(Base):
    __tablename__ = "report_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")


class DataShare(Base):
    __tablename__ = "data_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shared_with_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    categories: Mapped[str] = mapped_column(
        String(255)
    )  # Comma-separated: "daily_logs,nutrition"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])
    shared_with: Mapped["User"] = relationship("User", foreign_keys=[shared_with_id])

    __table_args__ = (
        UniqueConstraint("owner_id", "shared_with_id", name="unique_share"),
    )


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_name: Mapped[str] = mapped_column(String(100))
    plan_display_name: Mapped[str] = mapped_column(String(200))
    race_date: Mapped[date] = mapped_column(Date)
    race_distance_km: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[TrainingPlanStatus] = mapped_column(
        Enum(TrainingPlanStatus), default=TrainingPlanStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User")
    planned_workouts: Mapped[list["PlannedWorkout"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_training_plans_user", "user_id"),)


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.id", ondelete="CASCADE"), index=True
    )
    week_number: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date, index=True)
    workout_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))
    target_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_pace_description: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id"), nullable=True
    )

    plan: Mapped["TrainingPlan"] = relationship(back_populates="planned_workouts")
    activity: Mapped["Activity | None"] = relationship("Activity")

    __table_args__ = (Index("ix_planned_workouts_plan_date", "plan_id", "date"),)
