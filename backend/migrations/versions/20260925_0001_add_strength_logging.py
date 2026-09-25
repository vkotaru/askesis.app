"""Add the shared exercise catalogue and per-set logging

Revision ID: add_strength_logging
Revises: add_mcp_oauth_tables
Create Date: 2026-09-25 00:00:00.000000

Strength sessions previously stored one row per exercise with `sets` as a count,
`reps` as a comma-joined String ("10,10,8"), and a single `weight_kg` for the
whole movement -- so 3x5@100 followed by 1x3@110 had no representation at all.
This adds real per-set rows, and a movement catalogue to hang a video link and
form notes off.

**The catalogue is shared across the install**, with a nullable `user_id` where
NULL means "the household's, not a person's". That is `food_items`' shape, not a
new idea: two people use this app and an exercise one of them adds must be
usable by the other.

**The backfill is the risky part.** Existing rows are parsed into real sets:
`sets=4, reps="10,10,8,8", weight_kg=60` becomes four rows at 60kg. Rep values
that are not integers -- the seeder writes "60s,60s,45s" for planks -- cannot
become an integer rep count, so they are preserved in the exercise's note rather
than silently dropped. The legacy columns are left in place, both so a row that
did not parse is still readable and so `downgrade()` has somewhere to put the
strings back.

Reversible, and CI runs `upgrade head` then `downgrade base`. But note that
downgrade is lossy in practice: a session logged natively with per-set weights
collapses to a single `weight_kg`, because that is all the old shape can hold.
Take a database backup before deploying this.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "add_strength_logging"
down_revision: str | None = "add_mcp_oauth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercise_catalog",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Nullable on purpose: NULL == shared with everyone on this install.
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("muscle_group", sa.String(50), nullable=True),
        sa.Column("video_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "name", name="uq_exercise_catalog_user_name"),
    )
    op.create_index("ix_exercise_catalog_name", "exercise_catalog", ["name"])
    # The UniqueConstraint above cannot stop two shared rows sharing a name: SQL
    # treats NULLs as distinct, so (NULL, 'Squat') twice is permitted. For a
    # library both people write into, duplicates are the obvious failure -- so
    # the shared half gets a partial unique index of its own.
    #
    # On lower(name), not name: the API looks entries up case-insensitively, so
    # a case-sensitive index would let "Squat" and "squat" both exist and then
    # the lookup would match two rows and raise. The index has to enforce the
    # same notion of "the same exercise" the API uses, or the two disagree and
    # the disagreement is a 500.
    op.create_index(
        "uq_exercise_catalog_shared_name",
        "exercise_catalog",
        [sa.text("lower(name)")],
        unique=True,
        sqlite_where=sa.text("user_id IS NULL"),
        postgresql_where=sa.text("user_id IS NULL"),
    )

    op.create_table(
        "exercise_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("set_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        # String, not Enum: SQLAlchemy's Enum persists the member NAME, which has
        # already produced one silent mismatch in this codebase.
        sa.Column("set_type", sa.String(10), nullable=False, server_default="working"),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
    )
    op.create_index("ix_exercise_sets_exercise_id", "exercise_sets", ["exercise_id"])

    # SQLite cannot ALTER a table to add a constraint, so every change to
    # `exercises` goes through one batch block. `activity_id` gains the index it
    # never had; `catalog_id` and `position` are new.
    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("catalog_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("position", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_foreign_key(
            "fk_exercises_catalog_id", "exercise_catalog", ["catalog_id"], ["id"]
        )
    op.create_index("ix_exercises_activity_id", "exercises", ["activity_id"])
    op.create_index("ix_exercises_catalog_id", "exercises", ["catalog_id"])

    _backfill()


#: Marker downgrade() reads back, so an unparseable rep value survives the round
#: trip instead of being readable only by a human.
_IMPORTED_REPS_PREFIX = "Imported reps: "


def _backfill() -> None:
    """Turn the legacy string form into catalogue entries and real set rows."""
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            "SELECT id, activity_id, name, sets, reps, weight_kg, notes FROM exercises "
            "ORDER BY activity_id, id"
        )
    ).fetchall()
    if not rows:
        return

    # One shared catalogue entry per distinct name. Shared (user_id NULL) rather
    # than attributed: the movement itself belongs to nobody, and guessing an
    # owner from whoever logged it first would make it invisible to the other
    # account.
    # Insert every distinct name, then read the ids back in one query.
    #
    # NOT `result.lastrowid`: psycopg2 returns **0** for a table with no OIDs
    # rather than None, so a `lastrowid or fallback` idiom silently yields
    # catalog_id=0 on Postgres and the very next UPDATE dies on a foreign key
    # violation -- taking the whole migration, and the container's boot, with it.
    # SQLite hides this completely, which is why it survived testing.
    #
    # Names are matched case-insensitively so "Bench Press" and "bench press"
    # collapse to one movement instead of splitting a person's history in two.
    by_lower: dict[str, str] = {}
    for r in rows:
        name = (r.name or "").strip()
        if name:
            by_lower.setdefault(name.lower(), name)

    for name in sorted(by_lower.values()):
        bind.execute(
            sa.text(
                "INSERT INTO exercise_catalog (user_id, name, is_shared, is_archived) "
                "VALUES (NULL, :name, :t, :f)"
            ),
            {"name": name, "t": True, "f": False},
        )

    catalog_ids: dict[str, int] = {
        str(row.name).lower(): int(row.id)
        for row in bind.execute(
            sa.text("SELECT id, name FROM exercise_catalog WHERE user_id IS NULL")
        )
    }

    position_by_activity: dict[int, int] = {}
    for row in rows:
        name = (row.name or "").strip().lower()
        if name and name in catalog_ids:
            bind.execute(
                sa.text("UPDATE exercises SET catalog_id = :c WHERE id = :i"),
                {"c": catalog_ids[name], "i": row.id},
            )

        # Preserve the order the rows already had, per activity. activity_id
        # comes from the driving SELECT rather than a query per row.
        pos = position_by_activity.get(row.activity_id, 0)
        position_by_activity[row.activity_id] = pos + 1
        bind.execute(
            sa.text("UPDATE exercises SET position = :p WHERE id = :i"),
            {"p": pos, "i": row.id},
        )

        reps_raw = (row.reps or "").strip()
        parts = (
            [p.strip() for p in reps_raw.split(",") if p.strip()] if reps_raw else []
        )

        # A rep value like "60s" is a duration, not a count. Keep the original
        # text on the exercise note rather than inventing a number for it.
        unparsed = [p for p in parts if not p.isdigit()]
        if unparsed:
            keep = f"{_IMPORTED_REPS_PREFIX}{reps_raw}"
            note = (row.notes or "").strip()
            merged = f"{note}\n{keep}" if note else keep
            bind.execute(
                sa.text("UPDATE exercises SET notes = :n WHERE id = :i"),
                {"n": merged[:2000], "i": row.id},
            )

        numeric = [int(p) for p in parts if p.isdigit()]
        if not numeric and row.sets:
            # A count with no usable rep string still describes N sets.
            numeric = [None] * int(row.sets)  # type: ignore[list-item]

        for index, reps in enumerate(numeric, start=1):
            bind.execute(
                sa.text(
                    "INSERT INTO exercise_sets "
                    "(exercise_id, set_number, weight_kg, reps, set_type) "
                    "VALUES (:e, :n, :w, :r, 'working')"
                ),
                {"e": row.id, "n": index, "w": row.weight_kg, "r": reps},
            )


def downgrade() -> None:
    """Fold sets back into the legacy string columns, then drop the new tables.

    Lossy where a session used per-set weights: the old shape holds one weight
    per exercise, so the heaviest is kept and the rest are lost. Nothing can be
    done about that -- it is the reason the new tables exist.
    """
    bind = op.get_bind()

    # What upgrade() parked on the note when a rep value was not a number, so
    # this can put it back. Without it a "60s" hold upgrades to blank sets and
    # downgrades to `reps = NULL`: the number is unrecoverable, the note says
    # what it was, and the two halves of the round trip disagree.
    notes_by_exercise = {
        int(r.id): (r.notes or "")
        for r in bind.execute(sa.text("SELECT id, notes FROM exercises"))
    }

    grouped = bind.execute(
        sa.text(
            "SELECT exercise_id, COUNT(*) AS n, MAX(weight_kg) AS w "
            "FROM exercise_sets GROUP BY exercise_id"
        )
    ).fetchall()
    for row in grouped:
        reps = bind.execute(
            sa.text(
                "SELECT reps FROM exercise_sets WHERE exercise_id = :e "
                "ORDER BY set_number"
            ),
            {"e": row.exercise_id},
        ).fetchall()
        joined = ",".join(str(r.reps) for r in reps if r.reps is not None)

        note = notes_by_exercise.get(int(row.exercise_id), "")
        recovered = None
        for line in note.splitlines():
            if line.startswith(_IMPORTED_REPS_PREFIX):
                recovered = line[len(_IMPORTED_REPS_PREFIX) :].strip()
        if recovered:
            joined = recovered
            remainder = "\n".join(
                line
                for line in note.splitlines()
                if not line.startswith(_IMPORTED_REPS_PREFIX)
            ).strip()
            bind.execute(
                sa.text("UPDATE exercises SET notes = :n WHERE id = :i"),
                {"n": remainder or None, "i": row.exercise_id},
            )

        bind.execute(
            sa.text(
                "UPDATE exercises SET sets = :s, reps = :r, weight_kg = :w "
                "WHERE id = :i"
            ),
            {
                "s": row.n,
                "r": joined[:50] or None,
                "w": row.w,
                "i": row.exercise_id,
            },
        )

    op.drop_index("ix_exercises_catalog_id", table_name="exercises")
    op.drop_index("ix_exercises_activity_id", table_name="exercises")
    with op.batch_alter_table("exercises") as batch:
        batch.drop_constraint("fk_exercises_catalog_id", type_="foreignkey")
        batch.drop_column("position")
        batch.drop_column("catalog_id")

    op.drop_index("ix_exercise_sets_exercise_id", table_name="exercise_sets")
    op.drop_table("exercise_sets")
    op.drop_index("uq_exercise_catalog_shared_name", table_name="exercise_catalog")
    op.drop_index("ix_exercise_catalog_name", table_name="exercise_catalog")
    op.drop_table("exercise_catalog")
