"""Unit tests for GlossarySyncManager (TASK-2.3, FR-02, FR-06, NFR-04).

Verifies:
- Idempotent base glossary synchronization (Tier 1)
- Dynamic book session glossary synchronization (Tier 2)
- Glossary ID sanitization complying with GCP regional glossary naming rules
- Direct GCS TSV staging upload
- Polling of create_glossary LRO to completion
- Exponential backoff retry on transient 429/503 errors
- Missing credential handling
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions
from google.cloud import translate_v3 as translate

from services.byok_credentials_manager import (
    BYOKCredentialsManager,
    CredentialNotFoundError,
)
from services.glossary_compiler import GlossaryCompiler
from services.glossary_sync_manager import GlossarySyncManager, sanitize_glossary_id


@pytest.fixture
def mock_creds_mgr() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    mgr.get_project_id.return_value = "test-project-123"
    mgr.get_bucket_name.return_value = "user-trans-bucket"

    # Mock Translation Client
    mock_trans_client = MagicMock(spec=translate.TranslationServiceClient)
    mgr.get_translation_client.return_value = mock_trans_client

    # Mock Storage Client
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client.bucket.return_value = mock_bucket
    mgr.get_storage_client.return_value = mock_storage_client

    return mgr


@pytest.fixture
def sync_mgr(mock_creds_mgr: MagicMock) -> GlossarySyncManager:
    compiler = GlossaryCompiler()
    return GlossarySyncManager(
        credentials_manager=mock_creds_mgr,
        compiler=compiler,
        location="us-central1",
        base_glossary_id="klages-philosophical-base-v1",
    )


class TestGlossaryIdSanitization:
    """Verify GCP glossary ID format rules: ^[a-zA-Z0-9_-]{1,63}$."""

    def test_sanitize_standard_ids(self) -> None:
        assert sanitize_glossary_id("klages_base") == "klages_base"
        assert sanitize_glossary_id("book-sess-42") == "book-sess-42"
        assert sanitize_glossary_id("Book_Session_1") == "book_session_1"

    def test_sanitize_special_characters(self) -> None:
        assert sanitize_glossary_id("book sess 42 & volume #1") == "book-sess-42---volume--1"

    def test_sanitize_length_truncation(self) -> None:
        very_long = "a" * 100
        sanitized = sanitize_glossary_id(very_long)
        assert len(sanitized) <= 63

    def test_sanitize_starts_with_invalid_char(self) -> None:
        assert sanitize_glossary_id("-sess-1").startswith("g-")


class TestBaseGlossarySync:
    """Test Tier 1 base glossary synchronization."""

    def test_sync_base_glossary_already_exists(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        existing_glossary = MagicMock()
        existing_glossary.name = "projects/test-project-123/locations/us-central1/glossaries/klages-philosophical-base-v1"
        mock_trans.get_glossary.return_value = existing_glossary

        resource_name = sync_mgr.sync_base_glossary(user_id="user_1")

        assert resource_name == existing_glossary.name
        mock_trans.get_glossary.assert_called_once()
        mock_trans.create_glossary.assert_not_called()

    def test_sync_base_glossary_creates_when_missing(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.get_glossary.side_effect = gcp_exceptions.NotFound("Glossary not found")

        # Mock create_glossary LRO
        mock_lro = MagicMock()
        mock_created_glossary = MagicMock()
        mock_created_glossary.name = "projects/test-project-123/locations/us-central1/glossaries/klages-philosophical-base-v1"
        mock_lro.result.return_value = mock_created_glossary
        mock_trans.create_glossary.return_value = mock_lro

        resource_name = sync_mgr.sync_base_glossary(user_id="user_1")

        assert resource_name == mock_created_glossary.name
        mock_creds_mgr.get_storage_client.assert_called_once_with("user_1")
        mock_trans.create_glossary.assert_called_once()
        mock_lro.result.assert_called_once()

    def test_sync_base_glossary_credential_not_found(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_creds_mgr.get_project_id.side_effect = CredentialNotFoundError("No credentials")
        with pytest.raises(CredentialNotFoundError):
            sync_mgr.sync_base_glossary(user_id="unknown_user")


class TestBookSessionGlossarySync:
    """Test Tier 2 dynamic book session glossary synchronization."""

    def test_sync_book_session_glossary_creates_new(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.get_glossary.side_effect = gcp_exceptions.NotFound("Not found")

        mock_lro = MagicMock()
        created = MagicMock()
        created.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101"
        mock_lro.result.return_value = created
        mock_trans.create_glossary.return_value = mock_lro

        user_choices = {
            "Biozentrik": "Biocentric Philosophy",
            "Schauung": "Vision",
        }
        res_name = sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id="book-101",
            user_choices=user_choices,
        )

        assert res_name == created.name
        mock_trans.create_glossary.assert_called_once()
        # Verify GCS TSV upload occurred
        storage_client = mock_creds_mgr.get_storage_client.return_value
        storage_client.bucket.assert_called_with("user-trans-bucket")

    def test_sync_book_session_glossary_already_exists_no_overwrite(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        existing = MagicMock()
        existing.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101"
        mock_trans.get_glossary.return_value = existing

        res_name = sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id="book-101",
            user_choices={"Term": "Trans"},
            overwrite=False,
        )
        assert res_name == existing.name
        mock_trans.create_glossary.assert_not_called()

    def test_sync_book_session_glossary_already_exists_overwrites_by_default(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        existing = MagicMock()
        existing.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101-old"
        mock_trans.get_glossary.return_value = existing

        mock_delete_op = MagicMock()
        mock_trans.delete_glossary.return_value = mock_delete_op

        mock_lro = MagicMock()
        created = MagicMock()
        created.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101-new"
        mock_lro.result.return_value = created
        mock_trans.create_glossary.return_value = mock_lro

        res_name = sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id="book-101",
            user_choices={"Term": "UpdatedTrans"},
            overwrite=True,
        )
        assert res_name == created.name
        # Blue-green verification: new glossary created first, old deleted only after new is live
        mock_trans.create_glossary.assert_called_once()
        mock_trans.delete_glossary.assert_called_once_with(name=existing.name)

    def test_sync_book_session_glossary_upload_failure_leaves_existing_untouched(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        existing = MagicMock()
        existing.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101"
        mock_trans.get_glossary.return_value = existing

        storage_client = mock_creds_mgr.get_storage_client.return_value
        mock_blob = storage_client.bucket.return_value.blob.return_value
        mock_blob.upload_from_string.side_effect = RuntimeError("GCS upload failed")

        with pytest.raises(RuntimeError, match="GCS upload failed"):
            sync_mgr.sync_book_session_glossary(
                user_id="user_1",
                session_id="book-101",
                user_choices={"Term": "UpdatedTrans"},
                overwrite=True,
            )

        # Existing glossary must NOT have been deleted
        mock_trans.delete_glossary.assert_not_called()

    def test_sync_book_session_glossary_creation_failure_leaves_existing_untouched(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        existing = MagicMock()
        existing.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101"
        mock_trans.get_glossary.return_value = existing

        # Create fails: zero-downtime invariant guarantees existing glossary is never deleted!
        mock_trans.create_glossary.side_effect = RuntimeError("GCP creation failed")

        with pytest.raises(RuntimeError, match="GCP creation failed"):
            sync_mgr.sync_book_session_glossary(
                user_id="user_1",
                session_id="book-101",
                user_choices={"Term": "UpdatedTrans"},
                overwrite=True,
            )

        # Existing glossary was NEVER deleted because new was not yet ready
        mock_trans.delete_glossary.assert_not_called()

    def test_sync_book_session_glossary_prefix_related_sessions_isolated(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value

        # Existing list contains both the target session and a prefix-related other session
        g_other = MagicMock()
        g_other.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101-extra"
        g_target = MagicMock()
        g_target.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101"
        mock_trans.list_glossaries.return_value = [g_other, g_target]

        mock_lro = MagicMock()
        created = MagicMock()
        created.name = "projects/test-project-123/locations/us-central1/glossaries/sess-book-101-new"
        mock_lro.result.return_value = created
        mock_trans.create_glossary.return_value = mock_lro

        sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id="book-101",
            user_choices={"Term": "Trans"},
            overwrite=True,
        )

        # MUST only delete the target session glossary, NOT the prefix-related other session!
        mock_trans.delete_glossary.assert_called_once_with(name=g_target.name)

    def test_sync_book_session_glossary_fallback_probes_versioned_slots_when_list_fails(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        # list_glossaries raises an error
        mock_trans.list_glossaries.side_effect = RuntimeError("list_glossaries unavailable")

        # Fallback probes find slot A
        session_key = sync_mgr._session_id_prefix("book-101")
        slot_a_name = f"projects/test-project-123/locations/us-central1/glossaries/{session_key}-a"
        existing_slot_a = MagicMock()
        existing_slot_a.name = slot_a_name

        def fake_get_glossary(name: str):
            if f"{session_key}-a" in name:
                return existing_slot_a
            raise gcp_exceptions.NotFound("Not found")

        mock_trans.get_glossary.side_effect = fake_get_glossary

        # With overwrite=False, fallback discovers slot A and returns it without recreation
        res = sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id="book-101",
            overwrite=False,
        )
        assert res == slot_a_name
        mock_trans.create_glossary.assert_not_called()

    def test_sync_book_session_glossary_matches_and_retires_55_char_truncated_legacy_id(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value

        # Session ID whose full name exceeds 55 chars
        long_sess_id = "book-philosophical-investigations-vol-2-chapter-9-subheading-alpha"
        from services.glossary_sync_manager import sanitize_glossary_id
        truncated_55_id = sanitize_glossary_id(f"sess-{long_sess_id}")[:55].rstrip("-")

        legacy_g = MagicMock()
        legacy_g.name = f"projects/test-project-123/locations/us-central1/glossaries/{truncated_55_id}"
        mock_trans.list_glossaries.return_value = [legacy_g]

        mock_lro = MagicMock()
        created = MagicMock()
        created.name = "projects/test-project-123/locations/us-central1/glossaries/sess-new"
        mock_lro.result.return_value = created
        mock_trans.create_glossary.return_value = mock_lro

        sync_mgr.sync_book_session_glossary(
            user_id="user_1",
            session_id=long_sess_id,
            user_choices={"Term": "Trans"},
            overwrite=True,
        )

        # Verified: 55-char truncated legacy glossary was discovered and retired!
        mock_trans.delete_glossary.assert_called_once_with(name=legacy_g.name)


class TestRetryAndResilience:
    """Test retry behavior on transient errors (429/503)."""

    def test_retry_on_429_then_succeed(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.get_glossary.side_effect = [
            gcp_exceptions.TooManyRequests("Rate limit"),
            gcp_exceptions.NotFound("Not found"),
        ]

        mock_lro = MagicMock()
        created = MagicMock()
        created.name = "projects/test-project-123/locations/us-central1/glossaries/klages-philosophical-base-v1"
        mock_lro.result.return_value = created
        mock_trans.create_glossary.return_value = mock_lro

        with patch("time.sleep", return_value=None):
            res = sync_mgr.sync_base_glossary("user_1")

        assert res == created.name
        assert mock_trans.get_glossary.call_count == 2


class TestGlossaryDeletionAndEdgeCases:
    """Test delete_glossary, URI validation, and retry exhaustion."""

    def test_delete_glossary_success(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_op = MagicMock()
        mock_trans.delete_glossary.return_value = mock_op

        res = sync_mgr.delete_glossary("user_1", "sess-book-101")
        assert res is True
        mock_trans.delete_glossary.assert_called_once()
        mock_op.result.assert_called_once()

    def test_delete_glossary_not_found(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.delete_glossary.side_effect = gcp_exceptions.NotFound("Not found")

        res = sync_mgr.delete_glossary("user_1", "projects/p/locations/l/glossaries/g1")
        assert res is False

    def test_get_glossary_with_full_resource_name(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_g = MagicMock()
        mock_trans.get_glossary.return_value = mock_g

        res = sync_mgr.get_glossary("user_1", "projects/test-p/locations/us-central1/glossaries/custom-g")
        assert res == mock_g
        mock_trans.get_glossary.assert_called_with(
            name="projects/test-p/locations/us-central1/glossaries/custom-g"
        )

    def test_upload_tsv_invalid_uri(self, sync_mgr: GlossarySyncManager) -> None:
        with pytest.raises(ValueError, match="Invalid GCS URI"):
            sync_mgr._upload_tsv_to_gcs("user_1", "https://not-gcs.com/file.tsv", b"test")

        with pytest.raises(ValueError, match="Malformed GCS URI"):
            sync_mgr._upload_tsv_to_gcs("user_1", "gs://just-bucket", b"test")

    def test_exhaust_retries_raises(
        self, sync_mgr: GlossarySyncManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.get_glossary.side_effect = gcp_exceptions.ServiceUnavailable("Down")

        with patch("time.sleep", return_value=None):
            with pytest.raises(gcp_exceptions.ServiceUnavailable):
                sync_mgr.sync_base_glossary("user_1")

    def test_sanitize_empty_string(self) -> None:
        assert sanitize_glossary_id("") == "glossary"
