#!/usr/bin/env python3
"""Every MCP write path, checked in one run.

The MCP connector is the only part of Askesis that faces the public internet,
and this is the change that let it write. There is no test suite, so this is the
harness: it calls the tool functions directly against a real database, exactly
as `mcp_server/server.py` does, and asserts both what they should do and what
they must refuse.

    cd backend
    rm -f /tmp/mcpw.db
    DEV_MODE=true SECRET_KEY=x DATABASE_URL="sqlite:////tmp/mcpw.db" \\
      python -m alembic upgrade head
    DEV_MODE=true SECRET_KEY=x DATABASE_URL="sqlite:////tmp/mcpw.db" \\
      python scripts/check_mcp_writes.py

Exits non-zero on any failure. Point it at a throwaway database.

The cases that matter most are not the happy paths. They are:
  * ownership  -- one account cannot read or change another's routines
  * refusal    -- bad input is rejected rather than half-written
  * isolation  -- the tools cannot reach logged history at all

The scope gate and the commit live in `server.py`, not in the tools, so they are
asserted here by inspection of `WRITE_TOOLS` rather than by calling them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models import ExerciseCatalog, User, WorkoutTemplate  # noqa: E402
from mcp_server import tools as T  # noqa: E402

fails: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    if not ok:
        fails.append(label)
    shown = repr(got)
    if len(shown) > 34:
        shown = shown[:31] + "..."
    print(f"  {'OK  ' if ok else 'FAIL'} {label:<52} {shown:>34}")


def refuses(label: str, fn, *args, **kwargs) -> None:
    """The tool must raise ToolError — a message a model can act on."""
    try:
        fn(*args, **kwargs)
    except T.ToolError:
        check(label, "refused", "refused")
        return
    except Exception as exc:  # noqa: BLE001
        fails.append(label)
        print(f"  FAIL {label:<52} {type(exc).__name__} (want ToolError)")
        return
    fails.append(label)
    print(f"  FAIL {label:<52} {'accepted (want refusal)':>34}")


def main() -> int:
    db = SessionLocal()

    # Two accounts, because the interesting assertions are about the boundary
    # between them: the exercise library is shared, routines are not.
    alice = db.query(User).filter(User.username == "alice").one_or_none()
    if alice is None:
        alice = User(email="a@x", username="alice", name="Alice")
        bob = User(email="b@x", username="bob", name="Bob")
        db.add_all([alice, bob])
        db.commit()
    bob = db.query(User).filter(User.username == "bob").one()
    a, b = alice.id, bob.id

    print("── the exercise library (shared) ──")
    r = T.create_exercise(db, a, "Zercher Squat", muscle_group="Legs")
    db.commit()
    check("create", (r["created"], r["name"]), (True, "Zercher Squat"))
    check("  is shared with the household", r["shared_with_household"], True)
    check(
        "  visible to the other account",
        any(
            e["name"] == "Zercher Squat"
            for e in T.list_exercises(db, b, "zercher")["exercises"]
        ),
        True,
    )
    refuses("duplicate is refused", T.create_exercise, db, a, "Zercher Squat")
    refuses("  case-insensitively", T.create_exercise, db, b, "zercher squat")
    refuses("blank name is refused", T.create_exercise, db, a, "   ")

    print()
    print("── video links ──")
    refuses(
        "javascript: is refused",
        T.create_exercise,
        db,
        a,
        "Bad Link",
        video_url="javascript:alert(1)",
    )
    r = T.update_exercise(db, a, "Zercher Squat", video_url="HTTPS://youtu.be/abc")
    db.commit()
    check("upper-case HTTPS accepted", r["video_url"], "HTTPS://youtu.be/abc")
    check("  muscle_group untouched by that edit", r["muscle_group"], "Legs")
    r = T.update_exercise(db, a, "Zercher Squat", notes="brace hard")
    db.commit()
    check(
        "  and the link survives a later edit", r["video_url"], "HTTPS://youtu.be/abc"
    )

    print()
    print("── archive and revive ──")
    T.archive_exercise(db, a, "Zercher Squat")
    db.commit()
    check(
        "archived leaves the picker",
        any(e["name"] == "Zercher Squat" for e in T.list_exercises(db, a)["exercises"]),
        False,
    )
    r = T.create_exercise(db, a, "Zercher Squat")
    db.commit()
    check("re-adding revives rather than duplicating", r["restored_from_archive"], True)
    check(
        "  exactly one row exists",
        db.query(ExerciseCatalog)
        .filter(ExerciseCatalog.name.ilike("zercher squat"))
        .count(),
        1,
    )
    refuses("archiving something unknown is refused", T.archive_exercise, db, a, "Nope")

    print()
    print("── routines (per account) ──")
    T.create_exercise(db, a, "Overhead Press A")
    db.commit()
    r = T.save_routine(
        db,
        a,
        "Push A",
        exercises=[{"name": "Overhead Press A", "target_sets": 3, "target_reps": 5}],
        default_duration_mins=55,
    )
    db.commit()
    check("create with one movement", len(r["exercises"]), 1)
    check("  target carried", r["exercises"][0]["target_sets"], 3)

    r = T.save_routine(db, a, "Push A", default_duration_mins=60)
    db.commit()
    check("omitting exercises leaves them alone", len(r["exercises"]), 1)
    check("  while other fields change", r["default_duration_mins"], 60)

    r = T.save_routine(db, a, "Push A", exercises=[])
    db.commit()
    check("an explicit empty list clears them", len(r["exercises"]), 0)

    refuses(
        "a movement not in the library is refused",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises=[{"name": "Nonexistent Lift"}],
    )
    refuses(
        "a movement with no name is refused",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises=[{"target_sets": 3}],
    )
    refuses(
        "an out-of-range target is refused",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises=[{"name": "Overhead Press A", "target_reps": 99999}],
    )

    print()
    print("── ownership ──")
    check("the other account sees no routines", T.list_routines(db, b)["count"], 0)
    T.save_routine(db, b, "Push A", exercises=[{"name": "Overhead Press A"}])
    db.commit()
    check("  and its own routine is separate", T.list_routines(db, b)["count"], 1)
    check("  mine is unaffected", T.list_routines(db, a)["count"], 1)
    check(
        "  two rows, one per account",
        db.query(WorkoutTemplate).filter(WorkoutTemplate.name == "Push A").count(),
        2,
    )

    print()
    print("── targets ──")
    r = T.set_targets(db, a, step_target=8000, protein_target=150)
    db.commit()
    check(
        "set two",
        (r["targets"]["step_target"], r["targets"]["protein_target"]),
        (8000, 150),
    )
    r = T.set_targets(db, a, calorie_target=2200)
    db.commit()
    check("setting a third leaves the others", r["targets"]["step_target"], 8000)
    r = T.set_targets(db, a, clear=["protein_target"])
    db.commit()
    check("clear removes just that one", r["targets"]["protein_target"], None)
    check("  and the rest survive", r["targets"]["calorie_target"], 2200)
    refuses("a negative target is refused", T.set_targets, db, a, calorie_target=-5000)
    refuses("an absurd target is refused", T.set_targets, db, a, step_target=10**9)
    refuses(
        "clearing an unknown field is refused", T.set_targets, db, a, clear=["salary"]
    )
    refuses("setting nothing is refused", T.set_targets, db, a)
    check(
        "the other account's targets are untouched",
        T.set_targets(db, b, step_target=3000)["targets"]["calorie_target"],
        None,
    )
    db.commit()

    print()
    print("── the weekly plan ──")
    r = T.set_weekly_plan(db, a, run_km=30, disciplines=["run", "strength"])
    db.commit()
    # Canonical order, not the caller's: `clean_disciplines` reorders against
    # DISCIPLINE_KEYS so the stored string is stable and de-duplicated however
    # the caller happened to list them.
    check(
        "set (canonical order, deduped)",
        (r["weekly_plan"]["run_km"], r["weekly_plan"]["disciplines"]),
        (30.0, ["run", "strength"]),
    )
    refuses(
        "an unknown discipline is refused, not dropped",
        T.set_weekly_plan,
        db,
        a,
        disciplines=["run", "quidditch"],
    )
    r = T.set_weekly_plan(db, a, bike_km=60)
    db.commit()
    check("adding bike leaves run and disciplines", r["weekly_plan"]["run_km"], 30.0)
    check("  disciplines intact", r["weekly_plan"]["disciplines"], ["run", "strength"])

    print()
    print("── the boundary: no tool writes history ──")
    # Not a runtime check — a structural one. If a write tool ever appears that
    # touches logged data, this list is where it would have to be declared, so
    # the assertion is that the list still says what we think it says.
    check(
        "write tools are exactly the planning ones",
        sorted(T.WRITE_TOOLS),
        [
            "archive_exercise",
            "create_exercise",
            "save_routine",
            "set_targets",
            "set_weekly_plan",
            "update_exercise",
        ],
    )
    check(
        "every write tool is registered",
        sorted(T.WRITE_TOOLS - set(T.TOOLS)),
        [],
    )

    db.close()
    print()
    if fails:
        print(f"  {len(fails)} FAILURE(S): " + ", ".join(fails))
        return 1
    print("  ALL MCP WRITE PATHS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
