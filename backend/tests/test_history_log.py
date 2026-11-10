"""The connector's history writes: a weight in either unit, a session with or
without numbers. Pounds come in here and nowhere else; kilograms go out."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app import history_log
from app.models import ExerciseSet, User

DAY = date(2026, 11, 10)


def test_body_weight_in_pounds_is_stored_in_kilograms(db: Session, user: User):
    r = history_log.log_weight(db, user.id, DAY, weight_lb=180)
    assert r["weight_kg"] == 81.65
    r = history_log.log_weight(db, user.id, DAY, weight_kg=81.6)
    assert (r["before_kg"], r["weight_kg"]) == (81.65, 81.6)


@pytest.mark.parametrize(
    "kwargs, said",
    [
        ({}, "weight_kg or weight_lb"),
        ({"weight_kg": 80, "weight_lb": 180}, "not both"),
        ({"weight_lb": "180"}, "must be a number"),
        ({"weight_lb": True}, "must be a number"),
        ({"weight_lb": 1200}, "1200 lb is outside"),
        ({"weight_kg": 650}, "650.0 kg is outside"),
    ],
)
def test_body_weight_refusals(db: Session, user: User, kwargs, said):
    with pytest.raises(history_log.HistoryError, match=said):
        history_log.log_weight(db, user.id, DAY, **kwargs)


def test_set_weight_in_either_unit(db: Session, user: User):
    r = history_log.log_workout(
        db,
        user.id,
        DAY,
        "Lift",
        exercises=[
            {
                "name": "Bench",
                "sets": [{"weight_lb": 135, "reps": 5}, {"weight_kg": 60, "reps": 5}],
            }
        ],
    )
    assert r["exercises"] == [{"name": "Bench", "sets": 2, "in_library": False}]
    stored = [(s.weight_kg, s.reps) for s in db.query(ExerciseSet).all()]
    assert stored == [(61.235, 5), (60.0, 5)]


def test_a_movement_needs_no_numbers(db: Session, user: User):
    """Not remembering the numbers is not a reason to lose the session."""
    r = history_log.log_workout(
        db,
        user.id,
        DAY,
        "Lift",
        exercises=[
            {"name": "Squat"},
            {"name": "Pull-ups", "sets": [{"reps": 8}]},
            {"name": "Push-ups", "sets": [{"weight_kg": 0, "reps": 20}]},
        ],
    )
    assert [e["sets"] for e in r["exercises"]] == [0, 1, 1]


@pytest.mark.parametrize(
    "sets, said",
    [
        ([{}], "leave `sets` out"),
        ([{"weight_kg": None, "reps": None}], "leave `sets` out"),
        ([{"weight_lb": 135, "weight_kg": 61}], "not both"),
        ([{"weight_lb": 3000}], "between 0 and 2204.6"),
        ([{"weight_lb": "135"}], "must be a number"),
    ],
)
def test_set_refusals(db: Session, user: User, sets, said):
    with pytest.raises(history_log.HistoryError, match=said):
        history_log.log_workout(
            db, user.id, DAY, "Lift", exercises=[{"name": "x", "sets": sets}]
        )
