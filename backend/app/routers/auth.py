import calendar
import json
import logging
import threading
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, update
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta

from app.database import get_db
from app.config import get_settings
from app.models import User, DataShare
from app.security import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    hash_password,
    verify_password,
)

logger = logging.getLogger("askesis.auth")

router = APIRouter()
settings = get_settings()


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.token_expire_hours)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


# ── Password-change token epoch ──────────────────────────────────────────────
# A token is good for token_expire_hours (720 = 30 days) and /refresh will
# still take one that expired up to _REFRESH_GRACE_DAYS ago, so without this a
# leaked cookie outlives a password change by more than a month — which is the
# one thing a password change is supposed to stop. Every token carries the
# issuing user's password_changed_at as `pwd_at`; a token stamped before the
# current value is dead.

_PWD_EPOCH_CLAIM = "pwd_at"


def _password_epoch(user: User) -> int | None:
    """`user.password_changed_at` as whole UTC seconds, or None if never set.

    `calendar.timegm` and not `.timestamp()`: the column holds a naive UTC
    datetime (everything here writes `datetime.utcnow()`), and `.timestamp()`
    would read a naive value as *local* time and shift it by the host's offset.
    """
    changed_at = user.password_changed_at
    if changed_at is None:
        return None
    return calendar.timegm(changed_at.utctimetuple())


def _advance_password_epoch(user: User) -> datetime:
    """The value to stamp on `user` now, guaranteed to be a *newer* epoch.

    The claim is whole seconds, so two password changes inside the same second
    would compare equal and the first one's tokens would survive the second.
    Rare, but the fix is one comparison: if wall-clock hasn't moved on far
    enough, step past the previous value instead.
    """
    now = datetime.utcnow()
    previous = user.password_changed_at
    if previous is not None and calendar.timegm(now.utctimetuple()) <= calendar.timegm(
        previous.utctimetuple()
    ):
        return previous + timedelta(seconds=1)
    return now


def _token_claims(user: User) -> dict:
    """The claim set for a token issued to `user`."""
    claims: dict = {"sub": user.email}
    epoch = _password_epoch(user)
    if epoch is not None:
        claims[_PWD_EPOCH_CLAIM] = epoch
    return claims


def _token_epoch_is_current(payload: dict, user: User) -> bool:
    """False if `payload` was issued before the user's last password change.

    The NULL case is deliberately permissive: an account that has not touched
    its password since this column existed has no epoch to compare against, so
    its outstanding sessions — which carry no `pwd_at` at all — stay valid.
    That is what makes deploying this a non-event rather than a forced
    re-login for everyone. The moment a password is set or changed the column
    is stamped and unstamped tokens start failing.
    """
    epoch = _password_epoch(user)
    if epoch is None:
        return True

    stamped = payload.get(_PWD_EPOCH_CLAIM)
    if not isinstance(stamped, int) or isinstance(stamped, bool):
        return False
    return stamped >= epoch


def set_auth_cookie(response, access_token: str) -> None:
    """Set secure auth cookie with appropriate flags."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=settings.token_expire_hours * 60 * 60,
        samesite="strict",
        secure=not settings.dev_mode,  # HTTPS only in production
    )


def clear_auth_cookie(response) -> None:
    """Clear the auth cookie, mirroring the flags set_auth_cookie used.

    Browsers match a deletion on name/path/domain, so a bare delete_cookie
    does work — but it emits SameSite=lax with no Secure/HttpOnly, which
    reads like a different cookie. Keep the two symmetrical.
    """
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="strict",
        secure=not settings.dev_mode,
    )


def get_or_create_dev_user(db: Session) -> User:
    """Get or create a dev user for local development."""
    dev_email = "dev@askesis.local"
    user = db.query(User).filter(User.email == dev_email).first()
    if not user:
        user = User(
            email=dev_email,
            name="Dev User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    # Dev mode: return dev user without auth
    if settings.dev_mode:
        return get_or_create_dev_user(db)

    # The httponly cookie is the only session mechanism: the web app is the
    # only client, and it is served same-origin with the API.
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        email = payload.get("sub")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not _token_epoch_is_current(payload, user):
        raise HTTPException(status_code=401, detail="Session ended by password change")

    return user


def check_view_permission(
    user_id: int | None,
    category: str,
    db: Session,
    current_user: User,
) -> User:
    """
    Check if current_user has permission to view user_id's data for the given category.
    Returns the target user if permission granted, raises 403 otherwise.
    If user_id is None, returns current_user (viewing own data).
    """
    if user_id is None or user_id == current_user.id:
        return current_user

    # Check if a share exists
    share = (
        db.query(DataShare)
        .filter(
            DataShare.owner_id == user_id,
            DataShare.shared_with_id == current_user.id,
        )
        .first()
    )

    if not share:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if category is in shared categories (supports JSON or legacy comma-separated)
    if share.categories and share.categories.startswith("["):
        try:
            categories = json.loads(share.categories)
        except json.JSONDecodeError:
            categories = share.categories.split(",")
    else:
        categories = share.categories.split(",") if share.categories else []
    if category not in categories:
        raise HTTPException(status_code=403, detail=f"No access to {category}")

    # Get target user
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    return target_user


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "username": current_user.username,
    }


# Accept tokens that expired up to this long ago, as long as the signature is
# still valid and the user still exists. Lets a client that's been offline for
# a few days come back online and silently refresh instead of bouncing the user
# to a full re-login.
_REFRESH_GRACE_DAYS = 7


@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    """Re-issue an access token from a still-valid-or-recently-expired one.

    Reads the token from the access_token cookie and re-sets that cookie. The
    token is also returned in the body for callers that want to inspect it.
    """
    if settings.dev_mode:
        user = get_or_create_dev_user(db)
        new_token = create_access_token(_token_claims(user))
        response = JSONResponse({"access_token": new_token})
        set_auth_cookie(response, new_token)
        return response

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No token to refresh")

    try:
        # Decode with leeway so a token that expired within the grace window
        # is still accepted. Signature validation is the real authentication.
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        email = payload.get("sub")
        exp = payload.get("exp")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not email or not isinstance(exp, int):
        raise HTTPException(status_code=401, detail="Malformed token")

    expired_at = datetime.utcfromtimestamp(exp)
    if datetime.utcnow() - expired_at > timedelta(days=_REFRESH_GRACE_DAYS):
        raise HTTPException(status_code=401, detail="Token expired beyond grace window")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Refresh is the longest-lived path in the app (grace window on top of a
    # 30-day token), so it has to honour the epoch too — otherwise a session
    # killed on /me could simply re-mint itself here.
    if not _token_epoch_is_current(payload, user):
        raise HTTPException(status_code=401, detail="Session ended by password change")

    new_token = create_access_token(_token_claims(user))
    response = JSONResponse({"access_token": new_token})
    set_auth_cookie(response, new_token)
    return response


# ── Username + password auth ─────────────────────────────────────────────────
# The only way in. The JWT `sub` is the email, so cookies issued by the older
# Google flow stay valid until they expire.

# pydantic's max_length counts *characters*; bcrypt truncates at 72 *bytes*.
# Characters <= bytes, so this bound is necessary but not sufficient —
# hash_password() re-checks the encoded length and raises.
_PASSWORD_FIELD = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    # No length floor on login: an old password shorter than today's minimum
    # must still be able to sign in and then change itself.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)
    new_password: str = _PASSWORD_FIELD


class SetInitialPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = _PASSWORD_FIELD


# Deliberately identical for "no such user" and "wrong password" so the
# response body doesn't reveal whether an account exists.
_BAD_CREDENTIALS = "Incorrect username or password"

# The one deliberate exception to that. Accounts that predate password auth
# (they signed in with Google) carry password_hash = NULL and cannot log in at
# all, so the login form has to be able to say "claim this one". That does leak
# "an unclaimed account exists for this identifier" — acceptable on a
# tailnet-private app, and strictly limited to accounts with no password: the
# moment a hash exists the account falls back to the generic 401 above.
_PASSWORD_NOT_SET = "This account has no password yet. Set one to finish signing in."

# Returned by /set-initial-password for both "no such account" and "that
# account already has a password". Keeping them identical means the claim
# endpoint is no more of an oracle than it has to be — and, more importantly,
# it is never a password *reset*: a claimed account can only be changed through
# /change-password, which requires the current password.
_CANNOT_CLAIM = "That account cannot set an initial password."


# ── Failed-attempt throttle ──────────────────────────────────────────────────
# In-process, no dependency, no storage: a deque of recent failure timestamps
# per identifier. bcrypt is otherwise the only brake on guessing, and since
# these handlers are `async def`, hashing runs on the event loop and serialises
# — so an attacker gets a few attempts a second and nothing ever says stop.
#
# Keyed on the submitted identifier, NOT the client IP. The app sits behind a
# Tailscale sidecar; if it ever stops setting X-Forwarded-For, every request
# shares one apparent IP and an IP-keyed limiter locks out the whole household
# at once. Identifier-keyed lets someone deliberately lock a known username out
# for the window — on a tailnet-only box, where reaching this endpoint already
# means being on the tailnet, that is the better trade.
#
# Process-local state, so it resets on restart and would be per-worker if the
# server ever ran more than one. Both are acceptable: this is a brake, not an
# access control.
_THROTTLE_WINDOW_SECONDS = 15 * 60
_THROTTLE_MAX_FAILURES = 10
_THROTTLE_MAX_KEYS = 1024

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _throttle_key(identifier: str) -> str:
    return identifier.strip().lower()[:255]


def _recent(stamps: list[float], now: float) -> list[float]:
    return [t for t in stamps if now - t < _THROTTLE_WINDOW_SECONDS]


def _enforce_throttle(identifier: str) -> None:
    """429 if this identifier has failed too often lately. Call before bcrypt."""
    key = _throttle_key(identifier)
    now = time.monotonic()
    with _failures_lock:
        stamps = _recent(_failures.get(key, []), now)
        if stamps:
            _failures[key] = stamps
        else:
            _failures.pop(key, None)
        if len(stamps) < _THROTTLE_MAX_FAILURES:
            return
        retry_after = int(_THROTTLE_WINDOW_SECONDS - (now - stamps[0])) + 1

    logger.warning("Throttled auth attempts for identifier=%s", key)
    raise HTTPException(
        status_code=429,
        detail="Too many attempts. Try again later.",
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def _record_failure(identifier: str) -> None:
    key = _throttle_key(identifier)
    now = time.monotonic()
    with _failures_lock:
        # Bound the table so a script cycling through identifiers can't grow it
        # without limit: drop every key whose failures have all aged out, and
        # if that wasn't enough, start over. Losing counters only ever costs
        # strictness, never correctness.
        if len(_failures) >= _THROTTLE_MAX_KEYS:
            for stale, stamps in list(_failures.items()):
                if not _recent(stamps, now):
                    del _failures[stale]
            if len(_failures) >= _THROTTLE_MAX_KEYS:
                _failures.clear()
        _failures[key] = _recent(_failures.get(key, []), now) + [now]


def _clear_failures(identifier: str) -> None:
    """A successful sign-in wipes the identifier's history."""
    with _failures_lock:
        _failures.pop(_throttle_key(identifier), None)


@router.post("/login")
async def password_login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Sign in with a username (or email) and password.

    Returns JSON rather than a redirect so the SPA stays mounted.
    """
    identifier = payload.username.strip()
    _enforce_throttle(identifier)

    user = (
        db.query(User)
        .filter(or_(User.username == identifier, User.email == identifier))
        .first()
    )

    # An account that exists but has never had a password set can't ever
    # satisfy the check below, so tell the client to offer the claim flow
    # instead of bouncing it off an unwinnable 401. Machine-readable `code` so
    # the SPA branches on that and not on prose.
    if user is not None and user.password_hash is None:
        return JSONResponse(
            status_code=409,
            content={"detail": _PASSWORD_NOT_SET, "code": "password_not_set"},
        )

    # verify_password burns a bcrypt round against a dummy hash when the user
    # is missing, so timing doesn't leak account existence.
    stored_hash = user.password_hash if user else None
    if not verify_password(payload.password, stored_hash):
        _record_failure(identifier)
        raise HTTPException(status_code=401, detail=_BAD_CREDENTIALS)

    _clear_failures(identifier)
    return _login_response(user)


def _login_response(user: User) -> JSONResponse:
    """The signed-in response: user JSON plus the session cookie."""
    access_token = create_access_token(_token_claims(user))
    response = JSONResponse(
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "username": user.username,
        }
    )
    set_auth_cookie(response, access_token)
    return response


@router.post("/set-initial-password")
async def set_initial_password(
    payload: SetInitialPasswordRequest, db: Session = Depends(get_db)
):
    """Claim an account that has never had a password (the Google-era rows).

    Strictly one-shot per account: it is gated on ``password_hash IS NULL``, so
    once a password exists this endpoint can never touch the account again.
    This is **not** a password reset and must never become one — there is no
    email round-trip here, so anything it could overwrite would be a takeover.
    """
    identifier = payload.username.strip()
    _enforce_throttle(identifier)

    user = (
        db.query(User)
        .filter(or_(User.username == identifier, User.email == identifier))
        .first()
    )

    if user is None or user.password_hash is not None:
        # Nothing to guess here, but a rejected claim is still a probe for
        # "which accounts are unclaimed", so it counts against the window.
        _record_failure(identifier)
        raise HTTPException(status_code=409, detail=_CANNOT_CLAIM)

    try:
        new_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Re-assert `password_hash IS NULL` in the UPDATE itself rather than
    # trusting the SELECT above. Two claims racing on the same unclaimed
    # account would both pass that check and the later commit would silently
    # win, handing the account to whoever wrote last. As a conditional update
    # the database decides: exactly one statement matches a row, and the loser
    # sees rowcount 0 and gets the same 409 as any other unclaimable account.
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.password_hash.is_(None))
        .values(
            password_hash=new_hash,
            password_changed_at=_advance_password_epoch(user),
        )
    )
    db.commit()

    if result.rowcount != 1:
        _record_failure(identifier)
        raise HTTPException(status_code=409, detail=_CANNOT_CLAIM)

    _clear_failures(identifier)

    # The ORM copy still holds the pre-UPDATE values; _login_response needs the
    # freshly stamped epoch to put in the token.
    db.refresh(user)

    # Visible in `docker compose logs`: the one event where an account gains a
    # password without anyone proving they already had one.
    logger.info(
        "Initial password claimed for user id=%s username=%s email=%s",
        user.id,
        user.username,
        user.email,
    )

    # Log them straight in — same shape as /login, so the SPA reuses its
    # post-login bootstrap.
    return _login_response(user)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    try:
        current_user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Advancing the epoch invalidates every token issued before now — the
    # other browser, the phone, the cookie someone copied. Including this
    # caller's own, which is why the response re-issues the cookie: the tab
    # that did the change stays signed in, everything else has to log in again.
    current_user.password_changed_at = _advance_password_epoch(current_user)
    db.commit()
    db.refresh(current_user)

    response = JSONResponse({"status": "ok"})
    set_auth_cookie(response, create_access_token(_token_claims(current_user)))
    return response


@router.post("/logout")
async def logout_post():
    """Fetch-based sign-out: clears the auth cookie."""
    response = JSONResponse({"status": "ok"})
    clear_auth_cookie(response)
    return response
