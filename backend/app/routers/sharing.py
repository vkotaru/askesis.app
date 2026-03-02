from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, DataShare
from app.routers.auth import get_current_user

router = APIRouter()

VALID_CATEGORIES = {"daily_logs", "nutrition", "activities", "measurements", "photos"}


class ShareCreate(BaseModel):
    shared_with_email: str
    categories: list[str]


class ShareUpdate(BaseModel):
    categories: list[str]


class ShareResponse(BaseModel):
    id: int
    shared_with_id: int
    shared_with_name: str
    shared_with_email: str
    shared_with_picture: str | None
    categories: list[str]

    class Config:
        from_attributes = True


class SharedWithMeResponse(BaseModel):
    id: int
    owner_id: int
    owner_name: str
    owner_email: str
    owner_picture: str | None
    categories: list[str]


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    picture: str | None

    class Config:
        from_attributes = True


def share_to_response(share: DataShare) -> ShareResponse:
    return ShareResponse(
        id=share.id,
        shared_with_id=share.shared_with_id,
        shared_with_name=share.shared_with.name,
        shared_with_email=share.shared_with.email,
        shared_with_picture=share.shared_with.picture,
        categories=share.categories.split(",") if share.categories else [],
    )


def share_to_shared_with_me(share: DataShare) -> SharedWithMeResponse:
    return SharedWithMeResponse(
        id=share.id,
        owner_id=share.owner_id,
        owner_name=share.owner.name,
        owner_email=share.owner.email,
        owner_picture=share.owner.picture,
        categories=share.categories.split(",") if share.categories else [],
    )


@router.get("/my-shares", response_model=list[ShareResponse])
def get_my_shares(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of users I'm sharing data with."""
    shares = db.query(DataShare).filter(DataShare.owner_id == current_user.id).all()
    return [share_to_response(s) for s in shares]


@router.get("/shared-with-me", response_model=list[SharedWithMeResponse])
def get_shared_with_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of users who are sharing data with me."""
    shares = db.query(DataShare).filter(DataShare.shared_with_id == current_user.id).all()
    return [share_to_shared_with_me(s) for s in shares]


@router.get("/users", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get list of all users (excluding myself) for sharing dropdown."""
    users = db.query(User).filter(User.id != current_user.id).all()
    return users


@router.post("/", response_model=ShareResponse)
def create_share(
    data: ShareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new share with another user."""
    # Validate categories
    invalid = set(data.categories) - VALID_CATEGORIES
    if invalid:
        raise HTTPException(400, f"Invalid categories: {invalid}")

    if not data.categories:
        raise HTTPException(400, "At least one category required")

    # Find target user
    target_user = db.query(User).filter(User.email == data.shared_with_email).first()
    if not target_user:
        raise HTTPException(404, "User not found")

    if target_user.id == current_user.id:
        raise HTTPException(400, "Cannot share with yourself")

    # Check if share already exists
    existing = db.query(DataShare).filter(
        DataShare.owner_id == current_user.id,
        DataShare.shared_with_id == target_user.id,
    ).first()

    if existing:
        raise HTTPException(400, "Share already exists. Use PUT to update.")

    share = DataShare(
        owner_id=current_user.id,
        shared_with_id=target_user.id,
        categories=",".join(data.categories),
    )
    db.add(share)
    db.commit()
    db.refresh(share)

    return share_to_response(share)


@router.put("/{share_id}", response_model=ShareResponse)
def update_share(
    share_id: int,
    data: ShareUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update categories for an existing share."""
    share = db.query(DataShare).filter(
        DataShare.id == share_id,
        DataShare.owner_id == current_user.id,
    ).first()

    if not share:
        raise HTTPException(404, "Share not found")

    # Validate categories
    invalid = set(data.categories) - VALID_CATEGORIES
    if invalid:
        raise HTTPException(400, f"Invalid categories: {invalid}")

    if not data.categories:
        raise HTTPException(400, "At least one category required")

    share.categories = ",".join(data.categories)
    db.commit()
    db.refresh(share)

    return share_to_response(share)


@router.delete("/{share_id}")
def delete_share(
    share_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a share (revoke access)."""
    share = db.query(DataShare).filter(
        DataShare.id == share_id,
        DataShare.owner_id == current_user.id,
    ).first()

    if not share:
        raise HTTPException(404, "Share not found")

    db.delete(share)
    db.commit()

    return {"ok": True}
