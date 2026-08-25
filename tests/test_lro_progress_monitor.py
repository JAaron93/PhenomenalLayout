"""Unit tests for LROProgressMonitor (TASK-1.4).

Traceability: FR-04, NFR-02
- Polls Long-Running Operations (LROs)
- Parses BatchTranslateDocumentMetadata
- Computes completion percentage and time estimates
- Exponential backoff retry on transient errors (429/503)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as api_exceptions

from services.byok_credentials_manager import BYOKCredentialsManager
from services.lro_progress_monitor import LROProgressMonitor, ProgressUpdate


@pytest.fixture
def mock_creds_manager() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    return mgr


@pytest.fixture
def monitor(mock_creds_manager: MagicMock) -> LROProgressMonitor:
    return LROProgressMonitor(credentials_manager=mock_creds_manager)


class TestLROPolling:
    """Test polling operations and parsing BatchTranslateDocumentMetadata."""

    def test_poll_running_state(self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None

        mock_meta = MagicMock()
        mock_meta.total_pages = 300
        mock_meta.translated_pages = 150
        mock_meta.failed_pages = 0
        mock_meta.state = "RUNNING"
        mock_op.metadata = mock_meta

        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-1")

        assert isinstance(progress, ProgressUpdate)
        assert progress.operation_name == "projects/p/locations/us-central1/operations/op-1"
        assert progress.state == "RUNNING"
        assert progress.total_pages == 300
        assert progress.translated_pages == 150
        assert progress.failed_pages == 0
        assert progress.completion_pct == pytest.approx(50.0)
        assert progress.is_done is False
        assert progress.error_message is None

    def test_poll_succeeded_state(self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = True
        mock_op.error = None

        mock_meta = MagicMock()
        mock_meta.total_pages = 350
        mock_meta.translated_pages = 350
        mock_meta.failed_pages = 0
        mock_meta.state = "SUCCEEDED"
        mock_op.metadata = mock_meta

        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-done")

        assert progress.state == "SUCCEEDED"
        assert progress.total_pages == 350
        assert progress.translated_pages == 350
        assert progress.completion_pct == pytest.approx(100.0)
        assert progress.is_done is True
        assert progress.error_message is None

    def test_poll_failed_state(self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = True
        mock_error = MagicMock()
        mock_error.message = "PDF document is corrupt or password-protected"
        mock_op.error = mock_error

        mock_meta = MagicMock()
        mock_meta.total_pages = 100
        mock_meta.translated_pages = 10
        mock_meta.failed_pages = 90
        mock_meta.state = "FAILED"
        mock_op.metadata = mock_meta

        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-failed")

        assert progress.state == "FAILED"
        assert progress.is_done is True
        assert progress.error_message == "PDF document is corrupt or password-protected"


class TestEstimateRemainingTime:
    """Test linear time extrapolation."""

    def test_estimate_when_running(self, monitor: LROProgressMonitor) -> None:
        progress = ProgressUpdate(
            operation_name="op-1",
            state="RUNNING",
            total_pages=300,
            translated_pages=100,
            failed_pages=0,
            completion_pct=33.33,
            is_done=False,
        )
        # 100 pages in 50 seconds = 0.5s per page. 200 pages remaining * 0.5 = 100s.
        est = monitor.estimate_remaining_time(progress, elapsed_seconds=50.0)
        assert est == pytest.approx(100.0, abs=1.0)

    def test_estimate_when_zero_pages_translated(self, monitor: LROProgressMonitor) -> None:
        progress = ProgressUpdate(
            operation_name="op-1",
            state="RUNNING",
            total_pages=300,
            translated_pages=0,
            failed_pages=0,
            completion_pct=0.0,
            is_done=False,
        )
        assert monitor.estimate_remaining_time(progress, elapsed_seconds=10.0) is None

    def test_estimate_when_not_running(self, monitor: LROProgressMonitor) -> None:
        progress = ProgressUpdate(
            operation_name="op-1",
            state="SUCCEEDED",
            total_pages=300,
            translated_pages=300,
            failed_pages=0,
            completion_pct=100.0,
            is_done=True,
        )
        assert monitor.estimate_remaining_time(progress, elapsed_seconds=150.0) is None


class TestRetryOnTransientErrors:
    """Test exponential backoff on 429/503 during polling."""

    @patch("time.sleep", return_value=None)
    def test_retry_on_429_then_succeed(
        self, mock_sleep: MagicMock, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None
        mock_meta = MagicMock()
        mock_meta.total_pages = 50
        mock_meta.translated_pages = 25
        mock_meta.failed_pages = 0
        mock_meta.state = "RUNNING"
        mock_op.metadata = mock_meta

        mock_client.get_operation.side_effect = [
            api_exceptions.ResourceExhausted("Rate limit"),
            mock_op,
        ]

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-1")
        assert progress.state == "RUNNING"
        assert mock_sleep.called

    @patch("time.sleep", return_value=None)
    def test_retry_on_503_then_succeed(
        self, mock_sleep: MagicMock, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None
        mock_meta = MagicMock()
        mock_meta.total_pages = 10
        mock_meta.translated_pages = 5
        mock_meta.failed_pages = 0
        mock_meta.state = "RUNNING"
        mock_op.metadata = mock_meta

        mock_client.get_operation.side_effect = [
            api_exceptions.ServiceUnavailable("Unavailable"),
            mock_op,
        ]

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-1")
        assert progress.state == "RUNNING"
        assert mock_sleep.called

    def test_non_transient_error_reraises(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client
        mock_client.get_operation.side_effect = api_exceptions.PermissionDenied("No permission")

        with pytest.raises(api_exceptions.PermissionDenied):
            monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-1")

    @patch("time.sleep", return_value=None)
    def test_retry_exhausted_raises(
        self, mock_sleep: MagicMock, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client
        mock_client.get_operation.side_effect = api_exceptions.ResourceExhausted("Rate limit loop")

        with pytest.raises(api_exceptions.ResourceExhausted):
            monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-1")


class TestMetadataDeserializationBranches:
    """Test Stage A (bytes), Stage B, and fallback paths."""

    def test_none_metadata_returns_sentinel(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.metadata = None
        mock_op.done = False
        mock_op.error = None
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-none")
        assert progress.state == "SUBMITTED"
        assert progress.total_pages == 0
        assert progress.translated_pages == 0
        assert progress.completion_pct == 0.0

    def test_unparseable_metadata_returns_sentinel(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.metadata = object()  # plain object without attributes
        mock_op.done = True
        mock_op.error = None
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-unparseable")
        assert progress.state == "SUBMITTED"
        assert progress.is_done is True

    @patch("services.lro_progress_monitor.translate.types.BatchTranslateDocumentMetadata.deserialize")
    def test_stage_a_bytes_deserialization(
        self, mock_deserialize: MagicMock, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_deserialized = MagicMock()
        mock_deserialized.total_pages = 200
        mock_deserialized.translated_pages = 200
        mock_deserialized.failed_pages = 0
        mock_deserialized.state = "SUCCEEDED"
        mock_deserialize.return_value = mock_deserialized

        mock_op = MagicMock()
        mock_op.done = True
        mock_op.error = None
        mock_meta_holder = MagicMock()
        mock_meta_holder.value = b"\x08\xc8\x01"
        mock_op.metadata = mock_meta_holder
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-bytes")
        assert progress.state == "SUCCEEDED"
        assert progress.total_pages == 200
        assert progress.completion_pct == pytest.approx(100.0)

    def test_integer_state_normalization(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None
        mock_meta = MagicMock()
        mock_meta.total_pages = 100
        mock_meta.translated_pages = 50
        mock_meta.failed_pages = 0
        # Integer state value (1 = RUNNING in GCP BatchTranslateDocumentMetadata.State)
        mock_meta.state = 1
        mock_op.metadata = mock_meta
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-int-state")
        assert progress.state == "RUNNING"

    def test_failed_state_with_error_detail_in_metadata(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = True
        mock_op.error = None  # No top-level error
        mock_meta = MagicMock()
        mock_meta.total_pages = 100
        mock_meta.translated_pages = 0
        mock_meta.failed_pages = 100
        mock_meta.state = "FAILED"
        mock_meta.error_detail = "Failed to parse layout elements on page 1"
        mock_op.metadata = mock_meta
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-fail-detail")
        assert progress.state == "FAILED"
        assert progress.error_message == "Failed to parse layout elements on page 1"

    @patch("services.lro_progress_monitor.translate.types.BatchTranslateDocumentMetadata.deserialize")
    def test_stage_a_deserialization_exception_falls_back_to_stage_b(
        self, mock_deserialize: MagicMock, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_deserialize.side_effect = Exception("Corrupt protobuf bytes")

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None
        mock_meta = MagicMock()
        mock_meta.value = b"invalid_bytes"
        mock_meta.total_pages = 50
        mock_meta.translated_pages = 10
        mock_meta.failed_pages = 0
        mock_meta.state = "RUNNING"
        mock_op.metadata = mock_meta
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-stage-b-fallback")
        assert progress.state == "RUNNING"
        assert progress.total_pages == 50

    def test_unknown_state_falls_back_to_submitted(
        self, monitor: LROProgressMonitor, mock_creds_manager: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_creds_manager.get_translation_client.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = False
        mock_op.error = None
        mock_meta = MagicMock()
        mock_meta.total_pages = 50
        mock_meta.translated_pages = 0
        mock_meta.failed_pages = 0
        mock_meta.state = "UNKNOWN_NONEXISTENT_STATE"
        mock_op.metadata = mock_meta
        mock_client.get_operation.return_value = mock_op

        progress = monitor.poll_once("user-1", "projects/p/locations/us-central1/operations/op-unknown")
        assert progress.state == "SUBMITTED"
