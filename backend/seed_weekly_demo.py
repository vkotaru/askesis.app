#!/usr/bin/env python3
"""Seed 2 weeks (current + previous) of demo data for visualizing the weekly dashboard.

Creates meals (with calories), daily_nutrition (protein/carbs/fat),
daily_logs (steps/sleep/water), and activities (with burned calories) for every
day of the current and previous ISO weeks (Mon-Sun). Existing rows are skipped.

Run:
    cd backend && python seed_weekly_demo.py
"""

import random
from datetime import date, timedelta

from app.database import SessionLocal, engine
from app.models import (
    Activity,
    ActivityType,
    Base,
    DailyLog,
    DailyNutrition,
    Meal,
    User,
)

Base.metadata.create_all(bind=engine)


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


MEAL_TEMPLATES = [
    ("Breakfast", "08:00", 380, "Oatmeal with berries and almonds"),
    ("Lunch", "12:30", 620, "Grilled chicken bowl with quinoa"),
    ("Snack", "15:30", 220, "Greek yogurt with honey"),
    ("Dinner", "19:00", 780, "Salmon, sweet potato, greens"),
]

CARDIO_ACTIVITIES = [
    ("Morning Run", 35, 360, 6.0),
    ("Cycling", 50, 520, 18.0),
    ("HIIT Session", 25, 310, None),
    ("Evening Walk", 40, 180, 3.5),
    ("Trail Hike", 75, 480, 7.0),
    ("Swim", 40, 330, None),
]


def seed():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            print("No user found. Log in to the app first so a user row exists.")
            return

        print(f"Seeding weekly demo data for: {user.email}")

        today = date.today()
        current_mon = monday_of(today)
        prev_mon = current_mon - timedelta(days=7)

        # Days of current + previous week (14 days total)
        days = [prev_mon + timedelta(days=i) for i in range(14)]

        created = {"logs": 0, "meals": 0, "nutrition": 0, "activities": 0}

        for d in days:
            # Daily log
            log_exists = (
                db.query(DailyLog)
                .filter(DailyLog.user_id == user.id, DailyLog.date == d)
                .first()
            )
            if not log_exists:
                db.add(
                    DailyLog(
                        user_id=user.id,
                        date=d,
                        weight=round(random.uniform(72, 74), 1),
                        sleep_hours=round(random.uniform(6.0, 8.0), 1),
                        steps=random.randint(5000, 14000),
                        water_ml=random.randint(1800, 2800),
                        feelings="energetic,focused",
                        caffeine_mg=random.choice([0, 80, 160]),
                        ate_outside=False,
                        notes="Seeded demo data",
                    )
                )
                created["logs"] += 1

            # Meals (3-4 per day for realistic calorie totals)
            num_meals = random.choice([3, 3, 4])
            picked = random.sample(MEAL_TEMPLATES, num_meals)
            for label, time_str, base_cal, desc in picked:
                exists = (
                    db.query(Meal)
                    .filter(
                        Meal.user_id == user.id,
                        Meal.date == d,
                        Meal.label == label,
                    )
                    .first()
                )
                if not exists:
                    db.add(
                        Meal(
                            user_id=user.id,
                            date=d,
                            label=label,
                            time=time_str,
                            calories=base_cal + random.randint(-80, 120),
                            description=desc,
                        )
                    )
                    created["meals"] += 1

            # Daily nutrition (protein/carbs/fat)
            nutrition_exists = (
                db.query(DailyNutrition)
                .filter(
                    DailyNutrition.user_id == user.id,
                    DailyNutrition.date == d,
                )
                .first()
            )
            if not nutrition_exists:
                db.add(
                    DailyNutrition(
                        user_id=user.id,
                        date=d,
                        protein_g=round(random.uniform(110, 180), 1),
                        carbs_g=round(random.uniform(180, 280), 1),
                        fat_g=round(random.uniform(50, 90), 1),
                        notes="Seeded demo data",
                    )
                )
                created["nutrition"] += 1

            # Activity — every day gets at least one cardio session with burned calories
            activity_exists = (
                db.query(Activity)
                .filter(
                    Activity.user_id == user.id,
                    Activity.date == d,
                    Activity.notes == "Seeded demo data",
                )
                .first()
            )
            if not activity_exists:
                name, dur, cal, dist = random.choice(CARDIO_ACTIVITIES)
                db.add(
                    Activity(
                        user_id=user.id,
                        date=d,
                        name=name,
                        activity_type=ActivityType.CARDIO,
                        duration_mins=dur + random.randint(-5, 10),
                        calories=cal + random.randint(-60, 80),
                        distance_km=dist,
                        tags="demo",
                        notes="Seeded demo data",
                    )
                )
                created["activities"] += 1

                # ~40% of days get a second shorter activity for variety in burn
                if random.random() < 0.4:
                    name2, dur2, cal2, dist2 = random.choice(CARDIO_ACTIVITIES)
                    db.add(
                        Activity(
                            user_id=user.id,
                            date=d,
                            name=f"{name2} (evening)",
                            activity_type=ActivityType.CARDIO,
                            duration_mins=max(15, dur2 // 2),
                            calories=max(80, cal2 // 2) + random.randint(-20, 40),
                            distance_km=dist2,
                            tags="demo",
                            notes="Seeded demo data",
                        )
                    )
                    created["activities"] += 1

        db.commit()

        print("\nSeed complete.")
        print(f"  Date range: {days[0]} → {days[-1]}")
        for k, v in created.items():
            print(f"  {k}: +{v}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
