"""Seed the shared exercise library

Revision ID: seed_exercise_library
Revises: add_app_mode
Create Date: 2026-09-28 00:00:00.000000

Until now the library started empty. The only entries were the ones the strength
migration backfilled from whatever `exercises` rows already existed — which on a
real install is close to nothing — so the first session in a new account meant
typing every movement's name before logging a single set. For an app whose whole
argument is "faster than a notes app", that is the wrong first five minutes.

Shared (`user_id IS NULL`), like everything else in this table: two people use
this install and a movement one of them adds has to be usable by the other.

**Idempotent by name, case-insensitively.** An install where someone already
added "Bench Press" keeps their row and does not gain a duplicate — the partial
unique index would reject it anyway, but failing a deploy over a name collision
would be a poor trade. Matching is done against every row regardless of owner,
because a personal entry and a shared one with the same name would both show in
the picker and look like a bug.

`muscle_group` is filled so the picker can label entries; it is free text and
not a taxonomy anyone has to agree with.

Warm-up and cool-down movements are included deliberately. `set_type` already
distinguishes a warm-up *set* of a working movement ("two light squats first"),
which is a different thing from a warm-up *exercise* ("ten minutes on the bike",
"band pull-aparts"). Both are things people log, and only the first existed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "seed_exercise_library"
down_revision: str | None = "add_app_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: (name, muscle_group). Ordered by group for readability; insert order does not
#: matter because the picker sorts by name.
LIBRARY: list[tuple[str, str]] = [
    # ── Warm-up and mobility ────────────────────────────────────────────────
    ("Treadmill Walk", "Warm-up"),
    ("Stationary Bike", "Warm-up"),
    ("Rowing Machine", "Warm-up"),
    ("Jump Rope", "Warm-up"),
    ("Arm Circles", "Warm-up"),
    ("Leg Swings", "Warm-up"),
    ("Band Pull-Apart", "Warm-up"),
    ("Shoulder Dislocates", "Warm-up"),
    ("Cat-Cow", "Warm-up"),
    ("Hip Circles", "Warm-up"),
    ("World's Greatest Stretch", "Warm-up"),
    ("Glute Bridge", "Warm-up"),
    ("Bodyweight Squat", "Warm-up"),
    # ── Chest ───────────────────────────────────────────────────────────────
    ("Barbell Bench Press", "Chest"),
    ("Incline Barbell Bench Press", "Chest"),
    ("Dumbbell Bench Press", "Chest"),
    ("Incline Dumbbell Press", "Chest"),
    ("Dumbbell Fly", "Chest"),
    ("Cable Fly", "Chest"),
    ("Chest Press Machine", "Chest"),
    ("Pec Deck", "Chest"),
    ("Push-Up", "Chest"),
    ("Dip", "Chest"),
    # ── Back ────────────────────────────────────────────────────────────────
    ("Deadlift", "Back"),
    ("Rack Pull", "Back"),
    ("Barbell Row", "Back"),
    ("Pendlay Row", "Back"),
    ("Dumbbell Row", "Back"),
    ("T-Bar Row", "Back"),
    ("Seated Cable Row", "Back"),
    ("Lat Pulldown", "Back"),
    ("Pull-Up", "Back"),
    ("Chin-Up", "Back"),
    ("Straight-Arm Pulldown", "Back"),
    ("Face Pull", "Back"),
    ("Back Extension", "Back"),
    # ── Shoulders ───────────────────────────────────────────────────────────
    ("Overhead Press", "Shoulders"),
    ("Seated Dumbbell Press", "Shoulders"),
    ("Arnold Press", "Shoulders"),
    ("Lateral Raise", "Shoulders"),
    ("Cable Lateral Raise", "Shoulders"),
    ("Front Raise", "Shoulders"),
    ("Rear Delt Fly", "Shoulders"),
    ("Upright Row", "Shoulders"),
    ("Barbell Shrug", "Shoulders"),
    # ── Legs ────────────────────────────────────────────────────────────────
    ("Back Squat", "Legs"),
    ("Front Squat", "Legs"),
    ("Goblet Squat", "Legs"),
    ("Hack Squat", "Legs"),
    ("Leg Press", "Legs"),
    ("Romanian Deadlift", "Legs"),
    ("Bulgarian Split Squat", "Legs"),
    ("Lunge", "Legs"),
    ("Walking Lunge", "Legs"),
    ("Step-Up", "Legs"),
    ("Leg Extension", "Legs"),
    ("Lying Leg Curl", "Legs"),
    ("Seated Leg Curl", "Legs"),
    ("Hip Thrust", "Legs"),
    ("Standing Calf Raise", "Legs"),
    ("Seated Calf Raise", "Legs"),
    # ── Arms ────────────────────────────────────────────────────────────────
    ("Barbell Curl", "Arms"),
    ("Dumbbell Curl", "Arms"),
    ("Hammer Curl", "Arms"),
    ("Preacher Curl", "Arms"),
    ("Cable Curl", "Arms"),
    ("Concentration Curl", "Arms"),
    ("Tricep Pushdown", "Arms"),
    ("Overhead Tricep Extension", "Arms"),
    ("Skull Crusher", "Arms"),
    ("Close-Grip Bench Press", "Arms"),
    ("Tricep Kickback", "Arms"),
    ("Wrist Curl", "Arms"),
    # ── Core ────────────────────────────────────────────────────────────────
    ("Plank", "Core"),
    ("Side Plank", "Core"),
    ("Hanging Leg Raise", "Core"),
    ("Cable Crunch", "Core"),
    ("Russian Twist", "Core"),
    ("Ab Wheel Rollout", "Core"),
    ("Dead Bug", "Core"),
    ("Bird Dog", "Core"),
    ("Mountain Climber", "Core"),
    ("Pallof Press", "Core"),
    # ── Cardio ──────────────────────────────────────────────────────────────
    ("Treadmill Run", "Cardio"),
    ("Elliptical", "Cardio"),
    ("Stair Climber", "Cardio"),
    ("Assault Bike", "Cardio"),
    ("Swim", "Cardio"),
    # ── Cool-down ───────────────────────────────────────────────────────────
    ("Hamstring Stretch", "Cool-down"),
    ("Quad Stretch", "Cool-down"),
    ("Couch Stretch", "Cool-down"),
    ("Chest Stretch", "Cool-down"),
    ("Child's Pose", "Cool-down"),
    ("Pigeon Pose", "Cool-down"),
    ("Foam Roll Quads", "Cool-down"),
    ("Foam Roll Upper Back", "Cool-down"),
    ("Foam Roll IT Band", "Cool-down"),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {
        str(row[0]).strip().lower()
        for row in bind.execute(sa.text("SELECT name FROM exercise_catalog"))
    }
    fresh = [(n, g) for n, g in LIBRARY if n.lower() not in existing]
    if not fresh:
        return
    bind.execute(
        sa.text(
            "INSERT INTO exercise_catalog "
            "(user_id, name, muscle_group, is_shared, is_archived) "
            "VALUES (NULL, :name, :grp, :t, :f)"
        ),
        [{"name": n, "grp": g, "t": True, "f": False} for n, g in fresh],
    )


def downgrade() -> None:
    """Remove seeded entries that nothing points at.

    A seeded row someone has since used is left alone: `exercises.catalog_id`
    and `routine_exercises.catalog_id` reference it, and deleting it would
    strand a logged session or a saved routine. That makes this asymmetric with
    upgrade() on purpose — a downgrade should not cost you history.

    Known and accepted: this matches on name, so it also removes an *unused*
    entry someone typed themselves that happens to share a name with the seed
    ("Barbell Bench Press", added by hand before this migration ran). There is
    no way to tell those apart after the fact — a migration keeps no record of
    which rows it inserted — and the loss is one unreferenced name on a
    rollback, which is a better trade than a downgrade that undoes nothing.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM exercise_catalog "
            "WHERE user_id IS NULL "
            "  AND name IN :names "
            "  AND id NOT IN (SELECT catalog_id FROM exercises WHERE catalog_id IS NOT NULL) "
            "  AND id NOT IN "
            "      (SELECT catalog_id FROM routine_exercises WHERE catalog_id IS NOT NULL)"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": [n for n, _ in LIBRARY]},
    )
