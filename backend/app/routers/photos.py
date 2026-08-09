import io
import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIC support optional

from app import storage
from app.config import get_settings
from app.database import get_db
from app.models import User, ProgressPhoto, PhotoView
from app.routers.auth import get_current_user, check_view_permission

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class PhotoResponse(BaseModel):
    id: int
    date: date
    view: str
    # No file_path: the client reads photos through `url` and never needs the
    # on-disk location, which would leak the server's filesystem layout.
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
            notes=p.notes,
            url=f"/api/photos/file/{p.id}",
        )
        for p in photos
    ]


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

    # Filename format is load-bearing: scripts/adopt_photos.py parses user id,
    # date and view back out of it to match hand-copied files to rows.
    filename = f"askesis_{current_user.id}_{photo_date.isoformat()}_{view.value}_{uuid.uuid4().hex[:8]}.jpg"

    # Write to the server's own disk. Store the RELATIVE path.
    try:
        stored_path = storage.save_media(
            storage.PHOTOS_BUCKET, filename, processed_content
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store photo: {e}")

    if existing:
        # Replacing: drop the superseded file before repointing the row, or it
        # is orphaned on disk with nothing referencing it.
        old_path = existing.file_path
        existing.file_path = stored_path
        existing.notes = notes
        db.commit()
        db.refresh(existing)
        photo = existing
        if old_path and old_path != stored_path:
            storage.delete_media(old_path, storage.PHOTOS_BUCKET)
    else:
        # Create new record
        photo = ProgressPhoto(
            user_id=current_user.id,
            date=photo_date,
            view=view,
            file_path=stored_path,
            notes=notes,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)

    return PhotoResponse(
        id=photo.id,
        date=photo.date,
        view=photo.view.value,
        notes=photo.notes,
        url=f"/api/photos/file/{photo.id}",
    )


@router.get("/file/{photo_id}")
def get_photo_file(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = (
        db.query(ProgressPhoto)
        .filter(ProgressPhoto.id == photo_id)
        # Match get_photos: a soft-deleted photo must not stay fetchable by id.
        .filter(ProgressPhoto.deleted_at.is_(None))
        .first()
    )

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Check permission - allow owner or shared users
    if photo.user_id != current_user.id:
        check_view_permission(photo.user_id, "photos", db, current_user)

    # The server's own disk is the only photo store. FileResponse streams and
    # sets ETag/Last-Modified, which the service worker's CacheFirst rule on
    # /api/photos/file/* relies on.
    if photo.file_path:
        path = storage.resolve_media_path(photo.file_path, storage.PHOTOS_BUCKET)
        if path.is_file():
            return FileResponse(path, media_type="image/jpeg")

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

    # Soft delete only: the row is still handed to clients by /api/sync/changes
    # so they can tombstone their local copy, and unlinking the file here would
    # make an undelete unrecoverable. Files are reclaimed out-of-band, not here.
    photo.deleted_at = datetime.utcnow()
    db.commit()

    return {"ok": True}
