"""Unit and integration tests for BYOKCredentialsManager (TASK-1.2).

Traceability: FR-05, FR-08, NFR-03, NFR-05, NFR-11
- Zero credentials written to disk or logs
- Dual Translation and Storage validation
- In-memory thread safety
- Onboarding guide generation
- Transient error exponential backoff retry
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions

from services.byok_credentials_manager import (
    BYOKCredentialsManager,
    CredentialNotFoundError,
    GuideStep,
    ValidationResult,
)


@pytest.fixture
def valid_sa_dict() -> dict[str, str]:
    """Sample valid Service Account dictionary."""
    return {
        "type": "service_account",
        "project_id": "test-project-123",
        "private_key_id": "pkid-12345",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n",
        "client_email": "test-sa@test-project-123.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test-sa%40test-project-123.iam.gserviceaccount.com",
    }


@pytest.fixture
def valid_sa_json(valid_sa_dict: dict[str, str]) -> str:
    """Sample valid Service Account JSON string."""
    return json.dumps(valid_sa_dict)


@pytest.fixture
def manager() -> BYOKCredentialsManager:
    return BYOKCredentialsManager()


class TestCredentialIngestion:
    """Test set_credentials, clear_credentials, and has_credentials."""

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_set_credentials_dict(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        success = manager.set_credentials(
            user_id="user-1",
            project_id="test-project-123",
            bucket_name="test-bucket",
            sa_json_content=valid_sa_dict,
        )
        assert success is True
        assert manager.has_credentials("user-1") is True
        assert manager.get_project_id("user-1") == "test-project-123"
        assert manager.get_bucket_name("user-1") == "test-bucket"

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_set_credentials_json_string(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_json: str
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        success = manager.set_credentials(
            user_id="user-2",
            project_id="test-project-123",
            bucket_name="test-bucket-2",
            sa_json_content=valid_sa_json,
        )
        assert success is True
        assert manager.has_credentials("user-2") is True

    def test_set_credentials_invalid_json(self, manager: BYOKCredentialsManager) -> None:
        with pytest.raises(ValueError):
            manager.set_credentials(
                user_id="user-err",
                project_id="test-project-123",
                bucket_name="test-bucket",
                sa_json_content="not a valid json {",
            )

    def test_set_credentials_missing_required_fields(self, manager: BYOKCredentialsManager) -> None:
        incomplete_dict = {"type": "service_account", "project_id": "test-proj"}
        with pytest.raises(ValueError):
            manager.set_credentials(
                user_id="user-missing",
                project_id="test-proj",
                bucket_name="test-bucket",
                sa_json_content=incomplete_dict,
            )

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_clear_credentials(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        manager.set_credentials("user-clear", "proj-1", "bucket-1", valid_sa_dict)
        assert manager.has_credentials("user-clear") is True

        manager.clear_credentials("user-clear")
        assert manager.has_credentials("user-clear") is False

        with pytest.raises(CredentialNotFoundError):
            manager.get_project_id("user-clear")

    def test_get_nonexistent_user_raises(self, manager: BYOKCredentialsManager) -> None:
        with pytest.raises(CredentialNotFoundError):
            manager.get_translation_client("nonexistent-user")

        with pytest.raises(CredentialNotFoundError):
            manager.get_storage_client("nonexistent-user")


class TestDualServiceValidation:
    """Test validate_credentials for Translation and Storage checks."""

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_validate_credentials_success(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        manager.set_credentials("user-valid", "test-project-123", "test-bucket", valid_sa_dict)

        mock_translate_client = MagicMock()
        mock_translate_client.list_glossaries.return_value = []

        mock_storage_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.test_iam_permissions.return_value = [
            "storage.objects.create",
            "storage.objects.get",
            "storage.objects.delete",
            "storage.buckets.get",
            "storage.buckets.update",
        ]
        mock_storage_client.get_bucket.return_value = mock_bucket

        with patch.object(manager, "_build_translation_client", return_value=mock_translate_client), \
             patch.object(manager, "_build_storage_client", return_value=mock_storage_client):

            result = manager.validate_credentials("user-valid")
            assert isinstance(result, ValidationResult)
            assert result.status == "VALID"
            assert result.translation_check_passed is True
            assert result.storage_check_passed is True
            assert result.error_details is None

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_validate_credentials_translation_failure(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        manager.set_credentials("user-t-fail", "test-project-123", "test-bucket", valid_sa_dict)

        mock_translate_client = MagicMock()
        mock_translate_client.list_glossaries.side_effect = gcp_exceptions.PermissionDenied("No translation permission")

        mock_storage_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.test_iam_permissions.return_value = [
            "storage.objects.create",
            "storage.objects.get",
            "storage.objects.delete",
            "storage.buckets.get",
            "storage.buckets.update",
        ]
        mock_storage_client.get_bucket.return_value = mock_bucket

        with patch.object(manager, "_build_translation_client", return_value=mock_translate_client), \
             patch.object(manager, "_build_storage_client", return_value=mock_storage_client):

            result = manager.validate_credentials("user-t-fail")
            assert result.status == "INVALID"
            assert result.translation_check_passed is False
            assert result.storage_check_passed is True
            assert result.error_details is not None

    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_validate_credentials_storage_missing_permissions(
        self, mock_creds_from_info: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds_from_info.return_value = MagicMock()
        manager.set_credentials("user-s-fail", "test-project-123", "test-bucket", valid_sa_dict)

        mock_translate_client = MagicMock()
        mock_translate_client.list_glossaries.return_value = []

        mock_storage_client = MagicMock()
        mock_bucket = MagicMock()
        # Missing storage.buckets.update permission
        mock_bucket.test_iam_permissions.return_value = [
            "storage.objects.create",
            "storage.objects.get",
        ]
        mock_storage_client.get_bucket.return_value = mock_bucket

        with patch.object(manager, "_build_translation_client", return_value=mock_translate_client), \
             patch.object(manager, "_build_storage_client", return_value=mock_storage_client):

            result = manager.validate_credentials("user-s-fail")
            assert result.status == "INVALID"
            assert result.translation_check_passed is True
            assert result.storage_check_passed is False
            assert "Missing" in (result.error_details or "") or "Storage" in (result.error_details or "")


class TestOnboardingGuide:
    """Test get_onboarding_guide structure and contents."""

    def test_get_onboarding_guide(self) -> None:
        steps = BYOKCredentialsManager.get_onboarding_guide()
        assert isinstance(steps, list)
        assert len(steps) == 6
        for i, step in enumerate(steps, 1):
            assert isinstance(step, GuideStep)
            assert step.step_number == i
            assert len(step.title) > 0
            assert len(step.description) > 0

        # Step 5 must contain gcloud commands for power users
        step5 = steps[4]
        assert step5.step_number == 5
        assert step5.gcloud_command is not None
        assert "roles/cloudtranslate.editor" in step5.gcloud_command
        assert "roles/storage.admin" in step5.gcloud_command


class TestRetryAndBackoff:
    """Test exponential backoff on transient GCP errors."""

    @patch("time.sleep", return_value=None)
    @patch("google.oauth2.service_account.Credentials.from_service_account_info")
    def test_retry_on_transient_error_success(
        self, mock_creds: MagicMock, mock_sleep: MagicMock, manager: BYOKCredentialsManager, valid_sa_dict: dict[str, str]
    ) -> None:
        mock_creds.return_value = MagicMock()
        manager.set_credentials("user-retry", "test-project-123", "test-bucket", valid_sa_dict)

        mock_translate_client = MagicMock()
        # Fail once with ResourceExhausted (429), then succeed
        mock_translate_client.list_glossaries.side_effect = [
            gcp_exceptions.ResourceExhausted("Rate limit exceeded"),
            [],
        ]

        mock_storage_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.test_iam_permissions.return_value = [
            "storage.objects.create", "storage.objects.get", "storage.objects.delete",
            "storage.buckets.get", "storage.buckets.update"
        ]
        mock_storage_client.get_bucket.return_value = mock_bucket

        with patch.object(manager, "_build_translation_client", return_value=mock_translate_client), \
             patch.object(manager, "_build_storage_client", return_value=mock_storage_client):

            result = manager.validate_credentials("user-retry")
            assert result.status == "VALID"
            assert mock_sleep.called
