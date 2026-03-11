"""Google Drive storage service for progress photos."""

import io
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from app.config import get_settings

logger = logging.getLogger("askesis.google_drive")


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


def get_or_create_app_folder(service, parent_folder_id: str | None = None) -> str:
    """Get or create the app folder in user's Drive. Returns folder ID.

    Args:
        service: Google Drive service instance
        parent_folder_id: Optional parent folder ID from user's settings
    """
    settings = get_settings()
    folder_name = settings.drive_folder_name

    # Search for existing folder (optionally within a specific parent)
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_folder_id:
        folder_metadata["parents"] = [parent_folder_id]
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]


def upload_photo(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
    parent_folder_id: str | None = None,
) -> str:
    """
    Upload a photo to Google Drive.

    Args:
        refresh_token: User's Google refresh token
        file_content: Raw file bytes
        filename: Name for the file in Drive
        mime_type: MIME type of the file
        parent_folder_id: Optional parent folder ID from user's settings

    Returns:
        Google Drive file ID
    """
    service = get_drive_service(refresh_token)
    folder_id = get_or_create_app_folder(service, parent_folder_id)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,
    )

    file = (
        service.files()
        .create(
            body=file_metadata,
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


def get_or_create_backup_folder(service, parent_folder_id: str | None = None) -> str:
    """Get or create the backup folder in user's Drive. Returns folder ID."""
    folder_name = "Askesis Backups"

    # Search for existing folder
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_folder_id:
        folder_metadata["parents"] = [parent_folder_id]
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]


def get_or_create_meals_folder(service, parent_folder_id: str | None = None) -> str:
    """Get or create the meal photos folder in user's Drive. Returns folder ID."""
    folder_name = "Askesis Meal Photos"

    # Search for existing folder
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_folder_id:
        folder_metadata["parents"] = [parent_folder_id]
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]


def upload_meal_photo(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
    parent_folder_id: str | None = None,
) -> str:
    """
    Upload a meal photo to Google Drive.

    Args:
        refresh_token: User's Google refresh token
        file_content: Raw file bytes
        filename: Name for the file in Drive
        mime_type: MIME type of the file
        parent_folder_id: Optional parent folder ID from user's settings

    Returns:
        Google Drive file ID
    """
    service = get_drive_service(refresh_token)
    folder_id = get_or_create_meals_folder(service, parent_folder_id)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,
    )

    file = (
        service.files()
        .create(
            body=file_metadata,
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
    parent_folder_id: str | None = None,
) -> str:
    """
    Upload or update a database backup in Google Drive.
    Overwrites existing backup file if it exists.

    Args:
        refresh_token: User's Google refresh token
        file_content: Raw file bytes
        filename: Name for the backup file in Drive
        parent_folder_id: Optional parent folder ID from user's settings

    Returns:
        Google Drive file ID
    """
    logger.info(f"Starting backup upload: {filename}, size={len(file_content)} bytes")
    try:
        service = get_drive_service(refresh_token)
        folder_id = get_or_create_backup_folder(service, parent_folder_id)
        logger.info(f"Using backup folder: {folder_id}")

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
