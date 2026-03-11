"""Google Drive storage service for progress photos."""
import io
from typing import BinaryIO

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

from app.config import get_settings


def get_drive_service(refresh_token: str):
    """Build Google Drive service using refresh token."""
    settings = get_settings()

    credentials = Credentials(
        token=None,  # Will be refreshed
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    return build("drive", "v3", credentials=credentials)


def get_or_create_app_folder(service) -> str:
    """Get or create the app folder in user's Drive. Returns folder ID."""
    settings = get_settings()
    folder_name = settings.drive_folder_name
    parent_id = settings.drive_parent_folder_id

    # Search for existing folder (optionally within a specific parent)
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        folder_metadata["parents"] = [parent_id]
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]


def upload_photo(
    refresh_token: str,
    file_content: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
) -> str:
    """
    Upload a photo to Google Drive.

    Args:
        refresh_token: User's Google refresh token
        file_content: Raw file bytes
        filename: Name for the file in Drive
        mime_type: MIME type of the file

    Returns:
        Google Drive file ID
    """
    service = get_drive_service(refresh_token)
    folder_id = get_or_create_app_folder(service)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,
    )

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()

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
