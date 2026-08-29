"""Unit and BDD scenario tests for GoogleDriveExporter (TASK-1.6).

Traceability: FR-09, FR-10, NFR-03, NFR-07, NFR-09
- Stream translated PDF to Google Drive via GIS OAuth (drive.file scope)
- Zero host PDF disk storage (MediaIoBaseUpload directly from stream)
- Automatic destination folder lookup and creation
- Exponential backoff retry on transient HTTP 429/500/503 errors
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
import httplib2

from services.google_drive_exporter import DriveExportResult, GoogleDriveExporter


@pytest.fixture
def exporter() -> GoogleDriveExporter:
    return GoogleDriveExporter()


class TestGoogleDriveExporterBDD:
    """BDD Scenario FR-09.1: Export translated book to Google Drive via GIS OAuth."""

    @patch("services.google_drive_exporter.build")
    @patch("services.google_drive_exporter.Credentials")
    def test_export_stream_to_drive_success_new_folder(
        self, mock_creds_cls: MagicMock, mock_build: MagicMock, exporter: GoogleDriveExporter
    ) -> None:
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # 1. Folder lookup returns empty (folder not found)
        mock_files = mock_service.files.return_value
        mock_files.list.return_value.execute.return_value = {"files": []}

        # 2. Folder creation returns new folder id
        mock_files.create.return_value.execute.side_effect = [
            {"id": "folder-abc-123"},  # folder creation
            {  # file upload
                "id": "file-xyz-789",
                "name": "der_geist_translated.pdf",
                "webViewLink": "https://drive.google.com/file/d/file-xyz-789/view",
                "webContentLink": "https://drive.google.com/uc?id=file-xyz-789",
                "createdTime": "2026-08-25T12:00:00.000Z",
            },
        ]

        pdf_stream = io.BytesIO(b"%PDF-1.4 translated book content")

        result = exporter.export_stream_to_drive(
            access_token="ya29.mock_gis_oauth_token",
            file_stream=pdf_stream,
            filename="der_geist_translated.pdf",
            folder_name="PhenomenalLayout Translations",
        )

        assert isinstance(result, DriveExportResult)
        assert result.file_id == "file-xyz-789"
        assert result.file_name == "der_geist_translated.pdf"
        assert result.web_view_link == "https://drive.google.com/file/d/file-xyz-789/view"
        assert result.web_content_link == "https://drive.google.com/uc?id=file-xyz-789"
        assert result.created_time == "2026-08-25T12:00:00.000Z"

    @patch("services.google_drive_exporter.build")
    @patch("services.google_drive_exporter.Credentials")
    def test_export_stream_to_drive_existing_folder(
        self, mock_creds_cls: MagicMock, mock_build: MagicMock, exporter: GoogleDriveExporter
    ) -> None:
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # 1. Folder lookup finds existing folder
        mock_files = mock_service.files.return_value
        mock_files.list.return_value.execute.return_value = {
            "files": [{"id": "existing-folder-456", "name": "PhenomenalLayout Translations"}]
        }

        # 2. File upload directly into existing folder
        mock_files.create.return_value.execute.return_value = {
            "id": "file-111",
            "name": "kant_translated.pdf",
            "webViewLink": "https://drive.google.com/file/d/file-111/view",
            "webContentLink": None,
            "createdTime": "2026-08-25T13:00:00.000Z",
        }

        pdf_stream = io.BytesIO(b"%PDF-1.4 content")
        result = exporter.export_stream_to_drive(
            access_token="ya29.mock_gis_token",
            file_stream=pdf_stream,
            filename="kant_translated.pdf",
        )

        assert result.file_id == "file-111"
        assert result.web_view_link == "https://drive.google.com/file/d/file-111/view"


class TestGoogleDriveExporterValidationAndRetry:
    """Test validation errors and backoff retry logic."""

    def test_unreadable_stream_raises_value_error(self, exporter: GoogleDriveExporter) -> None:
        mock_stream = MagicMock()
        mock_stream.readable.return_value = False

        with pytest.raises(ValueError, match="readable"):
            exporter.export_stream_to_drive(
                access_token="token",
                file_stream=mock_stream,
                filename="doc.pdf",
            )

    @patch("time.sleep", return_value=None)
    @patch("services.google_drive_exporter.build")
    @patch("services.google_drive_exporter.Credentials")
    def test_retry_on_transient_http_error(
        self, mock_creds: MagicMock, mock_build: MagicMock, mock_sleep: MagicMock, exporter: GoogleDriveExporter
    ) -> None:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_files = mock_service.files.return_value

        # Folder lookup succeeds
        mock_files.list.return_value.execute.return_value = {
            "files": [{"id": "folder-1", "name": "PhenomenalLayout Translations"}]
        }

        # First upload attempt fails with 503 Service Unavailable, second succeeds
        resp_503 = httplib2.Response({"status": 503})
        error_503 = HttpError(resp_503, b"Service Unavailable")

        mock_files.create.return_value.execute.side_effect = [
            error_503,
            {
                "id": "file-retry-ok",
                "name": "book.pdf",
                "webViewLink": "https://drive.google.com/file/d/file-retry-ok/view",
                "webContentLink": None,
                "createdTime": None,
            },
        ]

        pdf_stream = io.BytesIO(b"%PDF content")
        result = exporter.export_stream_to_drive(
            access_token="token",
            file_stream=pdf_stream,
            filename="book.pdf",
        )

        assert result.file_id == "file-retry-ok"
        assert mock_sleep.called
