#!/usr/bin/env python3
"""
Seed common food items into the database.

Usage:
    python seed_foods.py
"""

from app.database import SessionLocal, engine, Base
from seed_data import seed_foods

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    seed_foods(db)
finally:
    db.close()
