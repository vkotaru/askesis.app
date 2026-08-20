"""Pull daily wellness and activities from Garmin Connect into Askesis.

There is no official personal Garmin API — the Connect Developer Program needs
a legal entity — so this rides on `garminconnect`, which talks to the same
endpoints the mobile app does. That has two consequences worth knowing before
touching anything here:

1. **Logins are rate limited by IP.** Garmin answers 429 to a burst, and the
   library's own strategy chain burns attempts working around it. So the
   session token is cached on disk and reused; `sync()` never logs in when a
   valid token exists. Poll once or twice a day, not per request.
2. **It can break.** Garmin changed its auth flow in March 2026 and deprecated
   `garth`, the library everything used to depend on; `garminconnect` survived
   by moving to `curl_cffi`. Expect to pin versions and expect breakage.

Because of (1), credentials are handled *out of band*: an operator logs in once
interactively (`scripts/garmin_sync.py --login`, answering MFA at the prompt)
and the resulting token file is all this module needs afterwards. **No Garmin
password is ever stored in the database.** That is deliberate — v1.0.0 removed
the app's only reversible-secret mechanism along with Google, and this keeps it
removed.

Everything is stored canonical metric (see app/units.py): Garmin's metres and
seconds become kilometres and minutes here, at the boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Activity, ActivityType, DailyLog, TimeOfDay, User

logger = logging.getLogger(__name__)

SOURCE = "garmin"

# Garmin's typeKey vocabulary is open-ended and Askesis only has two buckets, so
# this is a membership test with a default rather than an exhaustive table: an
# activity type nobody has seen yet lands in CARDIO instead of crashing.
_STRENGTH_TYPE_KEYS = {
    "strength_training",
    "indoor_cardio_strength",
    "pilates",
    "yoga",
}

# Icon names must match frontend/src/lib/utils/activityIcons.ts, which only
# renders a known set. Anything unmapped is left NULL and the UI falls back.
_ICON_BY_TYPE_KEY = {
    "running": "footprints",
    "treadmill_running": "footprints",
    "trail_running": "mountain",
    "walking": "footprints",
    "hiking": "mountain",
    "cycling": "bike",
    "road_biking": "bike",
    "mountain_biking": "bike",
    "indoor_cycling": "bike",
    "virtual_ride": "bike",
    "strength_training": "dumbbell",
    "lap_swimming": "waves",
    "open_water_swimming": "waves",
}


@dataclass
class SyncReport:
    """What one sync run did. Counts, not rows — this is for a CLI summary."""

    activities_created: int = 0
    activities_updated: int = 0
    daily_logs_created: int = 0
    daily_logs_filled: int = 0
    days_seen: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"activities: +{self.activities_created} new, "
            f"{self.activities_updated} updated | "
            f"daily logs: +{self.daily_logs_created} new, "
            f"{self.daily_logs_filled} filled | "
            f"{self.days_seen} days | {len(self.errors)} errors"
        )


# ── Pure mapping ─────────────────────────────────────────────────────────────
# Deliberately free of network and database access so the shapes can be checked
# against a recorded payload without either.


def time_of_day_for(hour: int) -> TimeOfDay:
    """Bucket a local clock hour into Askesis's four-way enum."""
    if 5 <= hour < 12:
        return TimeOfDay.MORNING
    if 12 <= hour < 17:
        return TimeOfDay.AFTERNOON
    if 17 <= hour < 21:
        return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


def activity_type_for(type_key: str | None) -> ActivityType:
    return (
        ActivityType.STRENGTH
        if (type_key or "") in _STRENGTH_TYPE_KEYS
        else ActivityType.CARDIO
    )


def map_activity(raw: dict[str, Any]) -> dict[str, Any] | None:
    """One Garmin activity -> Activity column values, or None if unusable.

    `startTimeLocal` is the device's own wall clock ("2026-08-19 08:08:36").
    Using it directly — rather than deriving a date from a UTC instant — is what
    keeps a late-evening workout on the day it happened.
    """
    external_id = raw.get("activityId")
    started = raw.get("startTimeLocal")
    if external_id is None or not started:
        return None

    try:
        # Naive on purpose (DTZ007): this is the device's local wall clock,
        # not an instant. Attaching a timezone here is what produces the
        # classic off-by-one where an evening workout lands on tomorrow.
        start = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
    except ValueError:
        logger.warning("Unparseable startTimeLocal %r, skipping", started)
        return None

    type_key = (raw.get("activityType") or {}).get("typeKey")
    duration_s = raw.get("duration")
    distance_m = raw.get("distance")
    calories = raw.get("calories")

    return {
        "external_id": str(external_id),
        "source": SOURCE,
        "date": start.date(),
        "time_of_day": time_of_day_for(start.hour),
        "name": (raw.get("activityName") or type_key or "Activity")[:100],
        "activity_type": activity_type_for(type_key),
        # Garmin sends float seconds and metres; Askesis stores minutes and km.
        "duration_mins": round(duration_s / 60) if duration_s else None,
        "distance_km": round(distance_m / 1000, 3) if distance_m else None,
        "calories": round(calories) if calories else None,
        "icon": _ICON_BY_TYPE_KEY.get(type_key or ""),
    }


def sleep_hours_from(payload: dict[str, Any] | None) -> float | None:
    """Total sleep in hours from a get_sleep_data payload."""
    seconds = ((payload or {}).get("dailySleepDTO") or {}).get("sleepTimeSeconds")
    return round(seconds / 3600, 2) if seconds else None


def water_ml_from(payload: dict[str, Any] | None) -> int | None:
    """Logged hydration in ml. 0 means "tracked, drank nothing recorded" —
    which is not a value worth writing over a blank, so treat it as absent."""
    value = (payload or {}).get("valueInML")
    return round(value) if value else None


# ── Database side ────────────────────────────────────────────────────────────


def _upsert_activity(
    db: Session, user: User, values: dict[str, Any], report: SyncReport
):
    """Insert, or update the row this provider already owns.

    Matched on (user, source, external_id) — the unique constraint added in
    `add_activity_provenance`. Fields the user can edit but Garmin doesn't
    supply (notes, tags, url) are never touched.
    """
    existing = (
        db.query(Activity)
        .filter(
            Activity.user_id == user.id,
            Activity.source == SOURCE,
            Activity.external_id == values["external_id"],
        )
        .one_or_none()
    )

    if existing is None:
        db.add(Activity(user_id=user.id, **values))
        report.activities_created += 1
        return

    # A previously-synced activity can legitimately change: Garmin recomputes
    # calories, and the user can rename it in Connect.
    changed = False
    for key, value in values.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    if changed:
        existing.deleted_at = None
        report.activities_updated += 1


def _fill_daily_log(
    db: Session,
    user: User,
    day: date_type,
    fields: dict[str, Any],
    report: SyncReport,
) -> None:
    """Write Garmin's wellness numbers into that day's log.

    **Only fills blanks.** If you already typed a step count or a sleep figure
    for that day, Garmin does not overwrite it. The device is not more
    authoritative than the person, and silently rewriting hand-entered health
    data is the kind of surprise that makes a tracker untrustworthy.
    """
    supplied = {k: v for k, v in fields.items() if v is not None}
    if not supplied:
        return

    log = (
        db.query(DailyLog)
        .filter(
            DailyLog.user_id == user.id,
            DailyLog.date == day,
            DailyLog.deleted_at.is_(None),
        )
        .one_or_none()
    )

    if log is None:
        db.add(DailyLog(user_id=user.id, date=day, **supplied))
        report.daily_logs_created += 1
        return

    filled = False
    for key, value in supplied.items():
        if getattr(log, key) is None:
            setattr(log, key, value)
            filled = True
    if filled:
        report.daily_logs_filled += 1


# ── Client ───────────────────────────────────────────────────────────────────


def connect(tokenstore: str, email: str | None = None, password: str | None = None):
    """Return a logged-in Garmin client, preferring the cached session.

    `login(tokenstore)` both loads an existing token file and writes one after a
    fresh credential login, so there is no separate save step. Imported lazily
    so the rest of the app still boots when `garminconnect` isn't installed.
    """
    from garminconnect import Garmin

    if not (email and password):
        api = Garmin()
        api.login(tokenstore)  # raises if there is no usable cached session
        return api

    api = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    api.login(tokenstore)
    return api


def sync_user(api, db: Session, user: User, days: int = 7) -> SyncReport:
    """Pull the last `days` days for one account and commit.

    Re-running is safe and is the intended mode: activities dedupe on their
    provider id, and daily logs only fill blanks. Overlapping windows are how
    a late-arriving device upload gets picked up.
    """
    report = SyncReport()
    # Local civil date (DTZ011), matching how the rest of the app keys days.
    today = date_type.today()  # noqa: DTZ011
    start = today - timedelta(days=days)

    # One ranged call instead of one per day — fewer requests is the whole game
    # against a rate-limited endpoint.
    try:
        steps_by_day = {
            row["calendarDate"]: row.get("totalSteps")
            for row in api.get_daily_steps(start.isoformat(), today.isoformat())
        }
    except Exception as exc:  # noqa: BLE001 - one endpoint failing isn't fatal
        report.errors.append(f"steps: {type(exc).__name__}: {exc}")
        steps_by_day = {}

    try:
        activities = api.get_activities_by_date(start.isoformat(), today.isoformat())
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"activities: {type(exc).__name__}: {exc}")
        activities = []

    for raw in activities:
        values = map_activity(raw)
        if values is not None:
            _upsert_activity(db, user, values, report)

    # Sleep and hydration are per-day endpoints, so this is the expensive loop.
    for offset in range(days + 1):
        day = start + timedelta(days=offset)
        iso = day.isoformat()
        report.days_seen += 1

        sleep = hydration = None
        try:
            sleep = api.get_sleep_data(iso)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"sleep {iso}: {type(exc).__name__}")
        try:
            hydration = api.get_hydration_data(iso)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"hydration {iso}: {type(exc).__name__}")

        _fill_daily_log(
            db,
            user,
            day,
            {
                "steps": steps_by_day.get(iso),
                "sleep_hours": sleep_hours_from(sleep),
                "water_ml": water_ml_from(hydration),
            },
            report,
        )

    db.commit()
    return report
