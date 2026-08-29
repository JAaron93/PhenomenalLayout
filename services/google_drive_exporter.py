"""
services/google_drive_exporter.py
==================================
TASK-1.6 — FR-09, FR-10, NFR-03, NFR-07, NFR-09

Exports translated PDFs to Google Drive using a short-lived GIS OAuth token
that is supplied by the browser client.

Design invariants
-----------------
* Access tokens are **never** written to disk or emitted to logs.
* **Zero** temporary files are created on the host — uploads are streamed
  directly via :class:`googleapiclient.http.MediaIoBaseUpload`.
* Transient HTTP 429 / 500 / 503 errors are retried with exponential backoff
  (up to ``MAX_RETRIES`` attempts).
* All public methods carry complete type annotations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import BinaryIO

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

#: Google Drive v3 API identifier.
_DRIVE_API_NAME: str = "drive"
_DRIVE_API_VERSION: str = "v3"

#: MIME type used for Drive folder resources.
_DRIVE_FOLDER_MIME: str = "application/vnd.google-apps.folder"

#: Maximum number of retry attempts for transient HTTP errors.
MAX_RETRIES: int = 5

#: Base delay (seconds) for the first retry; doubles with each attempt.
_BACKOFF_BASE_SECONDS: float = 1.0

#: HTTP status codes that are considered transient and eligible for retry.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 503})

#: Comma-separated Drive fields to request when creating/uploading a file.
_FILE_FIELDS: str = "id,name,webViewLink,webContentLink,createdTime"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class DriveExportResult:
    """Immutable result returned after a successful Drive export.

    Attributes
    ----------
    file_id:
        The opaque Drive file identifier assigned by the API.
    file_name:
        The display name of the uploaded file as stored in Drive.
    web_view_link:
        A permanent URL at which the file can be viewed in a browser.
    web_content_link:
        A direct download URL, when available (``None`` for Google-native
        formats or when the API omits the field).
    created_time:
        RFC 3339 timestamp string indicating when the file was created,
        or ``None`` when the API omits the field.
    """

    file_id: str
    file_name: str
    web_view_link: str
    web_content_link: str | None
    created_time: str | None


# ---------------------------------------------------------------------------
# Main exporter class
# ---------------------------------------------------------------------------


class GoogleDriveExporter:
    """Streams translated PDFs to Google Drive on behalf of the end-user.

    Authentication
    --------------
    The caller supplies a short-lived *access token* obtained via the
    browser-side **Google Identity Services (GIS)** OAuth flow with the
    ``https://www.googleapis.com/auth/drive.file`` scope.  The token is
    used only for the lifetime of a single :meth:`export_stream_to_drive`
    call and is **never** persisted, logged, or stored in instance state.

    Upload strategy
    ---------------
    Files are uploaded via the Drive v3 *resumable* multipart upload path
    using :class:`googleapiclient.http.MediaIoBaseUpload`.  This keeps
    zero bytes on the host filesystem; the caller-supplied :class:`BinaryIO`
    stream is forwarded directly to the API.

    Retry policy
    ------------
    All Drive API calls are wrapped in :meth:`_call_with_backoff`, which
    retries on transient HTTP status codes (429, 500, 503) up to
    :data:`MAX_RETRIES` times with exponential backoff and full jitter.

    Example
    -------
    ::

        exporter = GoogleDriveExporter()
        result = await asyncio.to_thread(
            exporter.export_stream_to_drive,
            access_token=gis_token,
            file_stream=pdf_bytes_io,
            filename="translated_brochure_es.pdf",
        )
        print(result.web_view_link)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_stream_to_drive(
        self,
        access_token: str,
        file_stream: BinaryIO,
        filename: str,
        mime_type: str = "application/pdf",
        folder_name: str = "PhenomenalLayout Translations",
    ) -> DriveExportResult:
        """Upload *file_stream* to Google Drive and return metadata.

        The method performs three Drive API calls in sequence:

        1. **Folder lookup** — search for an existing folder named
           *folder_name* that is not in the trash.
        2. **Folder creation** (if absent) — create the folder.
        3. **File upload** — stream *file_stream* into the folder using a
           resumable multipart upload.

        All three calls are protected by :meth:`_call_with_backoff`.

        Parameters
        ----------
        access_token:
            Short-lived GIS OAuth token with ``drive.file`` scope.
            **Never** stored or logged.
        file_stream:
            Readable binary stream (e.g., :class:`io.BytesIO`) containing
            the PDF payload.  Must be open and positioned at offset 0.
        filename:
            The name the file will have in Google Drive.
        mime_type:
            MIME type of *file_stream*.  Defaults to ``application/pdf``.
        folder_name:
            Name of the destination Drive folder.  Created if absent.
            Defaults to ``"PhenomenalLayout Translations"``.

        Returns
        -------
        DriveExportResult
            Metadata about the newly created Drive file.

        Raises
        ------
        googleapiclient.errors.HttpError
            Re-raised after all retry attempts are exhausted for
            non-transient errors, or after ``MAX_RETRIES`` failures for
            transient ones.
        ValueError
            If *file_stream* is not readable.
        """
        if not file_stream.readable():
            raise ValueError("file_stream must be open and readable.")

        service = self._get_authenticated_service(access_token)

        # ---- Step 1 & 2: resolve (or create) the destination folder ------
        folder_id = self._resolve_or_create_folder(service, folder_name)

        # ---- Step 3: upload file -----------------------------------------
        media = MediaIoBaseUpload(
            file_stream,
            mimetype=mime_type,
            resumable=True,
        )
        file_metadata: dict[str, object] = {
            "name": filename,
            "parents": [folder_id],
        }

        logger.info(
            "Uploading '%s' (%s) to Drive folder '%s' (id=%s).",
            filename,
            mime_type,
            folder_name,
            folder_id,
        )

        raw: dict[str, object] = self._call_with_backoff(
            service.files().create(
                body=file_metadata,
                media_body=media,
                fields=_FILE_FIELDS,
            )
        )

        result = DriveExportResult(
            file_id=str(raw["id"]),
            file_name=str(raw["name"]),
            web_view_link=str(raw["webViewLink"]),
            web_content_link=str(raw["webContentLink"]) if raw.get("webContentLink") else None,
            created_time=str(raw["createdTime"]) if raw.get("createdTime") else None,
        )

        logger.info(
            "Drive upload complete — file_id=%s name='%s'.",
            result.file_id,
            result.file_name,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_authenticated_service(self, access_token: str) -> object:
        """Build and return a Drive v3 service resource.

        The service is constructed from a :class:`google.oauth2.credentials.Credentials`
        object carrying only the short-lived *access_token*.  No client
        secret, refresh token, or token URI is set — the token is used as-is
        for the duration of the upload.

        Parameters
        ----------
        access_token:
            Short-lived GIS OAuth bearer token.  **Never** logged.

        Returns
        -------
        googleapiclient.discovery.Resource
            Authenticated Drive v3 service resource.
        """
        credentials = Credentials(token=access_token)
        service = build(
            _DRIVE_API_NAME,
            _DRIVE_API_VERSION,
            credentials=credentials,
            # Disable file-based cache to prevent any credential material
            # being written to the local filesystem (NFR-03).
            cache_discovery=False,
        )
        return service

    def _resolve_or_create_folder(
        self,
        service: object,  # googleapiclient.discovery.Resource
        folder_name: str,
    ) -> str:
        """Return the Drive ID of *folder_name*, creating it if absent.

        The search is limited to non-trashed Drive folders accessible with
        the caller's ``drive.file`` scope.  When multiple folders share the
        same name, the first result from the API is used.

        Parameters
        ----------
        service:
            Authenticated Drive v3 service resource.
        folder_name:
            Human-readable folder name to look up or create.

        Returns
        -------
        str
            The Drive folder ID.
        """
        # Escape single quotes in folder name to prevent query injection.
        safe_name = folder_name.replace("'", "\\'")
        query = (
            f"name='{safe_name}' "
            f"and mimeType='{_DRIVE_FOLDER_MIME}' "
            f"and trashed=false"
        )

        logger.debug("Searching Drive for folder: '%s'.", folder_name)

        list_response: dict[str, object] = self._call_with_backoff(
            service.files().list(  # type: ignore[attr-defined]
                q=query,
                fields="files(id,name)",
                pageSize=1,
            )
        )

        files: list[dict[str, str]] = list_response.get("files", [])  # type: ignore[assignment]

        if files:
            folder_id: str = files[0]["id"]
            logger.debug(
                "Found existing Drive folder '%s' (id=%s).",
                folder_name,
                folder_id,
            )
            return folder_id

        # Folder not found — create it.
        logger.info("Drive folder '%s' not found; creating it.", folder_name)
        create_response: dict[str, object] = self._call_with_backoff(
            service.files().create(  # type: ignore[attr-defined]
                body={
                    "name": folder_name,
                    "mimeType": _DRIVE_FOLDER_MIME,
                },
                fields="id",
            )
        )
        new_folder_id: str = str(create_response["id"])
        logger.info(
            "Created Drive folder '%s' (id=%s).",
            folder_name,
            new_folder_id,
        )
        return new_folder_id

    @staticmethod
    def _call_with_backoff(request: object) -> dict[str, object]:
        """Execute a Drive API *request* with exponential backoff.

        Delegates to :func:`utils.gcp_helpers.retry_gcp_call`.
        """
        from utils.gcp_helpers import retry_gcp_call

        def _do_execute() -> dict[str, object]:
            return request.execute()  # type: ignore[union-attr]

        return retry_gcp_call(
            _do_execute,
            max_retries=MAX_RETRIES - 1,
            base_delay=_BACKOFF_BASE_SECONDS,
            max_delay=_BACKOFF_BASE_SECONDS * (2 ** (MAX_RETRIES - 1)),
        )
