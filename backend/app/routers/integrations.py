"""Read and drive the Garmin import from the app, instead of from a shell.

Deliberately narrow. This reports what the importer did and lets you start it
by hand; it does **not** log in. Connecting an account stays
`scripts/garmin_sync.py --login`, because the login is interactive (MFA), is
rate-limited by IP, and would mean this app accepting a Garmin password --
which v1.0.0 removed the ability to store on purpose. What the UI adds is a
diagnosis: when the cached token is gone, `needs_reauth` says so and the client
shows the command to run.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import scheduler
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user

router = APIRouter()


class GarminRunResponse(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    ok: bool
    running: bool
    trigger: str
    summary: dict[str, int]
    errors: list[str]


class GarminStatusResponse(BaseModel):
    enabled: bool  # is the nightly schedule on
    configured: bool  # is there a cached session to sync with
    scheduled_hour: int | None
    timezone: str
    lookback_days: int
    sync_username: str | None  # the account the token store belongs to
    is_owner: bool  # ...and whether that is the caller
    running: bool
    needs_reauth: bool
    rate_limited: bool
    last_run: GarminRunResponse | None


def _has_token(tokenstore: str) -> bool:
    """A token store counts as configured once it holds anything.

    The client writes more than one file and has renamed them across versions,
    so this asks "did a login ever land here" rather than naming a file.
    """
    path = Path(tokenstore)
    return path.is_dir() and any(path.iterdir())


def _run_response(run: scheduler.GarminRun | None) -> GarminRunResponse | None:
    if run is None:
        return None
    return GarminRunResponse(
        started_at=run.started_at,
        finished_at=run.finished_at,
        ok=run.ok,
        running=run.finished_at is None,
        trigger=run.trigger,
        summary=run.summary,
        errors=run.errors,
    )


@router.get("/garmin/status", response_model=GarminStatusResponse)
def garmin_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    run = scheduler.last_run()
    owner = scheduler.resolve_sync_user(db)
    configured = _has_token(settings.garmin_tokenstore)

    # Two failures that look alike in a log and must not look alike in the UI.
    # A dead token is a thing to go and fix; a 429 is a thing to leave alone,
    # and re-logging in to "fix" it is what turns a rate limit into a longer one.
    rate_limited = bool(
        run and not run.ok and any("TooManyRequests" in e for e in run.errors)
    )
    needs_reauth = not configured or bool(run and run.auth_failed)

    return GarminStatusResponse(
        enabled=settings.garmin_sync_enabled,
        configured=configured,
        scheduled_hour=settings.garmin_sync_hour
        if settings.garmin_sync_enabled
        else None,
        timezone=settings.garmin_sync_tz,
        lookback_days=settings.garmin_sync_days,
        sync_username=owner.username if owner else None,
        is_owner=bool(owner and owner.id == current_user.id),
        running=scheduler.is_running(),
        needs_reauth=needs_reauth and not rate_limited,
        rate_limited=rate_limited,
        last_run=_run_response(run),
    )


@router.post("/garmin/sync", status_code=status.HTTP_202_ACCEPTED)
def garmin_sync_now(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a pull and return immediately.

    `sync_user` is a blocking chain of rate-limited requests -- one call each
    for steps and activities, then a pair per day for sleep and hydration -- so
    it cannot run on the request thread. Failures inside it therefore cannot
    become a status code here; they land in `last_run.errors` and the status
    endpoint reports them.
    """
    settings = get_settings()
    if not _has_token(settings.garmin_tokenstore):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No cached Garmin session. Run scripts/garmin_sync.py --login first.",
        )

    owner = scheduler.resolve_sync_user(db)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No account is configured to sync. Set GARMIN_SYNC_USER.",
        )
    # One token store, one account. Letting anyone else trigger it would attach
    # one person's watch data to another person's log.
    if owner.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The Garmin session belongs to a different account.",
        )

    if not scheduler.run_garmin_sync_now():
        response.status_code = status.HTTP_409_CONFLICT
        return {"started": False, "reason": "already_running"}

    return {"started": True, "started_at": datetime.now(timezone.utc)}


class DiagnosticCheck(BaseModel):
    name: str
    result: Literal["pass", "fail", "warn", "info"]
    detail: str


class GarminDiagnosis(BaseModel):
    checked_at: datetime
    checks: list[DiagnosticCheck]


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


@router.get("/garmin/diagnose", response_model=GarminDiagnosis)
def garmin_diagnose(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer "why doesn't the Garmin card work" from the server's side.

    The status endpoint can fail as a whole -- one exception and the client gets
    a bare 500 and nothing else. This runs the same steps one at a time, each in
    its own try, so the one that breaks is named with its exception instead of
    hiding the rest. Including the status endpoint itself, called in-process:
    if *that* is what fails, this is where its error message becomes visible.

    Read-only, and it never logs in to Garmin: the network check is an
    unauthenticated GET, which is not what Garmin rate-limits.
    """
    settings = get_settings()
    checks: list[DiagnosticCheck] = []

    def add(name: str, result: str, detail: str) -> None:
        checks.append(DiagnosticCheck(name=name, result=result, detail=detail))

    # 1. The status endpoint, exactly as the card calls it.
    try:
        garmin_status(db=db, current_user=current_user)
        add("Status endpoint", "pass", "Answers normally.")
    except Exception as exc:  # noqa: BLE001 -- naming the failure is the point
        db.rollback()
        add("Status endpoint", "fail", _error(exc))

    # 2. Schedule.
    try:
        ZoneInfo(settings.garmin_sync_tz)
        zone_ok = True
    except Exception as exc:  # noqa: BLE001
        zone_ok = False
        add(
            "Timezone",
            "fail",
            f"GARMIN_SYNC_TZ={settings.garmin_sync_tz!r}: {_error(exc)}",
        )
    if zone_ok:
        if settings.garmin_sync_tz == "UTC":
            add(
                "Timezone",
                "warn",
                "GARMIN_SYNC_TZ is UTC. Set it to where you live, or the nightly "
                "pull fires in your evening and days roll over early.",
            )
        else:
            add("Timezone", "pass", settings.garmin_sync_tz)
    if not settings.garmin_sync_enabled:
        add(
            "Nightly schedule",
            "info",
            "Off (GARMIN_SYNC_ENABLED is not true). Manual sync still works.",
        )
    else:
        try:
            nxt = scheduler.next_run_time()
            if nxt is None:
                add(
                    "Nightly schedule",
                    "fail",
                    "Enabled, but no scheduler job is running in this process.",
                )
            else:
                add(
                    "Nightly schedule",
                    "pass",
                    f"Next run {nxt.isoformat(timespec='minutes')}",
                )
        except Exception as exc:  # noqa: BLE001
            add("Nightly schedule", "fail", _error(exc))

    # 3. The cached session on disk. Writable matters as much as readable: every
    #    run renews the token and writes it back, and a store it cannot write
    #    works once and then expires.
    store = Path(settings.garmin_tokenstore)
    try:
        if not store.exists():
            add(
                "Token store",
                "fail",
                f"{store} does not exist. Run scripts/garmin_sync.py --login.",
            )
        elif not store.is_dir():
            add("Token store", "fail", f"{store} is not a directory.")
        elif not os.access(store, os.R_OK | os.X_OK):
            add("Token store", "fail", f"{store} is not readable by uid {os.getuid()}.")
        elif not any(store.iterdir()):
            add(
                "Token store",
                "fail",
                f"{store} is empty. Run scripts/garmin_sync.py --login.",
            )
        elif not os.access(store, os.W_OK):
            add(
                "Token store",
                "warn",
                f"{store} is not writable by uid {os.getuid()}, so a renewed token cannot be saved.",
            )
        else:
            add("Token store", "pass", f"{store} holds a session.")
    except Exception as exc:  # noqa: BLE001
        add("Token store", "fail", _error(exc))

    # 4. Whose watch it is.
    try:
        owner = scheduler.resolve_sync_user(db)
        if owner is None:
            add(
                "Sync account",
                "fail",
                "Can't tell which account to sync. Set GARMIN_SYNC_USER to a username.",
            )
        elif owner.id != current_user.id:
            add(
                "Sync account", "info", f"Syncs into {owner.username}'s log, not yours."
            )
        else:
            add("Sync account", "pass", f"Syncs into your log ({owner.username}).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        add("Sync account", "fail", _error(exc))

    # 5. The last run, if this process has seen one.
    run = scheduler.last_run()
    if scheduler.is_running():
        add("Last run", "info", "A sync is running now.")
    elif run is None:
        add("Last run", "info", "None since the server started.")
    elif run.ok:
        add(
            "Last run",
            "pass",
            f"Succeeded at {run.started_at.isoformat(timespec='minutes')}.",
        )
    else:
        errs = "; ".join(run.errors) or "no error recorded"
        add(
            "Last run",
            "fail",
            f"Failed at {run.started_at.isoformat(timespec='minutes')}: {errs}",
        )

    # 6. Can this box reach Garmin at all.
    try:
        r = httpx.get(
            "https://connect.garmin.com/", timeout=5.0, follow_redirects=False
        )
        add(
            "Garmin reachable",
            "pass",
            f"connect.garmin.com answered HTTP {r.status_code}.",
        )
    except Exception as exc:  # noqa: BLE001
        add("Garmin reachable", "fail", _error(exc))

    return GarminDiagnosis(checked_at=datetime.now(timezone.utc), checks=checks)
