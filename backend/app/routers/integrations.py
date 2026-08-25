"""Read and drive the Garmin import from the app, instead of from a shell.

Deliberately narrow. This reports what the importer did and lets you start it
by hand; it does **not** log in. Connecting an account stays
`scripts/garmin_sync.py --login`, because the login is interactive (MFA), is
rate-limited by IP, and would mean this app accepting a Garmin password --
which v1.0.0 removed the ability to store on purpose. What the UI adds is a
diagnosis: when the cached token is gone, `needs_reauth` says so and the client
shows the command to run.
"""

from datetime import datetime, timezone
from pathlib import Path

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
