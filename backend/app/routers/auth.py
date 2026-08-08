import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
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

# Only set up OAuth if not in dev mode
if not settings.dev_mode:
    from authlib.integrations.starlette_client import OAuth

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            # Request Drive + Sheets scopes for photo storage and export
            "scope": "openid email profile https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets",
        },
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.token_expire_hours)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


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
            picture=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    # Dev mode: return dev user without auth
    if settings.dev_mode:
        return get_or_create_dev_user(db)

    # Bearer header takes precedence (mobile clients); fall back to cookie (web)
    token: str | None = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
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


@router.get("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    # Dev mode: auto-login
    if settings.dev_mode:
        user = get_or_create_dev_user(db)
        access_token = create_access_token({"sub": user.email})
        response = RedirectResponse(url="/")
        set_auth_cookie(response, access_token)
        return response

    redirect_uri = request.url_for("auth_callback")
    # Force HTTPS in production (behind reverse proxy)
    redirect_uri = str(redirect_uri).replace("http://", "https://")

    # Check if user needs refresh token (force_consent param)
    force_consent = request.query_params.get("force_consent") == "true"

    # Request offline access to get refresh token for Drive API
    # Only force consent if explicitly requested (e.g., when user needs Drive access)
    oauth_params = {"access_type": "offline"}
    if force_consent:
        oauth_params["prompt"] = "consent"

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        **oauth_params,
    )


def _upsert_user_from_google(db: Session, token: dict) -> User:
    """Apply a Google OAuth token to the users table. Returns the user."""
    user_info = token.get("userinfo") or {}

    logger.info(f"OAuth token keys: {list(token.keys())}")
    logger.info(f"Refresh token present: {'refresh_token' in token}")

    email = user_info["email"]

    if settings.allowed_emails and email not in settings.allowed_emails:
        raise HTTPException(status_code=403, detail="Email not authorized")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            name=user_info.get("name", ""),
            picture=user_info.get("picture"),
        )
        db.add(user)

    refresh_token = token.get("refresh_token")
    if refresh_token:
        from app.encryption import encrypt_token

        user.google_refresh_token = encrypt_token(refresh_token)
        logger.info(f"Saved encrypted refresh token for user {email}")
    else:
        logger.warning(f"No refresh token received for user {email}")

    db.commit()
    db.refresh(user)
    return user


@router.get("/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    if settings.dev_mode:
        return RedirectResponse(url="/")

    token = await oauth.google.authorize_access_token(request)
    user = _upsert_user_from_google(db, token)

    access_token = create_access_token({"sub": user.email})
    response = RedirectResponse(url="/")
    set_auth_cookie(response, access_token)
    return response


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


# Accept tokens that expired up to this long ago, as long as the signature is
# still valid and the user still exists. Lets a mobile client that's been
# offline for a few days come back online and silently refresh instead of
# bouncing the user to a full re-login.
_REFRESH_GRACE_DAYS = 7


@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    """Re-issue an access token from a still-valid-or-recently-expired one.

    Accepts the token from the Authorization header (mobile) or the
    access_token cookie (web). On success returns {"access_token": "..."} and
    also refreshes the cookie for web callers.
    """
    if settings.dev_mode:
        user = get_or_create_dev_user(db)
        new_token = create_access_token({"sub": user.email})
        response = JSONResponse({"access_token": new_token})
        set_auth_cookie(response, new_token)
        return response

    token: str | None = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
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

    new_token = create_access_token({"sub": email})
    response = JSONResponse({"access_token": new_token})
    set_auth_cookie(response, new_token)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    clear_auth_cookie(response)
    return response


# ── Username + password auth ─────────────────────────────────────────────────
# Added alongside Google OAuth, not in place of it. The JWT `sub` stays the
# email for both paths, so `get_current_user` needs no change and cookies
# issued before this shipped stay valid.

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


# Deliberately identical for "no such user" and "wrong password" so the
# response body doesn't reveal whether an account exists.
_BAD_CREDENTIALS = "Incorrect username or password"


@router.post("/login")
async def password_login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Sign in with a username (or email) and password.

    Returns JSON rather than a redirect so the SPA stays mounted.
    """
    identifier = payload.username.strip()

    user = (
        db.query(User)
        .filter(or_(User.username == identifier, User.email == identifier))
        .first()
    )

    # verify_password burns a bcrypt round against a dummy hash when the user
    # is missing or has no password set, so timing doesn't leak account
    # existence.
    stored_hash = user.password_hash if user else None
    if not verify_password(payload.password, stored_hash):
        raise HTTPException(status_code=401, detail=_BAD_CREDENTIALS)

    access_token = create_access_token({"sub": user.email})
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

    db.commit()
    return {"status": "ok"}


@router.post("/logout")
async def logout_post():
    """POST counterpart to GET /auth/logout, for fetch-based sign-out."""
    response = JSONResponse({"status": "ok"})
    clear_auth_cookie(response)
    return response
