import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta

from app.database import get_db
from app.config import get_settings
from app.models import User, DataShare

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


@router.get("/mobile/login")
async def mobile_login(request: Request, db: Session = Depends(get_db)):
    """Start OAuth from a Capacitor/native client.

    On success, the callback redirects to the app's deep link with a
    `#token=<jwt>` fragment instead of setting a cookie.
    """
    if settings.dev_mode:
        # In dev, hand back a token immediately so we can test the deep-link flow.
        user = get_or_create_dev_user(db)
        access_token = create_access_token({"sub": user.email})
        return RedirectResponse(
            url=f"{settings.mobile_redirect_uri}#token={access_token}"
        )

    redirect_uri = request.url_for("mobile_auth_callback")
    redirect_uri = str(redirect_uri).replace("http://", "https://")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        access_type="offline",
    )


@router.get("/mobile/callback", name="mobile_auth_callback")
async def mobile_auth_callback(request: Request, db: Session = Depends(get_db)):
    if settings.dev_mode:
        user = get_or_create_dev_user(db)
        access_token = create_access_token({"sub": user.email})
        return RedirectResponse(
            url=f"{settings.mobile_redirect_uri}#token={access_token}"
        )

    token = await oauth.google.authorize_access_token(request)
    user = _upsert_user_from_google(db, token)

    access_token = create_access_token({"sub": user.email})
    # Hand the JWT to the app via deep link. Fragment (#) keeps the token out of
    # server logs / browser history more reliably than a query string.
    return RedirectResponse(
        url=f"{settings.mobile_redirect_uri}#token={access_token}"
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
