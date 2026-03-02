import os
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIC support optional

from app.database import get_db
from app.models import User, ProgressPhoto, PhotoView
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

# Upload directory
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "photos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class PhotoResponse(BaseModel):
    id: int
    date: date
    view: str
    file_path: str
    notes: str | None
    url: str

    class Config:
        from_attributes = True


def process_image(file_path: Path, max_size: int = 1200, quality: int = 85) -> Path:
    """Process uploaded image: resize, optimize, convert to JPEG."""
    img = Image.open(file_path)

    # Fix rotation based on EXIF
    img = ImageOps.exif_transpose(img)

    # Convert to RGB if needed
    if img.mode in ("RGBA", "P", "CMYK"):
        img = img.convert("RGB")

    # Resize if too large (maintain aspect ratio)
    if img.size[0] > max_size or img.size[1] > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Save as optimized JPEG
    output_path = file_path.with_suffix(".jpg")
    img.save(output_path, "JPEG", quality=quality, optimize=True)

    # Remove original if different
    if output_path != file_path and file_path.exists():
        file_path.unlink()

    return output_path


@router.get("/", response_model=list[PhotoResponse])
def get_photos(
    start_date: date | None = None,
    end_date: date | None = None,
    view: PhotoView | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "photos", db, current_user)
    query = db.query(ProgressPhoto).filter(ProgressPhoto.user_id == target_user.id)

    if start_date:
        query = query.filter(ProgressPhoto.date >= start_date)
    if end_date:
        query = query.filter(ProgressPhoto.date <= end_date)
    if view:
        query = query.filter(ProgressPhoto.view == view)

    photos = query.order_by(ProgressPhoto.date.desc()).all()

    return [
        PhotoResponse(
            id=p.id,
            date=p.date,
            view=p.view.value,
            file_path=p.file_path,
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
    photos = db.query(ProgressPhoto).filter(
        ProgressPhoto.user_id == target_user.id,
        ProgressPhoto.date == photo_date
    ).all()

    return [
        PhotoResponse(
            id=p.id,
            date=p.date,
            view=p.view.value,
            file_path=p.file_path,
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
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Use JPEG, PNG, HEIC, or WebP.")

    # Check if photo already exists for this date/view
    existing = db.query(ProgressPhoto).filter(
        ProgressPhoto.user_id == current_user.id,
        ProgressPhoto.date == photo_date,
        ProgressPhoto.view == view
    ).first()

    # Generate unique filename
    file_ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    unique_name = f"{current_user.id}_{photo_date.isoformat()}_{view.value}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = UPLOAD_DIR / unique_name

    # Save uploaded file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Process image (resize, optimize)
    try:
        processed_path = process_image(file_path)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")

    # Delete old photo file if replacing
    if existing and existing.file_path:
        old_path = Path(existing.file_path)
        if old_path.exists():
            old_path.unlink()

        # Update existing record
        existing.file_path = str(processed_path)
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
            file_path=str(processed_path),
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

    file_path = Path(photo.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo file not found")

    return FileResponse(file_path, media_type="image/jpeg")


@router.delete("/{photo_id}")
def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = db.query(ProgressPhoto).filter(
        ProgressPhoto.id == photo_id,
        ProgressPhoto.user_id == current_user.id
    ).first()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Delete file
    file_path = Path(photo.file_path)
    if file_path.exists():
        file_path.unlink()

    # Delete record
    db.delete(photo)
    db.commit()

    return {"ok": True}
