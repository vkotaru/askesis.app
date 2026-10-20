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
  * isolation  -- the tools cannot reach logged history, except the narrow
                  writes: food intake, a day's weight, and adding a session

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
    print("── how a movement is measured ──")
    r = T.create_exercise(db, a, "Wall Sit", muscle_group="Legs", tracking_type="time")
    db.commit()
    check("create with tracking_type", r["tracking_type"], "time")
    refuses(
        "an unknown kind is refused",
        T.create_exercise,
        db,
        a,
        "Nonsense Hold",
        tracking_type="minutes",
    )
    refuses(
        "  and so is a non-string",
        T.create_exercise,
        db,
        a,
        "Nonsense Hold 2",
        tracking_type=3,
    )
    check(
        "a new movement defaults to weight and reps",
        T.create_exercise(db, a, "Landmine Press")["tracking_type"],
        "weight_reps",
    )
    db.commit()

    # The exact shape of a bug this repo shipped once: the workout screen
    # changed only how a movement is measured and wiped its muscle group, video
    # link and form notes for both accounts, because it sent that one field to
    # an endpoint whose contract is "this is the whole object". The service
    # layer's replace=False is what both the connector and the app's PATCH now
    # rely on, so it is asserted here rather than trusted.
    T.update_exercise(
        db, a, "Wall Sit", video_url="https://youtu.be/x", notes="knees at 90"
    )
    db.commit()
    r = T.update_exercise(db, a, "Wall Sit", tracking_type="reps")
    db.commit()
    check("changing the kind keeps muscle_group", r["muscle_group"], "Legs")
    check("  keeps the video link", r["video_url"], "https://youtu.be/x")
    check("  keeps the form notes", r["notes"], "knees at 90")
    check("  and did change the kind", r["tracking_type"], "reps")
    r = T.update_exercise(db, a, "Wall Sit", notes="hold it")
    db.commit()
    check("an edit that omits the kind leaves it alone", r["tracking_type"], "reps")

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
    print("── length bounds (an MCP write must not be able to 500 the web app) ──")
    refuses(
        "over-long exercise notes refused",
        T.create_exercise,
        db,
        a,
        "Long Notes Lift",
        notes="x" * 2508,
    )
    refuses(
        "over-long muscle_group refused",
        T.create_exercise,
        db,
        a,
        "Long Group Lift",
        muscle_group="g" * 80,
    )
    refuses(
        "over-long movement note refused",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises=[{"name": "Overhead Press A", "notes": "y" * 300}],
    )
    refuses(
        "an over-long name refused",
        T.create_exercise,
        db,
        a,
        "n" * 150,
    )
    refuses(
        "a non-string movement name refused, not a crash",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises=[{"name": 123}],
    )
    refuses(
        "a single object instead of a list refused",
        T.save_routine,
        db,
        a,
        "Push A",
        exercises={"name": "Overhead Press A"},
    )

    print()
    print("── each tool clears only what it can set ──")
    refuses(
        "set_targets cannot clear the weekly plan",
        T.set_targets,
        db,
        a,
        clear=["weekly_run_km"],
    )
    refuses(
        "set_weekly_plan cannot clear a daily target",
        T.set_weekly_plan,
        db,
        a,
        clear=["step_target"],
    )
    refuses(
        "setting and clearing the same field is a contradiction",
        T.set_targets,
        db,
        a,
        step_target=9000,
        clear=["step_target"],
    )

    print()
    print("── the scope gate ──")
    # Previously untestable: it lived in server.py, which imports the MCP SDK,
    # which CI never installs. It is the only thing between a read-only token
    # and a write tool, so "verified by reading it" was not good enough.
    from mcp_server.authz import may_write

    W = "askesis:write"
    check("read-only token cannot write", may_write(["askesis:read"], W), False)
    check("read+write token can", may_write(["askesis:read", W], W), True)
    check("no scopes at all cannot", may_write([], W), False)
    check("a None scope list cannot", may_write(None, W), False)
    check("case does not count as a match", may_write(["Askesis:Write"], W), False)
    check("a prefix does not match", may_write(["askesis:writeable"], W), False)
    check(
        "a misconfigured empty write_scope denies, not allows",
        may_write(["askesis:read", ""], ""),
        False,
    )

    print()
    print("── log_day_nutrition: the one write to logged history ──")
    from datetime import timedelta

    from app.config import local_today
    from app.models import DailyNutrition, Meal

    d = (local_today() - timedelta(days=3)).isoformat()

    def meals_on_day(uid, day, label):
        return (
            db.query(Meal)
            .filter(Meal.user_id == uid, Meal.date == day)
            .filter(Meal.label == label, Meal.deleted_at.is_(None))
            .all()
        )

    def meals_on(uid, label):
        return (
            db.query(Meal)
            .filter(Meal.user_id == uid, Meal.date == local_today() - timedelta(days=3))
            .filter(Meal.label == label, Meal.deleted_at.is_(None))
            .all()
        )

    r = T.log_day_nutrition(
        db,
        a,
        d,
        breakfast_kcal=420,
        lunch_kcal=650,
        snack_kcal=0,
        protein_g=152,
        carbs_g=210.44,
        fat_g=71,
    )
    db.commit()
    check(
        "creates a row per meal given",
        (r["meals"]["Breakfast"]["result"], r["meals"]["Lunch"]["result"]),
        ("created", "created"),
    )
    check(
        "  but never a zero-calorie row",
        (r["meals"]["Snack"]["result"], len(meals_on(a, "Snack"))),
        ("skipped", 0),
    )
    check("  day total is the sum", r["day_total_kcal"], 1070)
    check("  macros set, rounded to 0.1 g", r["macros"]["carbs_g"]["value"], 210.4)

    r = T.log_day_nutrition(db, a, d, lunch_kcal=700, dinner_kcal=800)
    db.commit()
    check(
        "a second call updates, not adds",
        (len(meals_on(a, "Lunch")), r["meals"]["Lunch"]["before_kcal"]),
        (1, 650),
    )
    check("  omitted meals are left alone", len(meals_on(a, "Breakfast")), 1)
    check("  day total reflects the replace", r["day_total_kcal"], 420 + 700 + 800)
    nut = (
        db.query(DailyNutrition)
        .filter(
            DailyNutrition.user_id == a,
            DailyNutrition.date == local_today() - timedelta(days=3),
        )
        .one()
    )
    check("  omitted macros are left alone", (nut.protein_g, nut.fat_g), (152.0, 71.0))

    r = T.log_day_nutrition(db, a, d, lunch_kcal=700)
    check("same value reports unchanged", r["meals"]["Lunch"]["result"], "unchanged")

    # Two Dinner rows: the Daily Log locks the box; the tool must not pick one.
    db.add(
        Meal(
            user_id=a,
            date=local_today() - timedelta(days=3),
            label="Dinner",
            calories=100,
        )
    )
    db.commit()
    r = T.log_day_nutrition(db, a, d, dinner_kcal=900)
    db.commit()
    check(
        "a label with several rows is skipped",
        r["meals"]["Dinner"]["result"],
        "skipped",
    )
    check(
        "  and both rows are untouched",
        sorted(m.calories for m in meals_on(a, "Dinner")),
        [100, 800],
    )

    r = T.log_day_nutrition(db, b, d, lunch_kcal=500)
    db.commit()
    check(
        "the other account gets its own row",
        (len(meals_on(b, "Lunch")), meals_on(a, "Lunch")[0].calories),
        (1, 700),
    )

    refuses(
        "a future date refused",
        T.log_day_nutrition,
        db,
        a,
        (local_today() + timedelta(days=1)).isoformat(),
        lunch_kcal=500,
    )
    refuses(
        "a misread year refused",
        T.log_day_nutrition,
        db,
        a,
        (local_today() - timedelta(days=3650)).isoformat(),
        lunch_kcal=500,
    )
    refuses(
        "a non-ISO date refused", T.log_day_nutrition, db, a, "Oct 6", lunch_kcal=500
    )
    refuses(
        "a misread 21400 kcal lunch refused",
        T.log_day_nutrition,
        db,
        a,
        d,
        lunch_kcal=21400,
    )
    refuses("negative calories refused", T.log_day_nutrition, db, a, d, lunch_kcal=-5)
    refuses(
        "an impossible macro refused", T.log_day_nutrition, db, a, d, protein_g=1520
    )
    refuses(
        "a string for calories refused, not a crash",
        T.log_day_nutrition,
        db,
        a,
        d,
        lunch_kcal="650",
    )
    refuses("nothing to log refused", T.log_day_nutrition, db, a, d)

    # Validate-everything-first: one bad field must leave the day untouched.
    before = meals_on(a, "Breakfast")[0].calories
    refuses(
        "a bad macro alongside a good meal refused",
        T.log_day_nutrition,
        db,
        a,
        d,
        breakfast_kcal=999,
        fat_g=-1,
    )
    db.rollback()
    check(
        "  and the good meal was not half-written",
        meals_on(a, "Breakfast")[0].calories,
        before,
    )

    print()
    print("── log_day_nutrition mode='add': one more snack, no read-modify-write ──")
    d2 = (local_today() - timedelta(days=4)).isoformat()
    T.log_day_nutrition(db, a, d2, lunch_kcal=500, protein_g=40)
    db.commit()
    r = T.log_day_nutrition(
        db, a, d2, mode="add", lunch_kcal=120, snack_kcal=90, protein_g=11.5, fat_g=3
    )
    db.commit()
    check(
        "add sums onto the existing meal",
        (r["meals"]["Lunch"]["before_kcal"], r["meals"]["Lunch"]["kcal"]),
        (500, 620),
    )
    check(
        "  creates a meal that wasn't there", r["meals"]["Snack"]["result"], "created"
    )
    check("  adds to the day's protein", r["macros"]["protein_g"]["value"], 51.5)
    check("  and an unset macro starts from 0", r["macros"]["fat_g"]["value"], 3.0)
    check("  day total includes both", r["day_total_kcal"], 620 + 90)
    refuses(
        "an unknown mode refused",
        T.log_day_nutrition,
        db,
        a,
        d2,
        mode="merge",
        lunch_kcal=1,
    )
    lunch_before = T.log_day_nutrition(db, a, d2, mode="add", lunch_kcal=0)["meals"][
        "Lunch"
    ]["kcal"]
    refuses(
        "add that would push a meal past the cap refused",
        T.log_day_nutrition,
        db,
        a,
        d2,
        mode="add",
        lunch_kcal=4900,
    )
    refuses(
        "add that would push a macro past the cap refused",
        T.log_day_nutrition,
        db,
        a,
        d2,
        mode="add",
        protein_g=999,
    )
    db.rollback()
    r = T.log_day_nutrition(db, a, d2, mode="add", lunch_kcal=0)
    check(
        "  and the refused add left the meal as it was",
        r["meals"]["Lunch"]["kcal"],
        lunch_before,
    )

    print()
    print("── log_meal: macros per meal, the day moved by the difference ──")
    d3 = local_today() - timedelta(days=5)
    ds = d3.isoformat()

    def day_protein(uid):
        n = (
            db.query(DailyNutrition)
            .filter(DailyNutrition.user_id == uid, DailyNutrition.date == d3)
            .first()
        )
        return n.protein_g if n else None

    T.log_meal(db, a, ds, "Breakfast", kcal=420, protein_g=30, carbs_g=50, fat_g=12)
    db.commit()
    r = T.log_meal(db, a, ds, "lunch", kcal=650, protein_g=40, carbs_g=70)
    db.commit()
    check("lunch created", r["result"], "created")
    check("  breakfast + lunch protein", day_protein(a), 70.0)
    check("  carbs summed too", r["day_macros"]["carbs_g"]["value"], 120.0)
    check(
        "  fat only from breakfast (lunch gave none)",
        r["day_macros"].get("fat_g"),
        None,
    )
    r = T.log_meal(db, a, ds, "Lunch", kcal=600, protein_g=35)
    db.commit()
    check("lunch again replaces lunch, not stacks", day_protein(a), 65.0)
    check("  and its calories", (r["before"]["kcal"], r["after"]["kcal"]), (650, 600))
    check("  breakfast untouched", meals_on_day(a, d3, "Breakfast")[0].protein_g, 30.0)
    check("  still one lunch row", len(meals_on_day(a, d3, "Lunch")), 1)
    r = T.log_meal(db, a, ds, "Lunch", mode="add", kcal=105, protein_g=1.3)
    db.commit()
    check(
        "add: a banana at lunch",
        (r["after"]["kcal"], r["after"]["protein_g"]),
        (705, 36.3),
    )
    check("  day moved by the banana only", day_protein(a), 66.3)

    # The user types a whole-day number in the Daily Log; it stays the truth.
    n = (
        db.query(DailyNutrition)
        .filter(DailyNutrition.user_id == a, DailyNutrition.date == d3)
        .one()
    )
    n.protein_g = 120
    db.commit()
    T.log_meal(db, a, ds, "Dinner", kcal=700, protein_g=45)
    db.commit()
    check("a hand-typed day total moves by the meal", day_protein(a), 165.0)
    check("  and another account is untouched", day_protein(b), None)

    refuses(
        "creating a meal without calories refused",
        T.log_meal,
        db,
        a,
        ds,
        "Snack",
        protein_g=5,
    )
    refuses("an unknown meal refused", T.log_meal, db, a, ds, "Brunch", kcal=300)
    refuses("nothing to log refused", T.log_meal, db, a, ds, "Lunch")
    refuses(
        "an impossible macro refused", T.log_meal, db, a, ds, "Lunch", protein_g=1500
    )
    refuses(
        "a future date refused",
        T.log_meal,
        db,
        a,
        (local_today() + timedelta(days=1)).isoformat(),
        "Lunch",
        kcal=1,
    )
    db.rollback()
    check("  refusals changed nothing", day_protein(a), 165.0)

    # Deleting a meal takes its share back out, on both delete paths.
    from app.intake_log import release_meal_macros

    dinner = meals_on_day(a, d3, "Dinner")[0]
    release_meal_macros(db, dinner)
    dinner.deleted_at = local_today()
    db.commit()
    check("deleting dinner takes its protein out", day_protein(a), 120.0)
    import inspect as _inspect

    from app.routers import nutrition as _nutrition
    from app.routers import sync as _sync

    check(
        "  both delete paths release macros",
        [
            "release_meal_macros(" in _inspect.getsource(_nutrition.delete_meal),
            "release_meal_macros(" in _inspect.getsource(_sync._handle_delete),
        ],
        [True, True],
    )

    print()
    print("── log_weight: one column of the day, stamped as the user's ──")
    from app.models import Activity, DailyLog
    from app.provenance import parse_sources

    d4 = local_today() - timedelta(days=6)
    db.add(DailyLog(user_id=a, date=d4, sleep_hours=7.5, steps=4000))
    db.commit()
    r = T.log_weight(db, a, d4.isoformat(), 81.25)
    db.commit()
    log = db.query(DailyLog).filter_by(user_id=a, date=d4).one()
    check("weight set on the existing day", (r["result"], log.weight), ("set", 81.25))
    check("  sleep and steps untouched", (log.sleep_hours, log.steps), (7.5, 4000))
    check(
        "  marked as the user's own", parse_sources(log.sources).get("weight"), "manual"
    )
    r = T.log_weight(db, a, d4.isoformat(), 80.9)
    db.commit()
    check("  a second call updates it", (r["before_kg"], r["weight_kg"]), (81.25, 80.9))
    d5 = (local_today() - timedelta(days=7)).isoformat()
    T.log_weight(db, a, d5, 82)
    db.commit()
    check(
        "a day with no log gets one",
        db.query(DailyLog)
        .filter_by(user_id=a, date=d4 - timedelta(days=1))
        .one()
        .weight,
        82.0,
    )
    check(
        "  and the other account has no row",
        db.query(DailyLog).filter_by(user_id=b, date=d4).count(),
        0,
    )
    refuses("pounds passed as kg refused (>500)", T.log_weight, db, a, d5, 650)
    refuses("an impossible weight refused", T.log_weight, db, a, d5, 5)
    refuses("a non-number refused", T.log_weight, db, a, d5, "80kg")
    db.rollback()

    print()
    print("── log_workout: add a session, never edit one ──")
    T.create_exercise(db, a, "Check Hamstring Hold", tracking_type="time")
    db.commit()
    stretches = [
        {
            "name": "check hamstring hold",
            "sets": [
                {"duration_seconds": 30, "notes": "left"},
                {"duration_seconds": 30, "notes": "right"},
            ],
        },
        {"name": "Check Unlisted Twist", "sets": [{"duration_seconds": 45}]},
    ]
    r = T.log_workout(
        db, a, d4.isoformat(), "Check stretch", exercises=stretches, duration_mins=12
    )
    db.commit()
    check("session added", r["name"], "Check stretch")
    check(
        "  library name resolved case-insensitively",
        r["exercises"][0],
        {"name": "Check Hamstring Hold", "sets": 2, "in_library": True},
    )
    check(
        "  an unknown movement is logged and listed",
        r["not_in_library"],
        ["Check Unlisted Twist"],
    )
    got = T.get_activity(db, a, r["id"])
    check(
        "  reads back with its sets",
        [(e["name"], len(e["sets"])) for e in got["exercises"]],
        [("Check Hamstring Hold", 2), ("Check Unlisted Twist", 1)],
    )
    check(
        "  and counts in exercise history",
        len(T.get_exercise_history(db, a, "Check Hamstring Hold")["sessions"]),
        1,
    )
    refuses(
        "the same session twice refused",
        T.log_workout,
        db,
        a,
        d4.isoformat(),
        "Check stretch",
        exercises=stretches,
    )
    db.rollback()
    r2 = T.log_workout(
        db,
        a,
        d4.isoformat(),
        "Check stretch",
        exercises=stretches,
        allow_duplicate=True,
    )
    db.commit()
    check("  unless allow_duplicate", r2["id"] != r["id"], True)
    refuses("  invisible to the other account", T.get_activity, db, b, r["id"])
    for label, kwargs in (
        ("an empty set refused", {"exercises": [{"name": "x", "sets": [{}]}]}),
        (
            "a bad set_type refused",
            {"exercises": [{"name": "x", "sets": [{"reps": 5, "set_type": "max"}]}]},
        ),
        (
            "a 25-hour hold refused",
            {"exercises": [{"name": "x", "sets": [{"duration_seconds": 90000}]}]},
        ),
        (
            "an unknown set field refused",
            {"exercises": [{"name": "x", "sets": [{"reps": 5, "weight": 20}]}]},
        ),
        (
            "fractional reps refused",
            {"exercises": [{"name": "x", "sets": [{"reps": 5.5}]}]},
        ),
        (
            "an unknown activity_type refused",
            {"activity_type": "yoga", "duration_mins": 20},
        ),
        ("nothing to log refused", {}),
    ):
        refuses(label, T.log_workout, db, a, d4.isoformat(), "Check refused", **kwargs)
    db.rollback()
    check(
        "  refusals added nothing",
        db.query(Activity).filter_by(user_id=a, name="Check refused").count(),
        0,
    )

    print()
    print("── the food library: save_food / search_foods ──")
    r = T.save_food(
        db,
        a,
        "Egg Whites",
        46,
        "g",
        25,
        brand="Kirkland Signature",
        protein_g=5,
        carbs_g=0,
        fat_g=0,
        notes="label: 3 tbsp (46 g)",
    )
    db.commit()
    check(
        "save creates a shared food",
        (r["created"], r["shared_with_household"], r["yours"]),
        (True, True, True),
    )
    r = T.save_food(
        db, a, "egg whites", 46, "g", 25, brand="KIRKLAND SIGNATURE", protein_g=5.5
    )
    db.commit()
    check(
        "same name+brand, any case, updates instead",
        (r["created"], r["protein_g"]),
        (False, 5.5),
    )
    check("  saving again replaces every field", r["notes"], None)
    s = T.search_foods(db, a, "kirkland egg white", include_online=False)
    check(
        "search matches word-wise across name and brand",
        [f["name"] for f in s["saved"]],
        ["egg whites"],
    )
    s = T.search_foods(db, b, "egg whites", include_online=False)
    check(
        "the other account sees a shared food",
        (len(s["saved"]), s["saved"][0]["yours"]),
        (1, False),
    )
    refuses(
        "the other account cannot overwrite it",
        T.save_food,
        db,
        b,
        "Egg Whites",
        46,
        "g",
        30,
        brand="Kirkland Signature",
    )
    r = T.save_food(
        db,
        a,
        "Chicken Rice Bowl",
        1,
        "bowl",
        540,
        category="Recipe",
        protein_g=42,
        carbs_g=60,
        fat_g=14,
        private=True,
        notes="Serves 4: 600 g chicken thigh, 300 g dry rice, 2 tbsp oil, veg",
    )
    db.commit()
    check(
        "a private recipe is saved",
        (r["category"], r["shared_with_household"]),
        ("Recipe", False),
    )
    check("  with its ingredients kept", r["notes"].startswith("Serves 4"), True)
    s = T.search_foods(db, b, "rice bowl", include_online=False)
    check("  and the other account cannot see it", s["saved"], [])
    refuses("a zero serving size refused", T.save_food, db, a, "X", 0, "g", 10)
    refuses("missing calories refused", T.save_food, db, a, "X", 10, "g", None)
    refuses(
        "a misread 25000 kcal serving refused", T.save_food, db, a, "X", 46, "g", 25000
    )
    refuses("an over-long unit refused", T.save_food, db, a, "X", 1, "u" * 30, 10)
    refuses(
        "over-long notes refused", T.save_food, db, a, "X", 1, "g", 10, notes="n" * 2100
    )
    refuses(
        "an empty search refused", T.search_foods, db, a, "   ", include_online=False
    )
    db.rollback()

    # USDA lists Energy in KCAL and kJ, in either order; a name-keyed dict once
    # kept the kJ value, so whole egg read 599 kcal. No network needed.
    from app.food_search import _usda_kcal

    check(
        "USDA kcal wins over kJ, whichever is listed last",
        (
            _usda_kcal({("Energy", "KCAL"): 143, ("Energy", "KJ"): 599}),
            _usda_kcal({("Energy", "KJ"): 776, ("Energy", "KCAL"): 185}),
        ),
        (143, 185),
    )
    check("  kJ alone is converted", round(_usda_kcal({("Energy", "KJ"): 599})), 143)

    # The REST response model must accept everything save_food can store, or a
    # connector write breaks the app's food list.
    from app.models import FoodItem as _Food
    from app.routers.nutrition import FoodItemResponse as _FoodOut

    rows = db.query(_Food).filter(_Food.source == "mcp").all()
    bad = []
    for row in rows:
        try:
            _FoodOut.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{row.name}: {exc}")
    check("every connector-saved food fits the REST response", bad, [])

    print()
    print("── the boundary: plans, plus one intake write, and nothing else ──")
    # Not a runtime check — a structural one. If a write tool ever appears that
    # touches logged data, this list is where it would have to be declared, so
    # the assertion is that the list still says what we think it says.
    # `log_day_nutrition` is the one deliberate exception (app/intake_log.py).
    check(
        "write tools: planning + save_food + the intake writes",
        sorted(T.WRITE_TOOLS),
        [
            "archive_exercise",
            "create_exercise",
            "log_day_nutrition",
            "log_meal",
            "log_weight",
            "log_workout",
            "save_food",
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

    # The dangerous direction, which the check above does not cover: a NEW
    # mutating tool added to TOOLS and forgotten in WRITE_TOOLS would be
    # callable with a read-only token AND would silently lose its write, since
    # server.py only commits for tools it knows are writers.
    #
    # Detected structurally rather than by a list someone has to remember to
    # update: any tool whose source calls a mutating planning function is a
    # writer, by definition.
    import inspect

    mutators = (
        "create_catalog_entry",
        "update_catalog_entry",
        "archive_catalog_entry",
        "save_routine",
        "apply_targets",
        "write_routine_exercises",
    )
    undeclared = sorted(
        name
        for name, fn in T.TOOLS.items()
        if name not in T.WRITE_TOOLS
        and (
            any(f"planning.{m}(" in inspect.getsource(fn) for m in mutators)
            or "intake_log.log_day(" in inspect.getsource(fn)
            or "intake_log.log_meal(" in inspect.getsource(fn)
            or "history_log." in inspect.getsource(fn)
            or "food_library.save(" in inspect.getsource(fn)
        )
    )
    check("no mutating tool is missing from WRITE_TOOLS", undeclared, [])

    # `sync.py::_write_exercises` builds an ExerciseSet from every field of
    # `ExerciseSetCreate`, which is what stops a new set field being accepted by
    # the REST path and silently dropped by the offline one -- the path every
    # set logged in the gym actually takes. That only holds while the schema and
    # the table agree, so assert it rather than assume it.
    from app.models import ExerciseSet as _Set
    from app.routers.activities import ExerciseSetCreate as _SetIn

    columns = {c.name for c in _Set.__table__.columns}
    check(
        "every set field the API accepts is a real column",
        sorted(f for f in _SetIn.model_fields if f not in columns),
        [],
    )

    print()
    print("── exercise history follows how a movement is measured ──")
    # Read-only, but it sits here because this is the harness that builds
    # movements of every kind. A timed movement used to return no sessions and
    # point at a tool that does not exist; a bodyweight pull-up (weight_reps,
    # blank weight) was filtered out as if it were noise.
    from datetime import date as _date

    from app.models import Activity, ActivityType, Exercise, ExerciseSet

    kinds = {
        "History Plank": "time",
        "History Pull-up": "weight_reps",
        "History Goblet Squat": "weight_reps",
        "History Row Erg": "distance_time",
        "History Push-up": "reps",
    }
    for name, kind in kinds.items():
        T.create_exercise(db, a, name, tracking_type=kind)
    db.commit()
    by_name = {
        e.name: e
        for e in db.query(ExerciseCatalog).filter(ExerciseCatalog.name.in_(list(kinds)))
    }
    act = Activity(
        user_id=a,
        date=_date(2026, 1, 5),
        name="History check",
        activity_type=ActivityType.STRENGTH,
    )
    db.add(act)
    db.flush()
    sets = {
        "History Plank": [dict(duration_seconds=65), dict(duration_seconds=50)],
        "History Pull-up": [dict(reps=8), dict(reps=6)],
        "History Goblet Squat": [
            dict(weight_kg=10, reps=10, set_type="warmup"),
            dict(weight_kg=20, reps=10),
            dict(weight_kg=22.5, reps=8),
        ],
        "History Row Erg": [dict(distance_m=500, duration_seconds=110)],
        "History Push-up": [dict(reps=20), dict(reps=15)],
    }
    for pos, (name, rows) in enumerate(sets.items()):
        ex = Exercise(
            activity_id=act.id, catalog_id=by_name[name].id, name=name, position=pos
        )
        db.add(ex)
        db.flush()
        for i, row in enumerate(rows, 1):
            db.add(ExerciseSet(exercise_id=ex.id, set_number=i, **row))
    db.commit()

    def first(name: str) -> dict:
        sessions = T.get_exercise_history(db, a, name)["sessions"]
        return sessions[0] if sessions else {}

    r = first("History Plank")
    check(
        "timed: longest and total hold",
        (r.get("longest_seconds"), r.get("total_seconds")),
        (65, 115),
    )
    r = first("History Pull-up")
    check(
        "bodyweight: best and total reps, no 1RM",
        (r.get("top_set"), r.get("total_reps"), "estimated_1rm_kg" in r),
        ({"weight_kg": None, "reps": 8}, 14, False),
    )
    r = first("History Goblet Squat")
    check(
        "weighted: top set, volume, warm-up excluded",
        (r.get("top_set"), r.get("volume_kg"), r.get("sets")),
        ({"weight_kg": 22.5, "reps": 8}, 380.0, 2),
    )
    r = first("History Row Erg")
    check(
        "distance: longest, totals",
        (r.get("longest_m"), r.get("total_seconds")),
        (500, 110),
    )
    r = first("History Push-up")
    check(
        "reps only: best and total", (r.get("best_reps"), r.get("total_reps")), (20, 35)
    )
    check(
        "  history for another account is empty",
        T.get_exercise_history(db, b, "History Plank")["sessions"],
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
