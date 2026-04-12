"""Google Drive storage service for progress photos, meal photos, and backups.

All files are organized under a main "Askesis" folder with subfolders:
- Askesis/
  ├── Progress Photos/
  ├── Meal Photos/
  └── Backups/
"""

import io
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from app.config import get_settings

logger = logging.getLogger("askesis.google_drive")

# Folder names
ASKESIS_FOLDER_NAME = "Askesis"
PROGRESS_PHOTOS_FOLDER = "Progress Photos"
MEAL_PHOTOS_FOLDER = "Meal Photos"
BACKUPS_FOLDER = "Backups"


def get_drive_service(refresh_token: str):
    """Build Google Drive service using refresh token."""
    settings = get_settings()

    logger.info("Building Drive service with refresh token")

    credentials = Credentials(
        token=None,  # Will be refreshed
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    try:
        service = build("drive", "v3", credentials=credentials)
        logger.info("Drive service built successfully")
        return service
    except Exception as e:
        logger.error(f"Failed to build Drive service: {e}")
        raise


def _get_or_create_subfolder(service, folder_name: str, parent_folder_id: str) -> str:
    """Get or create a folder as a direct child of a known parent. Returns folder ID.

    Always scoped to a parent so results are unambiguous.
    """
    query = (
        f"name='{folder_name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_folder_id}' in parents "
        f"and trashed=false"
    )
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    folder = (
        service.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_folder_id],
            },
            fields="id",
        )
        .execute()
    )
    return folder["id"]


def _folder_exists(service, folder_id: str) -> bool:
    """Verify a folder ID still exists and is not trashed."""
    try:
        meta = (
            service.files()
            .get(fileId=folder_id, fields="id, trashed, mimeType")
            .execute()
        )
        return (
            not meta.get("trashed", False)
            and meta.get("mimeType") == "application/vnd.google-apps.folder"
        )
    except HttpError:
        return False


def _find_or_create_askesis_folder(service, parent_folder_id: str | None = None) -> str:
    """Find the Askesis folder by name, or create it. Returns folder ID.

    When multiple matches exist (legacy duplicate folders), picks the most
    recently created one — that's where fresh uploads have been landing.
    """
    query = (
        f"name='{ASKESIS_FOLDER_NAME}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"

    results = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc",
        )
        .execute()
    )
    files = results.get("files", [])
    if files:
        logger.info(
            f"Found {len(files)} existing Askesis folder(s); picking newest: "
            f"{files[0]['id']} (created {files[0].get('createdTime')})"
        )
        return files[0]["id"]

    metadata = {
        "name": ASKESIS_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    logger.info(f"Created new Askesis folder: {folder['id']}")
    return folder["id"]


def resolve_askesis_folder_id(db, user) -> str:
    """Return the pinned Askesis folder ID for the user, creating it if needed.

    This is the single source of truth: the resolved ID is cached in
    ``user_settings.drive_askesis_folder_id`` so every subsequent upload reuses
    the exact same folder instead of searching by name. If the cached ID is
    invalid (folder deleted), it's cleared and re-resolved.
    """
    from app.models import UserSettings
    from app.encryption import get_refresh_token

    settings_row = (
        db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    )
    if settings_row is None:
        settings_row = UserSettings(user_id=user.id)
        db.add(settings_row)
        db.flush()

    service = get_drive_service(get_refresh_token(user))

    cached = settings_row.drive_askesis_folder_id
    if cached and _folder_exists(service, cached):
        return cached

    if cached:
        logger.warning(f"Cached Askesis folder {cached} no longer exists; re-resolving")

    folder_id = _find_or_create_askesis_folder(
        service, settings_row.drive_parent_folder_id
    )
    settings_row.drive_askesis_folder_id = folder_id
    db.commit()
    return folder_id


def upload_photo(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    askesis_folder_id: str,
    mime_type: str = "image/jpeg",
) -> str:
    """Upload a progress photo into the Askesis/Progress Photos/ folder."""
    service = get_drive_service(refresh_token)
    folder_id = _get_or_create_subfolder(
        service, PROGRESS_PHOTOS_FOLDER, askesis_folder_id
    )

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,
    )
    file = (
        service.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return file["id"]


def download_photo(refresh_token: str, file_id: str) -> bytes:
    """
    Download a photo from Google Drive.

    Args:
        refresh_token: User's Google refresh token
        file_id: Google Drive file ID

    Returns:
        File content as bytes
    """
    service = get_drive_service(refresh_token)

    request = service.files().get_media(fileId=file_id)
    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_buffer.seek(0)
    return file_buffer.read()


def delete_photo(refresh_token: str, file_id: str) -> bool:
    """
    Delete a photo from Google Drive.

    Args:
        refresh_token: User's Google refresh token
        file_id: Google Drive file ID

    Returns:
        True if deleted successfully
    """
    try:
        service = get_drive_service(refresh_token)
        service.files().delete(fileId=file_id).execute()
        return True
    except HttpError:
        return False


def check_drive_access(refresh_token: str) -> bool:
    """Check if we have valid Drive access with the refresh token."""
    try:
        service = get_drive_service(refresh_token)
        # Try to list files (limited to 1) to verify access
        service.files().list(pageSize=1).execute()
        return True
    except Exception:
        return False


def upload_meal_photo(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    askesis_folder_id: str,
    mime_type: str = "image/jpeg",
) -> str:
    """Upload a meal photo into the Askesis/Meal Photos/ folder."""
    service = get_drive_service(refresh_token)
    folder_id = _get_or_create_subfolder(service, MEAL_PHOTOS_FOLDER, askesis_folder_id)

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,
    )
    file = (
        service.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return file["id"]


def upload_backup(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    askesis_folder_id: str,
) -> str:
    """Upload or update a database backup inside Askesis/Backups/."""
    logger.info(f"Starting backup upload: {filename}, size={len(file_content)} bytes")
    try:
        service = get_drive_service(refresh_token)
        folder_id = _get_or_create_subfolder(service, BACKUPS_FOLDER, askesis_folder_id)
        logger.info(f"Using backup folder: {folder_id} (askesis={askesis_folder_id})")

        # Check if backup file already exists
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        results = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        existing_files = results.get("files", [])

        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype="application/x-sqlite3",
            resumable=True,
        )

        if existing_files:
            # Update existing file (overwrite)
            file_id = existing_files[0]["id"]
            logger.info(f"Updating existing backup file: {file_id}")
            file = (
                service.files()
                .update(
                    fileId=file_id,
                    media_body=media,
                )
                .execute()
            )
            logger.info("Backup updated successfully")
            return file["id"]
        else:
            # Create new file
            logger.info("Creating new backup file")
            file_metadata = {
                "name": filename,
                "parents": [folder_id],
            }
            file = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                )
                .execute()
            )
            logger.info(f"Backup created successfully: {file['id']}")
            return file["id"]
    except HttpError as e:
        logger.error(f"Google Drive API error: {e.status_code} - {e.reason}")
        logger.error(f"Error details: {e.error_details}")
        raise
    except Exception as e:
        logger.error(f"Backup upload failed: {type(e).__name__}: {e}")
        raise
