import io
import logging
import uuid
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIC support optional

from app.config import get_settings
from app.database import get_db
from app.models import User, ProgressPhoto, PhotoView
from app.routers.auth import get_current_user, check_view_permission
from app import google_drive
from app.encryption import get_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class PhotoResponse(BaseModel):
    id: int
    date: date
    view: str
    file_path: str | None  # Legacy, may be None for Drive-stored photos
    drive_file_id: str | None  # Google Drive file ID
    notes: str | None
    url: str

    class Config:
        from_attributes = True


def process_image_bytes(
    content: bytes, max_size: int = 1200, quality: int = 85
) -> bytes:
    """Process uploaded image: resize, optimize, convert to JPEG. Returns bytes."""
    img = Image.open(io.BytesIO(content))

    # Fix rotation based on EXIF
    img = ImageOps.exif_transpose(img)

    # Convert to RGB if needed
    if img.mode in ("RGBA", "P", "CMYK"):
        img = img.convert("RGB")

    # Resize if too large (maintain aspect ratio)
    if img.size[0] > max_size or img.size[1] > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Save as optimized JPEG to bytes
    output = io.BytesIO()
    img.save(output, "JPEG", quality=quality, optimize=True)
    output.seek(0)
    return output.read()


def require_drive_access(user: User):
    """Ensure user has Google Drive access configured."""
    if not user.google_refresh_token:
        raise HTTPException(
            status_code=403,
            detail="Google Drive access not configured. Please log out and log in again to grant Drive permissions.",
        )


@router.get("/", response_model=list[PhotoResponse])
def get_photos(
    start_date: date | None = None,
    end_date: date | None = None,
    view: PhotoView | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "photos", db, current_user)
    query = (
        db.query(ProgressPhoto)
        .filter(ProgressPhoto.user_id == target_user.id)
        .filter(ProgressPhoto.deleted_at.is_(None))
    )

    if start_date:
        query = query.filter(ProgressPhoto.date >= start_date)
    if end_date:
        query = query.filter(ProgressPhoto.date <= end_date)
    if view:
        query = query.filter(ProgressPhoto.view == view)

    photos = query.order_by(ProgressPhoto.date.desc()).offset(offset).limit(limit).all()

    return [
        PhotoResponse(
            id=p.id,
            date=p.date,
            view=p.view.value,
            file_path=p.file_path,
            drive_file_id=p.drive_file_id,
            notes=p.notes,
            url=f"/api/photos/file/{p.id}",
        )
        for p in photos
    ]


@router.get("/date/{photo_date}", response_model=list[PhotoResponse])
def get_photos_by_date(
    photo_date: date,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "photos", db, current_user)
    photos = (
        db.query(ProgressPhoto)
        .filter(
            ProgressPhoto.user_id == target_user.id, ProgressPhoto.date == photo_date
        )
        .filter(ProgressPhoto.deleted_at.is_(None))
        .all()
    )

    return [
        PhotoResponse(
            id=p.id,
            date=p.date,
            view=p.view.value,
            file_path=p.file_path,
            drive_file_id=p.drive_file_id,
            notes=p.notes,
            url=f"/api/photos/file/{p.id}",
        )
        for p in photos
    ]


@router.get("/drive-status")
def get_drive_status(
    current_user: User = Depends(get_current_user),
):
    """Check if user has Google Drive configured and working."""
    if not current_user.google_refresh_token:
        return {
            "configured": False,
            "working": False,
            "message": "Please log out and log in again to enable photo storage.",
        }

    try:
        working = google_drive.check_drive_access(get_refresh_token(current_user))
        return {
            "configured": True,
            "working": working,
            "message": "Google Drive connected"
            if working
            else "Drive access expired, please re-login",
        }
    except Exception as e:
        return {"configured": True, "working": False, "message": str(e)}


@router.post("/drive/disconnect")
def disconnect_drive(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke Google Drive access and clear the stored refresh token."""
    token = get_refresh_token(current_user)
    if token:
        # Attempt to revoke the token with Google
        try:
            resp = httpx.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                logger.info(f"Revoked Google token for user {current_user.email}")
            else:
                logger.warning(
                    f"Google revoke returned {resp.status_code} for user {current_user.email}"
                )
        except Exception as e:
            logger.warning(f"Failed to revoke Google token: {e}")

    # Clear token from database regardless of revoke result
    current_user.google_refresh_token = None
    db.commit()
    return {"message": "Google Drive disconnected"}


@router.post("/upload", response_model=PhotoResponse)
async def upload_photo(
    file: UploadFile = File(...),
    photo_date: date = Form(...),
    view: PhotoView = Form(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    require_drive_access(current_user)

    # Validate file type
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, detail="Invalid file type. Use JPEG, PNG, HEIC, or WebP."
        )

    # Read and check file size
    content = await file.read()
    if len(content) > settings.max_image_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_image_size // (1024 * 1024)}MB",
        )

    # Check if photo already exists for this date/view
    existing = (
        db.query(ProgressPhoto)
        .filter(
            ProgressPhoto.user_id == current_user.id,
            ProgressPhoto.date == photo_date,
            ProgressPhoto.view == view,
        )
        .filter(ProgressPhoto.deleted_at.is_(None))
        .first()
    )

    # Process image (resize, optimize, convert to JPEG)
    try:
        processed_content = process_image_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")

    # Generate unique filename for Drive
    filename = f"askesis_{current_user.id}_{photo_date.isoformat()}_{view.value}_{uuid.uuid4().hex[:8]}.jpg"

    # Resolve the pinned Askesis folder once (creates + caches on first use)
    try:
        askesis_folder_id = google_drive.resolve_askesis_folder_id(db, current_user)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to resolve Askesis folder: {e}"
        )

    # Upload to Google Drive
    try:
        drive_file_id = google_drive.upload_photo(
            get_refresh_token(current_user),
            processed_content,
            filename,
            askesis_folder_id=askesis_folder_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload to Google Drive: {e}"
        )

    # Delete old photo from Drive if replacing
    if existing and existing.drive_file_id:
        try:
            google_drive.delete_photo(
                get_refresh_token(current_user), existing.drive_file_id
            )
        except Exception:
            pass  # Ignore errors deleting old file

        # Update existing record
        existing.drive_file_id = drive_file_id
        existing.file_path = None  # Clear legacy path
        existing.notes = notes
        db.commit()
        db.refresh(existing)
        photo = existing
    else:
        # Create new record
        photo = ProgressPhoto(
            user_id=current_user.id,
            date=photo_date,
            view=view,
            drive_file_id=drive_file_id,
            file_path=None,
            notes=notes,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)

    return PhotoResponse(
        id=photo.id,
        date=photo.date,
        view=photo.view.value,
        file_path=photo.file_path,
        drive_file_id=photo.drive_file_id,
        notes=photo.notes,
        url=f"/api/photos/file/{photo.id}",
    )


@router.get("/file/{photo_id}")
def get_photo_file(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = db.query(ProgressPhoto).filter(ProgressPhoto.id == photo_id).first()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Check permission - allow owner or shared users
    if photo.user_id != current_user.id:
        check_view_permission(photo.user_id, "photos", db, current_user)

    # Get the photo owner for their refresh token
    owner = db.query(User).filter(User.id == photo.user_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Photo owner not found")

    # Download from Google Drive
    if photo.drive_file_id:
        if not owner.google_refresh_token:
            raise HTTPException(
                status_code=500, detail="Photo owner's Drive access expired"
            )

        try:
            content = google_drive.download_photo(
                get_refresh_token(owner), photo.drive_file_id
            )
            return Response(content=content, media_type="image/jpeg")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to download from Google Drive: {e}"
            )

    # Legacy: file stored locally (should not happen for new photos)
    if photo.file_path:
        file_path = Path(photo.file_path)
        if file_path.exists():
            return Response(content=file_path.read_bytes(), media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Photo file not found")


@router.delete("/{photo_id}")
def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = (
        db.query(ProgressPhoto)
        .filter(ProgressPhoto.id == photo_id, ProgressPhoto.user_id == current_user.id)
        .filter(ProgressPhoto.deleted_at.is_(None))
        .first()
    )

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.deleted_at = datetime.utcnow()
    db.commit()

    return {"ok": True}
