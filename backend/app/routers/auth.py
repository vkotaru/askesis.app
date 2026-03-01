from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta

from app.database import get_db
from app.config import get_settings
from app.models import User

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
        client_kwargs={"scope": "openid email profile"},
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


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


@router.get("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    # Dev mode: auto-login
    if settings.dev_mode:
        user = get_or_create_dev_user(db)
        access_token = create_access_token({"sub": user.email})
        response = RedirectResponse(url="/")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=7 * 24 * 60 * 60,
            samesite="lax",
        )
        return response

    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    if settings.dev_mode:
        return RedirectResponse(url="/")

    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    email = user_info["email"]

    # Check if email is allowed
    if settings.allowed_emails and email not in settings.allowed_emails:
        raise HTTPException(status_code=403, detail="Email not authorized")

    # Get or create user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            name=user_info.get("name", ""),
            picture=user_info.get("picture"),
        )
        db.add(user)
        db.commit()

    # Create JWT and set cookie
    access_token = create_access_token({"sub": email})
    response = RedirectResponse(url="/")
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,  # 7 days
        samesite="lax",
    )
    return response


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
