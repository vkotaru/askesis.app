#!/usr/bin/env python3
"""
Seed script for local development.
Creates dummy users with sample data for testing.

Usage:
    python seed_data.py
"""

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    User,
    UserSettings,
    DailyLog,
    Meal,
    DailyNutrition,
    Activity,
    ActivityType,
    TimeOfDay,
    BodyMeasurement,
    DataShare,
    FoodItem,
)


def create_users(db: Session) -> tuple[User, User]:
    """Create two dummy users for testing."""

    # Check if users already exist
    existing = (
        db.query(User)
        .filter(User.email.in_(["dev@askesis.local", "partner@askesis.local"]))
        .all()
    )

    if len(existing) == 2:
        print("Users already exist, skipping creation")
        return tuple(existing)

    # User 1: Main dev user (matches DEV_MODE auth email)
    user1 = db.query(User).filter(User.email == "dev@askesis.local").first()
    if not user1:
        user1 = User(
            email="dev@askesis.local",
            name="Dev User",
            picture=None,
        )
        db.add(user1)

    # User 2: Partner/spouse for shared dashboard testing
    user2 = db.query(User).filter(User.email == "partner@askesis.local").first()
    if not user2:
        user2 = User(
            email="partner@askesis.local",
            name="Partner User",
            picture=None,
        )
        db.add(user2)

    db.commit()
    db.refresh(user1)
    db.refresh(user2)

    # Create settings for both users (if not exists)
    if not db.query(UserSettings).filter(UserSettings.user_id == user1.id).first():
        settings1 = UserSettings(
            user_id=user1.id,
            theme="system",
            font_size="medium",
            font_family="space-grotesk",
            content_width="medium",
            color_scheme="forest",
            distance_unit="mi",
            measurement_unit="in",
            weight_unit="lb",
            water_unit="oz",
        )
        db.add(settings1)

    if not db.query(UserSettings).filter(UserSettings.user_id == user2.id).first():
        settings2 = UserSettings(
            user_id=user2.id,
            theme="system",
            font_size="medium",
            font_family="space-grotesk",
            content_width="medium",
            color_scheme="ocean",
            distance_unit="mi",
            measurement_unit="in",
            weight_unit="lb",
            water_unit="oz",
        )
        db.add(settings2)

    # Create bidirectional data sharing between users (if not exists)
    if (
        not db.query(DataShare)
        .filter(DataShare.owner_id == user1.id, DataShare.shared_with_id == user2.id)
        .first()
    ):
        share1 = DataShare(
            owner_id=user1.id,
            shared_with_id=user2.id,
            categories='["daily_logs", "nutrition", "activities", "measurements", "photos"]',
        )
        db.add(share1)

    if (
        not db.query(DataShare)
        .filter(DataShare.owner_id == user2.id, DataShare.shared_with_id == user1.id)
        .first()
    ):
        share2 = DataShare(
            owner_id=user2.id,
            shared_with_id=user1.id,
            categories='["daily_logs", "nutrition", "activities", "measurements", "photos"]',
        )
        db.add(share2)

    db.commit()
    print(f"Users ready: {user1.name} (id={user1.id}), {user2.name} (id={user2.id})")
    print("Bidirectional data sharing configured")

    return user1, user2


def seed_daily_logs(db: Session, user: User, days: int = 60):
    """Create sample daily logs for the past N days."""

    # Check if logs already exist
    existing = db.query(DailyLog).filter(DailyLog.user_id == user.id).count()
    if existing > 0:
        print(f"  Daily logs already exist for {user.name}, skipping")
        return

    today = date.today()
    base_weight = (
        random.uniform(150, 180)
        if user.email == "dev@askesis.local"
        else random.uniform(130, 150)
    )

    feelings_options = [
        "energetic",
        "tired",
        "focused",
        "stressed",
        "happy",
        "calm",
        "anxious",
    ]

    for i in range(days):
        log_date = today - timedelta(days=i)

        # Skip some days randomly (80% chance of having a log)
        if random.random() > 0.8:
            continue

        # Weight with slight variation and trend
        weight_trend = -0.05 * (days - i) / days  # Slight downward trend
        weight = base_weight + weight_trend + random.uniform(-0.5, 0.5)

        log = DailyLog(
            user_id=user.id,
            date=log_date,
            weight=round(weight / 2.20462, 2),  # Store in kg
            sleep_hours=round(random.uniform(5.5, 8.5), 1),
            steps=random.randint(3000, 15000) if random.random() > 0.3 else None,
            water_ml=random.randint(1500, 3500) if random.random() > 0.2 else None,
            feelings=",".join(random.sample(feelings_options, random.randint(1, 3))),
            caffeine_mg=random.choice([0, 100, 200, 300])
            if random.random() > 0.4
            else None,
            ate_outside=random.random() > 0.7,
            notes=random.choice(
                [None, "Good day", "Felt tired", "Great workout", "Rest day"]
            ),
        )
        db.add(log)

    db.commit()
    print(f"  Created daily logs for {user.name}")


def seed_meals(db: Session, user: User, days: int = 30):
    """Create sample meals for the past N days."""

    existing = db.query(Meal).filter(Meal.user_id == user.id).count()
    if existing > 0:
        print(f"  Meals already exist for {user.name}, skipping")
        return

    today = date.today()

    meal_templates = [
        ("Breakfast", "08:00", 400, "Oatmeal with berries and coffee"),
        ("Breakfast", "08:30", 500, "Eggs, toast, and avocado"),
        ("Breakfast", "09:00", 350, "Greek yogurt with granola"),
        ("Lunch", "12:30", 600, "Chicken salad with quinoa"),
        ("Lunch", "13:00", 700, "Turkey sandwich and soup"),
        ("Lunch", "12:00", 550, "Buddha bowl with tofu"),
        ("Dinner", "18:30", 800, "Grilled salmon with vegetables"),
        ("Dinner", "19:00", 750, "Pasta with meat sauce"),
        ("Dinner", "18:00", 650, "Stir fry with rice"),
        ("Snack", "15:00", 200, "Protein bar"),
        ("Snack", "10:30", 150, "Apple with peanut butter"),
    ]

    for i in range(days):
        meal_date = today - timedelta(days=i)

        # 2-4 meals per day
        num_meals = random.randint(2, 4)
        daily_meals = random.sample(meal_templates, num_meals)

        for label, time, calories, description in daily_meals:
            meal = Meal(
                user_id=user.id,
                date=meal_date,
                label=label,
                time=time,
                calories=calories + random.randint(-50, 50),
                description=description,
            )
            db.add(meal)

    db.commit()
    print(f"  Created meals for {user.name}")


def seed_nutrition(db: Session, user: User, days: int = 30):
    """Create sample daily nutrition for the past N days."""

    existing = (
        db.query(DailyNutrition).filter(DailyNutrition.user_id == user.id).count()
    )
    if existing > 0:
        print(f"  Nutrition already exists for {user.name}, skipping")
        return

    today = date.today()

    for i in range(days):
        nutr_date = today - timedelta(days=i)

        # Skip some days
        if random.random() > 0.7:
            continue

        nutrition = DailyNutrition(
            user_id=user.id,
            date=nutr_date,
            protein_g=random.randint(80, 180),
            carbs_g=random.randint(150, 300),
            fat_g=random.randint(50, 100),
        )
        db.add(nutrition)

    db.commit()
    print(f"  Created nutrition data for {user.name}")


def seed_activities(db: Session, user: User, days: int = 60):
    """Create sample activities for the past N days."""

    existing = db.query(Activity).filter(Activity.user_id == user.id).count()
    if existing > 0:
        print(f"  Activities already exist for {user.name}, skipping")
        return

    today = date.today()

    cardio_templates = [
        ("Morning Run", 30, 5.0, "footprints", ["Training"]),
        ("Evening Run", 45, 7.5, "footprints", ["Training"]),
        ("Cycling", 60, 20.0, "bike", ["Commute"]),
        ("Bike Ride", 90, 30.0, "bike", ["Weekend", "Fun"]),
        ("Walking", 30, 2.5, "footprints", ["Recovery"]),
        ("HIIT Session", 25, None, "flame", ["Training"]),
        ("Swimming", 45, 1.5, "waves", ["Training"]),
    ]

    strength_templates = [
        ("Upper Body", 45, "dumbbell", ["Training"]),
        ("Lower Body", 50, "dumbbell", ["Training"]),
        ("Full Body", 60, "dumbbell", ["Training"]),
        ("Core Workout", 20, "dumbbell", ["Training"]),
        ("Leg Day", 55, "dumbbell", ["Training"]),
        ("Push Day", 45, "dumbbell", ["Training"]),
        ("Pull Day", 45, "dumbbell", ["Training"]),
    ]

    time_of_day_options = [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING]

    for i in range(days):
        activity_date = today - timedelta(days=i)

        # 0-2 activities per day (average ~0.7)
        if random.random() > 0.5:
            continue

        num_activities = random.randint(1, 2) if random.random() > 0.7 else 1

        for _ in range(num_activities):
            if random.random() > 0.4:  # 60% cardio
                name, duration, distance, icon, tags = random.choice(cardio_templates)
                activity = Activity(
                    user_id=user.id,
                    date=activity_date,
                    name=name,
                    activity_type=ActivityType.CARDIO,
                    time_of_day=random.choice(time_of_day_options),
                    duration_mins=duration + random.randint(-5, 10),
                    calories=random.randint(200, 500),
                    distance_km=distance if distance else None,
                    icon=icon,
                    tags=",".join(tags),
                )
            else:  # 40% strength
                name, duration, icon, tags = random.choice(strength_templates)
                activity = Activity(
                    user_id=user.id,
                    date=activity_date,
                    name=name,
                    activity_type=ActivityType.STRENGTH,
                    time_of_day=random.choice(time_of_day_options),
                    duration_mins=duration + random.randint(-5, 10),
                    calories=random.randint(150, 350),
                    icon=icon,
                    tags=",".join(tags),
                )
            db.add(activity)

    db.commit()
    print(f"  Created activities for {user.name}")


def seed_measurements(db: Session, user: User, weeks: int = 8):
    """Create sample body measurements (weekly)."""

    existing = (
        db.query(BodyMeasurement).filter(BodyMeasurement.user_id == user.id).count()
    )
    if existing > 0:
        print(f"  Measurements already exist for {user.name}, skipping")
        return

    today = date.today()

    # Base measurements (in cm)
    if user.email == "dev@askesis.local":
        base = {"waist": 86, "chest": 102, "bicep": 35, "thigh": 58}
    else:
        base = {"waist": 70, "chest": 90, "bicep": 28, "thigh": 52}

    for i in range(weeks):
        measure_date = today - timedelta(weeks=i)

        # Slight improvement trend
        trend = -0.2 * (weeks - i) / weeks

        measurement = BodyMeasurement(
            user_id=user.id,
            date=measure_date,
            waist=base["waist"] + trend + random.uniform(-0.5, 0.5),
            chest=base["chest"] + random.uniform(-0.3, 0.3),
            bicep_left=base["bicep"] + random.uniform(-0.2, 0.2),
            bicep_right=base["bicep"] + random.uniform(-0.2, 0.2),
            thigh_left=base["thigh"] + random.uniform(-0.3, 0.3),
            thigh_right=base["thigh"] + random.uniform(-0.3, 0.3),
        )
        db.add(measurement)

    db.commit()
    print(f"  Created measurements for {user.name}")


def seed_foods(db: Session):
    """Seed common food items from common_foods.json."""
    import json
    import os

    # Skip if foods already exist
    if db.query(FoodItem).first():
        print("  Food items already seeded, skipping.")
        return

    json_path = os.path.join(os.path.dirname(__file__), "common_foods.json")
    with open(json_path) as f:
        foods = json.load(f)

    for item in foods:
        food = FoodItem(
            user_id=None,  # system/seed item
            name=item["name"],
            brand=item.get("brand"),
            category=item.get("category"),
            serving_size=item.get("serving_size", 1.0),
            serving_unit=item.get("serving_unit", "g"),
            calories=item.get("calories"),
            protein_g=item.get("protein_g"),
            carbs_g=item.get("carbs_g"),
            fat_g=item.get("fat_g"),
            fiber_g=item.get("fiber_g"),
            is_shared=True,
            source="seed",
        )
        db.add(food)

    db.commit()
    print(f"  Seeded {len(foods)} food items from common_foods.json")


def main():
    """Main entry point."""
    print("=" * 50)
    print("Seeding database with dummy data...")
    print("=" * 50)

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Create users
        user1, user2 = create_users(db)

        # Seed data for each user
        for user in [user1, user2]:
            print(f"\nSeeding data for {user.name}:")
            seed_daily_logs(db, user)
            seed_meals(db, user)
            seed_nutrition(db, user)
            seed_activities(db, user)
            seed_measurements(db, user)

        seed_foods(db)

        print("\n" + "=" * 50)
        print("Seeding complete!")
        print("=" * 50)
        print("\nDummy users created:")
        print(f"  - dev@askesis.local (id={user1.id})")
        print(f"  - partner@askesis.local (id={user2.id})")
        print("\nBoth users share all data with each other.")
        print("\nTo login as dev user in DEV_MODE, the app will auto-login")
        print("or you can manually set the session.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
