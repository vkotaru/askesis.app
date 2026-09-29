"""Give a movement a kind, and a set somewhere to put time and distance

Revision ID: add_exercise_tracking
Revises: seed_exercise_library
Create Date: 2026-09-29 00:00:00.000000

The logger asked every movement the same two questions — how much weight, how
many reps — because that is all a set could hold. So a plank was logged as
"0 kg x 10", a treadmill walk had nowhere to put the distance, and a stretch
was recorded as repetitions of nothing. The numbers were not merely ugly: a
volume total that counts a plank's imaginary reps is wrong, and there was no
way to correct any of it from the app.

Two changes, and they are separate on purpose:

* `exercise_catalog.tracking_type` says what a set of this movement IS —
  weight_reps, reps, time, or distance_time — and therefore which fields the
  logger shows. It lives on the movement, not the set, because it is a property
  of the exercise: a plank is timed whoever is doing it.
* `exercise_sets.duration_seconds` and `distance_m` are where the other kinds
  of set actually go. Nullable, like `weight_kg` and `reps` already are.

The backfill is by name against the seeded library, not by muscle group alone.
"Warm-up" holds both jump rope (timed) and band pull-aparts (reps), and getting
those wrong would be the same bug in a new place. Anything unrecognised keeps
the default, which is the behaviour it has today.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_exercise_tracking"
down_revision: str | None = "seed_exercise_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Movements whose set is a duration. Stretches, holds and skipping.
TIMED = [
    "Plank",
    "Side Plank",
    "Jump Rope",
    "World's Greatest Stretch",
    "Hamstring Stretch",
    "Quad Stretch",
    "Couch Stretch",
    "Chest Stretch",
    "Child's Pose",
    "Pigeon Pose",
    "Foam Roll Quads",
    "Foam Roll Upper Back",
    "Foam Roll IT Band",
]

#: Movements measured by how far and how long. Every machine in the cardio
#: section, plus the two warm-up entries that are the same machines.
DISTANCE_TIMED = [
    "Treadmill Walk",
    "Treadmill Run",
    "Stationary Bike",
    "Rowing Machine",
    "Elliptical",
    "Stair Climber",
    "Assault Bike",
    "Swim",
]

#: Bodyweight-only reps. Deliberately NOT pull-ups, dips, push-ups or hanging
#: leg raises — those get loaded, and `weight_reps` already shows a blank
#: weight as bodyweight.
REP_ONLY = [
    "Arm Circles",
    "Leg Swings",
    "Band Pull-Apart",
    "Shoulder Dislocates",
    "Cat-Cow",
    "Hip Circles",
    "Glute Bridge",
    "Bodyweight Squat",
    "Dead Bug",
    "Bird Dog",
    "Mountain Climber",
    "Russian Twist",
]


def _set_type(bind: sa.engine.Connection, names: list[str], kind: str) -> None:
    """Name-matched, case-insensitively, so a hand-typed "plank" is caught too."""
    bind.execute(
        sa.text(
            "UPDATE exercise_catalog SET tracking_type = :kind "
            "WHERE lower(name) IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"kind": kind, "names": [n.lower() for n in names]},
    )


def upgrade() -> None:
    # Plain ADD COLUMN, deliberately NOT batch_alter_table. Batch mode recreates
    # the table on SQLite, and doing that here left `alembic downgrade base`
    # failing six migrations later with "no such index: ix_exercises_catalog_id"
    # -- an index on a table this migration does not touch. Both engines support
    # ADD COLUMN with a server_default, and SQLite has supported DROP COLUMN
    # since 3.35, so neither direction needs the rewrite.
    #
    # The server_default is what makes a NOT NULL column safe on a table that
    # already has rows. It stays afterwards so an INSERT that omits the column
    # -- the MCP connector's, for one -- still lands a valid value.
    op.add_column(
        "exercise_catalog",
        sa.Column(
            "tracking_type",
            sa.String(16),
            nullable=False,
            server_default="weight_reps",
        ),
    )
    op.add_column(
        "exercise_sets", sa.Column("duration_seconds", sa.Integer(), nullable=True)
    )
    op.add_column("exercise_sets", sa.Column("distance_m", sa.Float(), nullable=True))

    bind = op.get_bind()
    _set_type(bind, TIMED, "time")
    _set_type(bind, DISTANCE_TIMED, "distance_time")
    _set_type(bind, REP_ONLY, "reps")


def downgrade() -> None:
    op.drop_column("exercise_sets", "distance_m")
    op.drop_column("exercise_sets", "duration_seconds")
    op.drop_column("exercise_catalog", "tracking_type")
