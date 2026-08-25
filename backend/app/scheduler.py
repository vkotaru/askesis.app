"""Background jobs owned by the app process. Currently the nightly Garmin pull.

Why in-process rather than host cron: the container is the only thing that knows
the token store, the database URL and the config, and `docker compose up` is the
only setup step. A cron entry on the host is a second place to configure, a
second thing to forget when the box is rebuilt, and it needs a shell — which is
the whole thing this is meant to avoid.

**This assumes one worker.** The image runs a single uvicorn process, so there is
exactly one scheduler. Adding `--workers N` would give you N schedulers all
firing the same job; that would need a shared lock instead.

Every job here must be defensive to the point of paranoia. A background task that
raises on a bad night must not take the API down with it, so the wrapper catches
everything and logs.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ── Run state ────────────────────────────────────────────────────────────────
# So the Settings page can answer "is this thing alive?" without a shell.
#
# Held in memory and lost on restart, deliberately: this is a debugging aid, not
# a record, and a table for it would be a schema commitment to a number nobody
# will read twice. A restarted container reports "unknown", which is honest --
# it is not the same claim as "never ran".


@dataclass
class GarminRun:
    started_at: datetime
    finished_at: datetime | None = None
    ok: bool = False
    summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Set when the failure was specifically "this token no longer works", which
    # is the one failure a person has to act on. Kept distinct from a 429:
    # telling someone to re-login while Garmin is rate-limiting them is how a
    # slow night becomes a locked account.
    auth_failed: bool = False
    trigger: str = "schedule"  # or "manual"


# Guards the sync itself, not the scheduler. APScheduler's max_instances=1 stops
# the cron job overlapping itself; this also stops a hand-pressed "Sync now"
# landing on top of it. Two concurrent Garmin sessions is exactly the 429 trap
# app/garmin.py's docstring warns about.
_run_lock = threading.Lock()
_last_run: GarminRun | None = None


def last_run() -> GarminRun | None:
    return _last_run


def is_running() -> bool:
    return _run_lock.locked()


def _resolve_sync_user(db, configured: str) -> User | None:
    """The account to sync: the configured one, or the only one there is.

    The Garmin token store is a single directory today, so it belongs to one
    account. Guessing between several would silently attach one person's watch
    data to another person's log, so with more than one account and no explicit
    setting this refuses rather than picks.
    """
    if configured:
        user = (
            db.query(User)
            .filter((User.username == configured) | (User.email == configured))
            .one_or_none()
        )
        if user is None:
            logger.error(
                "Garmin sync: GARMIN_SYNC_USER=%r matches no account", configured
            )
        return user

    users = db.query(User).all()
    if len(users) == 1:
        return users[0]
    logger.error(
        "Garmin sync: %d accounts exist and GARMIN_SYNC_USER is unset — refusing "
        "to guess which one the watch belongs to.",
        len(users),
    )
    return None


def resolve_sync_user(db) -> User | None:
    """The account the token store belongs to, or None if it can't be settled."""
    return _resolve_sync_user(db, get_settings().garmin_sync_user)


def run_garmin_sync(trigger: str = "schedule") -> None:
    """One pull. Never raises — a bad night must not kill the app.

    Both the cron job and the manual button land here, so they cannot overlap
    and they report through exactly the same state.
    """
    from app import garmin

    global _last_run

    if not _run_lock.acquire(blocking=False):
        logger.info("Garmin sync: already running, skipping this %s trigger", trigger)
        return

    run = GarminRun(started_at=datetime.now(timezone.utc), trigger=trigger)
    _last_run = run
    settings = get_settings()
    db = SessionLocal()
    try:
        user = _resolve_sync_user(db, settings.garmin_sync_user)
        if user is None:
            run.errors.append("No account to sync. Set GARMIN_SYNC_USER to a username.")
            return

        api = garmin.connect(settings.garmin_tokenstore)
        report = garmin.sync_user(api, db, user, days=settings.garmin_sync_days)
        logger.info("Garmin sync for %s — %s", user.username, report.summary())
        for err in report.errors:
            logger.warning("Garmin sync: %s", err)
        run.summary = {
            "activities_created": report.activities_created,
            "activities_updated": report.activities_updated,
            "daily_logs_created": report.daily_logs_created,
            "daily_logs_filled": report.daily_logs_filled,
            "days_seen": report.days_seen,
        }
        run.errors.extend(report.errors)
        run.ok = True
    except Exception as exc:  # noqa: BLE001 - a scheduled job may never propagate
        # Includes GarminAuthUnavailable (no token, no fallback credentials) and
        # the 429 that connect() deliberately refuses to work around. Both are
        # "try again tomorrow", not "crash the server".
        logger.error("Garmin sync failed: %s: %s", type(exc).__name__, exc)
        run.errors.append(f"{type(exc).__name__}: {exc}")
        run.auth_failed = isinstance(exc, garmin.GarminAuthUnavailable)
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.close()
        _run_lock.release()


def run_garmin_sync_now() -> bool:
    """Start a pull on a background thread. False if one is already running.

    A thread rather than FastAPI's BackgroundTasks: that runs after the response
    with no handle, so it could not answer "is it still going?" — which is the
    one question the status endpoint exists to answer.
    """
    if is_running():
        return False
    threading.Thread(
        target=run_garmin_sync,
        kwargs={"trigger": "manual"},
        daemon=True,
        name="garmin-sync-manual",
    ).start()
    return True


def start_scheduler() -> None:
    """Start background jobs if any are enabled. Safe to call once, at startup."""
    global _scheduler

    settings = get_settings()
    if not settings.garmin_sync_enabled:
        logger.info("Scheduler: no jobs enabled")
        return

    if _scheduler is not None:
        logger.warning("Scheduler: already started, ignoring")
        return

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_garmin_sync,
        CronTrigger(
            hour=settings.garmin_sync_hour,
            minute=17,
            timezone=ZoneInfo(settings.garmin_sync_tz),
        ),
        id="garmin_sync",
        name="Garmin Connect pull",
        # One at a time, and a run missed while the container was down is
        # folded into a single catch-up rather than replayed N times. The pull
        # re-reads an overlapping window anyway, so nothing is lost by skipping.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler: Garmin pull scheduled daily at %02d:17 %s, %d-day window",
        settings.garmin_sync_hour,
        settings.garmin_sync_tz,
        settings.garmin_sync_days,
    )


def shutdown_scheduler() -> None:
    """Stop background jobs on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler: stopped")
