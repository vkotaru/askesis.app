"""What kind of training was that? — one answer, shared by everything that asks.

The stored data does not make this easy. ``Activity.activity_type`` has exactly
two values (cardio, strength), the Garmin importer files yoga and pilates under
STRENGTH, and swims, hikes, walks and rides all arrive as CARDIO. So the type
column alone cannot answer the question a weekly training plan asks.

Evidence is weighed in this order, weakest last:

1. **the name** — the only signal that survives hand entry, and Garmin puts the
   discipline in it ("Mountain View Running", "Yoga")
2. **the icon** — set by the importer per Garmin ``typeKey``, or chosen by hand
   in the activity form
3. **``activity_type``** — a two-way split, so only ever a fallback

An activity that matches nothing stays ``None`` rather than being guessed at.

──────────────────────────────────────────────────────────────────────────────
KEEP IN SYNC WITH ``frontend/src/lib/utils/disciplines.ts``.

That file is the original and drives the dashboard's Weekly Targets tile; this
is a port of its ``DISCIPLINES`` table and ``classify()``. The two lists can
drift, and there is no test suite that would notice — if you add a discipline
or a keyword to one, add it to the other in the same commit. Only the matching
rules are duplicated; the icon and colour choices stay in the frontend, since
nothing here renders anything.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Discipline:
    key: str
    label: str
    #: Lowercased substrings tried against the activity name.
    names: tuple[str, ...]
    #: ``activities.icon`` values that imply this discipline.
    icons: tuple[str, ...] = field(default_factory=tuple)


# Order matters: the first match wins. Calisthenics is listed before strength
# because "calisthenics strength" should read as calisthenics, and "push ups"
# should not be swallowed by a generic strength match.
DISCIPLINES: tuple[Discipline, ...] = (
    Discipline(
        key="calisthenics",
        label="Calisthenics",
        names=(
            "calisthenic",
            "bodyweight",
            "body weight",
            "pull up",
            "pull-up",
            "push up",
            "push-up",
            "dips",
            "bar work",
        ),
    ),
    Discipline(
        key="stretch",
        label="Stretching",
        names=("stretch", "yoga", "pilates", "mobility", "flexibility", "foam roll"),
        icons=("stretch",),
    ),
    Discipline(key="swim", label="Swim", names=("swim", "pool"), icons=("waves",)),
    Discipline(
        key="hike",
        label="Hike / Walk",
        names=("hike", "hiking", "walk", "walking", "trek"),
        icons=("mountain",),
    ),
    Discipline(
        key="bike",
        label="Bike",
        names=("bike", "biking", "cycling", "cycle", "ride", "spin"),
        icons=("bike",),
    ),
    Discipline(
        key="run",
        label="Run",
        names=("run", "running", "jog", "jogging", "treadmill"),
        icons=("footprints",),
    ),
    Discipline(
        key="strength",
        label="Strength",
        names=(
            "strength",
            "weights",
            "lifting",
            "gym",
            "upper body",
            "lower body",
            "leg day",
            "legs",
            "chest",
            "back",
            "arms",
            "shoulders",
            "core",
            "abs",
            "full body",
        ),
        icons=("dumbbell",),
    ),
)

DISCIPLINE_BY_KEY: dict[str, Discipline] = {d.key: d for d in DISCIPLINES}
DISCIPLINE_KEYS: tuple[str, ...] = tuple(d.key for d in DISCIPLINES)


class _Classifiable(Protocol):
    """The three columns `classify` reads — an Activity, or anything shaped like one.

    ``activity_type`` is typed loosely because it arrives as a SQLAlchemy enum
    member from the ORM and as a plain string from anything hand-built.
    """

    name: str | None
    icon: str | None
    activity_type: Any


def classify(activity: _Classifiable) -> str | None:
    """Which discipline is this? ``None`` when nothing matches.

    Deliberately not a guess. A CARDIO activity that matches no name or icon
    covers swims, hikes and rides as well as runs, so assuming "run" would put
    distance against the wrong weekly target and light the wrong chip in the
    dashboard's plan.
    """
    name = (getattr(activity, "name", None) or "").lower()

    for d in DISCIPLINES:
        if any(n in name for n in d.names):
            return d.key

    icon = getattr(activity, "icon", None)
    if icon:
        for d in DISCIPLINES:
            if icon in d.icons:
                return d.key

    # Last resort, and only for STRENGTH. 'cardio' is left unresolved above.
    activity_type = getattr(activity, "activity_type", None)
    value = getattr(activity_type, "value", activity_type)
    if value == "strength":
        return "strength"
    return None


def parse_plan(raw: str | None) -> list[str]:
    """The comma-separated weekly plan from ``user_settings.weekly_disciplines``.

    Trims and validates each key, mirroring ``parsePlan`` in the frontend file.
    Dropping this was not cosmetic: ``"run, bike"`` yields a key of ``" bike"``,
    which can never equal anything `classify` returns, so that discipline is
    reported *missed* every single week and the user is told they skipped a
    session they did.
    """
    if not raw:
        return []
    return [
        key
        for key in (part.strip() for part in raw.split(","))
        if key in DISCIPLINE_BY_KEY
    ]
