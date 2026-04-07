from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_SCOPES = [DRIVE_FILE_SCOPE, DRIVE_READONLY_SCOPE]
GOOGLE_FILE_ID_RE = re.compile(
    r"/d/(?P<file_id>[-_a-zA-Z0-9]+)|[?&]id=(?P<query_id>[-_a-zA-Z0-9]+)"
)


@dataclass
class DriveConfig:
    credentials_path: Path
    token_path: Path
    folder_name: str = "WhatsApp Zip To Docx"


def ensure_drive_service(config: DriveConfig):
    credentials = _load_credentials(config)
    return build("drive", "v3", credentials=credentials)


def upload_file(
    file_path: Path,
    config: DriveConfig,
    mime_type: Optional[str] = None,
    folder_id: Optional[str] = None,
    service=None,
) -> str:
    drive_service = service or ensure_drive_service(config)
    target_folder_id = folder_id or ensure_folder(drive_service, config.folder_name)
    metadata = {
        "name": file_path.name,
        "parents": [target_folder_id],
    }
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=False)
    last_error: HttpError | None = None
    for attempt in range(3):
        try:
            created = (
                drive_service.files()
                .create(body=metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
            return created["webViewLink"]
        except HttpError as error:
            last_error = error
            status = getattr(error.resp, "status", None)
            if status not in {500, 502, 503, 504}:
                raise
            time.sleep(1.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected upload failure without HttpError")


def folder_web_link(config: DriveConfig, folder_id: Optional[str] = None, service=None) -> str:
    drive_service = service or ensure_drive_service(config)
    resolved_folder_id = folder_id or ensure_folder(drive_service, config.folder_name)
    return f"https://drive.google.com/drive/folders/{resolved_folder_id}"


def ensure_folder(service, folder_name: str) -> str:
    escaped_name = folder_name.replace("'", "\\'")
    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{escaped_name}' and trashed = false"
    )
    response = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = response.get("files", [])
    if files:
        return files[0]["id"]

    created = (
        service.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            },
            fields="id",
        )
        .execute()
    )
    return created["id"]


def shared_file_metadata_from_url(url: str, config: DriveConfig, service=None) -> Optional[dict[str, object]]:
    file_id = _extract_google_file_id(url)
    if not file_id:
        return None
    drive_service = service or ensure_drive_service(config)
    try:
        payload = (
            drive_service.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,thumbnailLink,webViewLink,owners(displayName)",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_google_file_id(url: str) -> Optional[str]:
    match = GOOGLE_FILE_ID_RE.search(url)
    if not match:
        return None
    return match.group("file_id") or match.group("query_id")


def _load_credentials(config: DriveConfig) -> Credentials:
    credentials = None
    if config.token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(config.token_path), DRIVE_SCOPES)

    if credentials and credentials.valid and credentials.has_scopes(DRIVE_SCOPES):
        return credentials

    if credentials and credentials.expired and credentials.refresh_token and credentials.has_scopes(DRIVE_SCOPES):
        credentials.refresh(Request())
        config.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    flow = InstalledAppFlow.from_client_secrets_file(str(config.credentials_path), DRIVE_SCOPES)
    credentials = flow.run_local_server(port=0)
    config.token_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
