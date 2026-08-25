"""Unit tests for GCPBatchTranslationService (TASK-1.3).

Traceability: FR-03, FR-10, NFR-01, NFR-02, NFR-07
- Zero host PDF disk storage
- 7-Day GCS staging lifecycle policy inspection/patching
- Asynchronous batch translation job submission
- Streaming translated output directly from GCS
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions

from services.byok_credentials_manager import BYOKCredentialsManager
from services.gcp_batch_translation_service import (
    BatchJobHandle,
    GCPBatchTranslationService,
)


@pytest.fixture
def mock_creds_manager() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    mgr.get_credentials.return_value = MagicMock()
    mgr.get_project_id.return_value = "test-project-123"
    mgr.get_bucket_name.return_value = "test-bucket"
    return mgr


@pytest.fixture
def batch_service(mock_creds_manager: MagicMock) -> GCPBatchTranslationService:
    return GCPBatchTranslationService(
        credentials_manager=mock_creds_manager,
        project_id="test-project-123",
        location="us-central1",
    )


class TestUploadBookToGCS:
    """Verify streaming PDF upload to GCS (zero host disk footprint)."""

    @patch("services.gcp_batch_translation_service.storage.Client")
    def test_upload_from_binary_stream(
        self, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        pdf_bytes = b"%PDF-1.4 test document content"
        pdf_stream = io.BytesIO(pdf_bytes)

        result_uri = batch_service.upload_book_to_gcs(
            user_id="user-1",
            source=pdf_stream,
            gcs_destination_uri="gs://my-bucket/inputs/book_101/source.pdf",
        )

        assert result_uri == "gs://my-bucket/inputs/book_101/source.pdf"
        mock_storage_client.bucket.assert_called_once_with("my-bucket")
        mock_bucket.blob.assert_called_once_with("inputs/book_101/source.pdf")
        mock_blob.upload_from_file.assert_called_once_with(pdf_stream, content_type="application/pdf")

    def test_upload_invalid_gcs_uri(self, batch_service: GCPBatchTranslationService) -> None:
        with pytest.raises(ValueError, match="Invalid GCS URI"):
            batch_service.upload_book_to_gcs(
                user_id="user-1",
                source=io.BytesIO(b"data"),
                gcs_destination_uri="http://my-bucket/inputs/source.pdf",
            )

    @patch("services.gcp_batch_translation_service.storage.Client")
    def test_upload_nonexistent_local_file(
        self, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        with pytest.raises(FileNotFoundError):
            batch_service.upload_book_to_gcs(
                user_id="user-1",
                source=Path("/tmp/nonexistent_book_12345.pdf"),
                gcs_destination_uri="gs://my-bucket/inputs/source.pdf",
            )


class TestEnsureStagingLifecyclePolicy:
    """Verify prefix-scoped 7-day auto-delete lifecycle inspection and patching."""

    @patch("services.gcp_batch_translation_service.storage.Client")
    def test_lifecycle_policy_already_exists(
        self, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_bucket.lifecycle_rules = [
            {
                "action": {"type": "Delete"},
                "condition": {"age": 7, "matchesPrefix": ["inputs/"]},
            }
        ]
        mock_storage_client.get_bucket.return_value = mock_bucket

        applied = batch_service.ensure_staging_lifecycle_policy(
            user_id="user-1",
            bucket_name="my-bucket",
            staging_prefix="inputs/",
            age_days=7,
        )

        assert applied is True
        mock_bucket.patch.assert_not_called()

    @patch("services.gcp_batch_translation_service.storage.Client")
    def test_lifecycle_policy_appended_and_patched(
        self, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_bucket.lifecycle_rules = []
        mock_storage_client.get_bucket.return_value = mock_bucket

        applied = batch_service.ensure_staging_lifecycle_policy(
            user_id="user-1",
            bucket_name="my-bucket",
            staging_prefix="inputs/",
            age_days=7,
        )

        assert applied is True
        mock_bucket.patch.assert_called_once()
        assert len(mock_bucket.lifecycle_rules) == 1
        rule = mock_bucket.lifecycle_rules[0]
        assert rule["action"]["type"] == "Delete"
        assert rule["condition"]["matchesPrefix"] == ["inputs/"]
        assert rule["condition"]["age"] == 7


class TestSubmitBatchJob:
    """Verify submitting batchTranslateDocument requests."""

    @patch("services.gcp_batch_translation_service.storage.Client")
    @patch("services.gcp_batch_translation_service.translate.TranslationServiceClient")
    def test_submit_batch_job_success(
        self, mock_translate_cls: MagicMock, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_bucket.lifecycle_rules = [{"action": {"type": "Delete"}, "condition": {"matchesPrefix": ["inputs/"], "age": 7}}]
        mock_storage_client.get_bucket.return_value = mock_bucket

        mock_translate_client = MagicMock()
        mock_translate_cls.return_value = mock_translate_client

        mock_operation = MagicMock()
        mock_operation.operation.name = "projects/test-project-123/locations/us-central1/operations/op-12345"
        mock_translate_client.batch_translate_document.return_value = mock_operation

        op_name = batch_service.submit_batch_job(
            user_id="user-1",
            gcs_input_uri="gs://my-bucket/inputs/book_101/source.pdf",
            gcs_output_uri_prefix="gs://my-bucket/outputs/book_101/",
            source_lang="de",
            target_lang="en-US",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/klages_glossary",
        )

        assert op_name == "projects/test-project-123/locations/us-central1/operations/op-12345"
        mock_translate_client.batch_translate_document.assert_called_once()

    @patch("time.sleep", return_value=None)
    @patch("services.gcp_batch_translation_service.storage.Client")
    @patch("services.gcp_batch_translation_service.translate.TranslationServiceClient")
    def test_submit_batch_job_transient_retry(
        self,
        mock_translate_cls: MagicMock,
        mock_storage_cls: MagicMock,
        mock_sleep: MagicMock,
        batch_service: GCPBatchTranslationService,
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_bucket.lifecycle_rules = [{"action": {"type": "Delete"}, "condition": {"matchesPrefix": ["inputs/"], "age": 7}}]
        mock_storage_client.get_bucket.return_value = mock_bucket

        mock_translate_client = MagicMock()
        mock_translate_cls.return_value = mock_translate_client

        mock_operation = MagicMock()
        mock_operation.operation.name = "projects/test-project-123/locations/us-central1/operations/op-retry"
        # Fail once with 429 then succeed
        mock_translate_client.batch_translate_document.side_effect = [
            gcp_exceptions.TooManyRequests("Rate limited"),
            mock_operation,
        ]

        op_name = batch_service.submit_batch_job(
            user_id="user-1",
            gcs_input_uri="gs://my-bucket/inputs/book_101/source.pdf",
            gcs_output_uri_prefix="gs://my-bucket/outputs/book_101/",
        )

        assert op_name == "projects/test-project-123/locations/us-central1/operations/op-retry"
        assert mock_sleep.called

    def test_upload_fails_if_lifecycle_policy_fails(
        self, batch_service: GCPBatchTranslationService
    ) -> None:
        with patch.object(batch_service, "ensure_staging_lifecycle_policy", return_value=False):
            with pytest.raises(RuntimeError, match="Failed to ensure 7-day auto-delete"):
                batch_service.upload_book_to_gcs(
                    user_id="user-1",
                    source=io.BytesIO(b"%PDF-test"),
                    gcs_destination_uri="gs://my-bucket/inputs/book_101/source.pdf",
                )


class TestStreamTranslatedBook:
    """Verify streaming translated PDF directly from GCS without host disk storage."""

    @patch("services.gcp_batch_translation_service.storage.Client")
    def test_stream_translated_book(
        self, mock_storage_cls: MagicMock, batch_service: GCPBatchTranslationService
    ) -> None:
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mock_stream = io.BytesIO(b"%PDF translated content")
        mock_blob.open.return_value = mock_stream

        stream = batch_service.stream_translated_book(
            user_id="user-1",
            gcs_output_uri="gs://my-bucket/outputs/book_101/book_de_en-US.pdf",
        )

        assert stream is mock_stream
        mock_blob.open.assert_called_once_with("rb")
