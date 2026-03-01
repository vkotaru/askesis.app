#!/usr/bin/env python3
"""Seed demo data for Askesis app."""

import random
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, User, DailyLog, Meal, Activity, ActivityType, Exercise

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)


def seed_demo_data():
    db = SessionLocal()
    try:
        # Get the first user (dev user)
        user = db.query(User).first()
        if not user:
            print("No user found. Please log in first to create a user.")
            return

        print(f"Seeding data for user: {user.email}")

        # Generate data for the last 30 days
        today = date.today()

        feelings_options = [
            ["happy", "energetic"],
            ["calm", "focused"],
            ["tired"],
            ["motivated", "energetic"],
            ["happy", "grateful"],
            ["stressed", "tired"],
            ["meh"],
            ["happy", "calm"],
            ["focused", "motivated"],
            ["tired", "sore"],
        ]

        meal_labels = ["Breakfast", "Lunch", "Dinner", "Snack"]
        meal_descriptions = {
            "Breakfast": ["Oatmeal with berries", "Eggs and toast", "Smoothie bowl", "Greek yogurt with granola", "Avocado toast"],
            "Lunch": ["Chicken salad", "Grilled salmon with veggies", "Buddha bowl", "Turkey sandwich", "Quinoa bowl"],
            "Dinner": ["Pasta with marinara", "Stir fry with tofu", "Grilled chicken with rice", "Fish tacos", "Vegetable curry"],
            "Snack": ["Apple with peanut butter", "Protein bar", "Mixed nuts", "Hummus and veggies", "Greek yogurt"],
        }

        cardio_activities = [
            ("Morning Run", 30, 250, 5.0, ["Training"]),
            ("Cycling", 45, 400, 15.0, ["Commute"]),
            ("Swimming", 40, 350, None, ["Training"]),
            ("HIIT Session", 25, 300, None, ["Training"]),
            ("Evening Walk", 30, 150, 3.0, ["Fun"]),
            ("Trail Hike", 90, 500, 8.0, ["Weekend", "Fun"]),
        ]

        strength_exercises = {
            "Upper Body": [
                ("Bench Press", 4, "10,10,8,8", 60),
                ("Shoulder Press", 3, "12,10,10", 25),
                ("Lat Pulldown", 3, "12,12,10", 50),
                ("Bicep Curls", 3, "12,12,12", 15),
                ("Tricep Dips", 3, "15,12,10", None),
            ],
            "Lower Body": [
                ("Squats", 4, "10,10,8,8", 80),
                ("Deadlifts", 4, "8,8,6,6", 100),
                ("Leg Press", 3, "12,12,10", 120),
                ("Lunges", 3, "12,12,12", 20),
                ("Calf Raises", 3, "15,15,15", 40),
            ],
            "Core": [
                ("Planks", 3, "60s,60s,45s", None),
                ("Russian Twists", 3, "20,20,20", 10),
                ("Leg Raises", 3, "15,15,12", None),
                ("Crunches", 3, "20,20,20", None),
            ],
        }

        for day_offset in range(30, -1, -1):
            current_date = today - timedelta(days=day_offset)

            # Check if daily log already exists
            existing_log = db.query(DailyLog).filter(
                DailyLog.user_id == user.id,
                DailyLog.date == current_date
            ).first()

            if not existing_log:
                # Create daily log
                log = DailyLog(
                    user_id=user.id,
                    date=current_date,
                    weight=round(random.uniform(70, 75), 1),
                    sleep_hours=round(random.uniform(5.5, 8.5), 1),
                    steps=random.randint(3000, 15000),
                    water_ml=random.randint(1500, 3000),
                    feelings=",".join(random.choice(feelings_options)),
                    caffeine_mg=random.choice([0, 80, 160, 240, 320]),
                    ate_outside=random.random() > 0.7,
                    notes=random.choice([
                        None,
                        "Good day overall",
                        "Felt a bit tired in the afternoon",
                        "Great workout session!",
                        "Need more sleep",
                        "Productive day",
                    ]),
                )
                db.add(log)

            # Add meals (2-4 per day)
            num_meals = random.randint(2, 4)
            selected_meals = random.sample(meal_labels, num_meals)

            for meal_label in selected_meals:
                existing_meal = db.query(Meal).filter(
                    Meal.user_id == user.id,
                    Meal.date == current_date,
                    Meal.label == meal_label
                ).first()

                if not existing_meal:
                    meal = Meal(
                        user_id=user.id,
                        date=current_date,
                        label=meal_label,
                        time={"Breakfast": "08:00", "Lunch": "12:30", "Dinner": "19:00", "Snack": "15:00"}[meal_label],
                        calories=random.randint(200, 800),
                        description=random.choice(meal_descriptions[meal_label]),
                    )
                    db.add(meal)

            # Add activities (50% chance per day)
            if random.random() > 0.5:
                existing_activity = db.query(Activity).filter(
                    Activity.user_id == user.id,
                    Activity.date == current_date
                ).first()

                if not existing_activity:
                    # Decide cardio or strength
                    if random.random() > 0.4:
                        # Cardio
                        name, duration, calories, distance, tags = random.choice(cardio_activities)
                        activity = Activity(
                            user_id=user.id,
                            date=current_date,
                            name=name,
                            activity_type=ActivityType.CARDIO,
                            duration_mins=duration + random.randint(-5, 10),
                            calories=calories + random.randint(-50, 50),
                            distance_km=distance,
                            tags=",".join(tags),
                        )
                        db.add(activity)
                    else:
                        # Strength
                        workout_name = random.choice(list(strength_exercises.keys()))
                        activity = Activity(
                            user_id=user.id,
                            date=current_date,
                            name=workout_name,
                            activity_type=ActivityType.STRENGTH,
                            duration_mins=random.randint(40, 70),
                            calories=random.randint(200, 400),
                            tags="Training",
                        )
                        db.add(activity)
                        db.flush()  # Get the activity ID

                        # Add exercises
                        for ex_name, sets, reps, weight in strength_exercises[workout_name]:
                            exercise = Exercise(
                                activity_id=activity.id,
                                name=ex_name,
                                sets=sets,
                                reps=reps,
                                weight_kg=weight,
                            )
                            db.add(exercise)

        db.commit()
        print("Demo data seeded successfully!")

        # Print summary
        log_count = db.query(DailyLog).filter(DailyLog.user_id == user.id).count()
        meal_count = db.query(Meal).filter(Meal.user_id == user.id).count()
        activity_count = db.query(Activity).filter(Activity.user_id == user.id).count()

        print(f"\nSummary:")
        print(f"  Daily logs: {log_count}")
        print(f"  Meals: {meal_count}")
        print(f"  Activities: {activity_count}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
