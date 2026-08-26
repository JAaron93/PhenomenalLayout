"""services/glossary_sync_manager.py
====================================
Track 2 — Dual-Tier Glossary Sync & Persistent User Vocabulary Store
Traceability: FR-02, FR-06, NFR-04

Provides :class:`GlossarySyncManager`, managing Google Cloud Translation v3
regional glossaries in `us-central1` across two tiers:
- **Tier 1 (Persistent Base Glossary)**: Static philosophical foundation dictionary
  (e.g. `klages-philosophical-base-v1`) provisioned once per user GCP project.
- **Tier 2 (Dynamic Book Session Glossary)**: Combined runtime vocabulary uploaded to GCS
  and provisioned for specific translation jobs.

Design invariants:
- **Idempotent Provisioning** — checks for active glossaries before dispatching `create_glossary`.
- **RFC 4180 Strict TSV Staging** — uploads compliant TSVs to `gs://<user_bucket>/glossaries/...`.
- **GCP Naming Compliance** — sanitizes glossary IDs to match `^[a-zA-Z0-9_-]{1,63}$`.
- **Exponential Backoff Retry** — retries transient 429/503 errors on all GCP API interactions.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import time
import uuid
from typing import Any, Callable, TypeVar

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from google.cloud import translate_v3 as translate

from config.settings import gcp_settings
from services.byok_credentials_manager import BYOKCredentialsManager
from services.glossary_compiler import GlossaryCompiler

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 5
_RETRY_BASE_DELAY_S: float = 1.0
_RETRY_MAX_DELAY_S: float = 30.0
_RETRYABLE_GCP_EXCEPTIONS: tuple[type[Exception], ...] = (
    gcp_exceptions.TooManyRequests,
    gcp_exceptions.ServiceUnavailable,
)

T = TypeVar("T")


def _retry_with_backoff(operation_desc: str, fn: Callable[[], T]) -> T:
    """Execute *fn* with exponential backoff on retryable GCP exceptions."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except _RETRYABLE_GCP_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                logger.error(
                    "Exhausted retries (%d/%d) during %s: %s",
                    attempt,
                    MAX_RETRIES,
                    operation_desc,
                    exc,
                )
                raise
            delay = min(_RETRY_MAX_DELAY_S, _RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
            jitter = delay * random.uniform(0.1, 0.3)
            total_delay = delay + jitter
            logger.warning(
                "Retryable error on attempt %d/%d for %s: %s. Retrying in %.2fs...",
                attempt,
                MAX_RETRIES,
                operation_desc,
                exc,
                total_delay,
            )
            time.sleep(total_delay)
        except Exception:
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"Unexpected termination of retry loop for {operation_desc}")


def sanitize_glossary_id(raw_id: str) -> str:
    """Sanitize a raw string into a compliant GCP glossary ID.

    Requirements:
    - Characters allowed: [a-z0-9_-]
    - Must start with letter or digit
    - Maximum 63 characters
    """
    cleaned = raw_id.lower().strip()
    # Replace invalid chars with hyphen
    cleaned = re.sub(r"[^a-z0-9_-]", "-", cleaned)
    # Ensure it starts with alphanumeric char
    if cleaned and not cleaned[0].isalnum():
        cleaned = f"g{cleaned}"
    elif not cleaned:
        cleaned = "glossary"

    # Truncate to 63 chars max
    return cleaned[:63]


class GlossarySyncManager:
    """Orchestrates GCP Cloud Translation v3 glossary synchronization and GCS staging."""

    def __init__(
        self,
        credentials_manager: BYOKCredentialsManager,
        compiler: GlossaryCompiler | None = None,
        location: str = "us-central1",
        base_glossary_id: str | None = None,
    ) -> None:
        """Initialize GlossarySyncManager.

        Parameters
        ----------
        credentials_manager:
            BYOKCredentialsManager vending authenticated GCP clients for users.
        compiler:
            GlossaryCompiler for generating RFC 4180 TSV bytes.
        location:
            GCP region endpoint (default: us-central1).
        base_glossary_id:
            Tier 1 foundation glossary ID (defaults to gcp_settings.gcp_base_glossary_id).
        """
        self._creds_manager = credentials_manager
        self._compiler = compiler or GlossaryCompiler()
        self._location = location or gcp_settings.gcp_location
        self._base_glossary_id = sanitize_glossary_id(
            base_glossary_id or gcp_settings.gcp_base_glossary_id
        )

    def _get_project_id(self, user_id: str) -> str:
        return self._creds_manager.get_project_id(user_id)

    def _get_bucket_name(self, user_id: str) -> str:
        return self._creds_manager.get_bucket_name(user_id)

    def _get_translate_client(self, user_id: str) -> translate.TranslationServiceClient:
        return self._creds_manager.get_translation_client(user_id)

    def _get_storage_client(self, user_id: str) -> storage.Client:
        return self._creds_manager.get_storage_client(user_id)

    def _format_glossary_name(self, project_id: str, glossary_id: str) -> str:
        return f"projects/{project_id}/locations/{self._location}/glossaries/{glossary_id}"

    def _upload_tsv_to_gcs(self, user_id: str, gcs_uri: str, tsv_bytes: bytes) -> str:
        """Upload TSV bytes directly to the user's GCS bucket without host disk caching."""
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")

        parts = gcs_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Malformed GCS URI: {gcs_uri}")

        bucket_name, blob_name = parts[0], parts[1]
        storage_client = self._get_storage_client(user_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        def _do_upload() -> None:
            blob.upload_from_string(
                tsv_bytes,
                content_type="text/tab-separated-values; charset=utf-8",
            )

        _retry_with_backoff(f"upload TSV to {gcs_uri}", _do_upload)
        logger.info("Uploaded glossary TSV to %s (%d bytes)", gcs_uri, len(tsv_bytes))
        return gcs_uri

    def get_glossary(self, user_id: str, glossary_id_or_name: str) -> translate.Glossary | None:
        """Retrieve existing glossary metadata from GCP Translation v3.

        Returns None if the glossary does not exist.
        """
        project_id = self._get_project_id(user_id)
        if glossary_id_or_name.startswith("projects/"):
            full_name = glossary_id_or_name
        else:
            full_name = self._format_glossary_name(
                project_id, sanitize_glossary_id(glossary_id_or_name)
            )

        client = self._get_translate_client(user_id)

        def _do_get() -> translate.Glossary | None:
            try:
                return client.get_glossary(name=full_name)
            except gcp_exceptions.NotFound:
                return None

        return _retry_with_backoff(f"get_glossary({full_name})", _do_get)

    def sync_base_glossary(self, user_id: str) -> str:
        """Synchronize persistent Tier 1 base foundation glossary in user's GCP region.

        Idempotent: if the glossary already exists, returns its resource name immediately.
        Otherwise compiles the base dictionary, stages TSV to GCS, and provisions the glossary.
        """
        project_id = self._get_project_id(user_id)
        bucket_name = self._get_bucket_name(user_id)
        glossary_id = self._base_glossary_id
        glossary_name = self._format_glossary_name(project_id, glossary_id)

        # Check if already provisioned
        existing = self.get_glossary(user_id, glossary_id)
        if existing is not None:
            logger.info("Tier 1 base glossary already exists: %s", existing.name)
            return existing.name

        logger.info("Provisioning Tier 1 base glossary %s for user %s", glossary_id, user_id)

        # 1. Compile base TSV
        tsv_bytes = self._compiler.compile_tsv(include_base=True, include_user_vocab=False)

        # 2. Stage TSV to GCS
        gcs_uri = f"gs://{bucket_name}/glossaries/base/{glossary_id}.tsv"
        self._upload_tsv_to_gcs(user_id, gcs_uri, tsv_bytes)

        # 3. Create regional glossary resource
        return self._create_glossary_resource(
            user_id=user_id,
            project_id=project_id,
            glossary_id=glossary_id,
            glossary_name=glossary_name,
            gcs_input_uri=gcs_uri,
        )

    @staticmethod
    def _session_token(session_id: str) -> str:
        """Compute deterministic 16-char SHA-256 hash for exact session isolation."""
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]

    def _session_id_prefix(self, session_id: str) -> str:
        """Compute isolated session prefix containing both readable slug and session hash."""
        clean_slug = re.sub(r"[^a-z0-9_-]", "-", session_id.lower().strip()).strip("-")[:28]
        if not clean_slug:
            clean_slug = "book"
        token = self._session_token(session_id)
        return f"sess-{clean_slug}-{token}"

    def _find_session_glossaries(self, user_id: str, session_id: str) -> list[translate.Glossary]:
        """Find active regional glossaries belonging strictly to *session_id*.

        Matches:
        1. Legacy exact ID (`sess-{session_id}` exact match only, never substring or prefix match).
        2. Versioned Blue-Green glossaries bearing the exact SHA-256 session token (`sess-{slug}-{token}-{version}`).
        """
        session_key = self._session_id_prefix(session_id)
        legacy_exact_id = sanitize_glossary_id(f"sess-{session_id}")

        client = self._get_translate_client(user_id)
        project_id = self._get_project_id(user_id)
        parent = f"projects/{project_id}/locations/{self._location}"

        matches: list[translate.Glossary] = []
        try:
            glossary_iter = client.list_glossaries(parent=parent)
            if glossary_iter:
                for g in glossary_iter:
                    g_name = getattr(g, "name", "")
                    g_id = g_name.split("/")[-1]
                    # Disallow partial prefix overlaps: match EXACT legacy ID or exact hash key
                    if g_id == legacy_exact_id or g_id == session_key or g_id.startswith(f"{session_key}-"):
                        matches.append(g)
        except Exception:
            logger.debug("list_glossaries check failed; falling back to get_glossary")

        # Fallback to direct get_glossary lookup if list_glossaries returned no matches
        if not matches:
            candidates = [session_key]
            if legacy_exact_id != session_key:
                candidates.append(legacy_exact_id)
            for candidate_id in candidates:
                exact = self.get_glossary(user_id, candidate_id)
                if exact is not None:
                    matches.append(exact)

        # Deduplicate matches by full resource name
        seen_names: set[str] = set()
        unique_matches: list[translate.Glossary] = []
        for g in matches:
            name = getattr(g, "name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                unique_matches.append(g)

        return unique_matches

    def sync_book_session_glossary(
        self,
        user_id: str,
        session_id: str,
        user_choices: dict[str, Any] | None = None,
        overwrite: bool = True,
    ) -> str:
        """Synchronize dynamic Tier 2 book session glossary in user's GCP region.

        Combines base foundation terms, persistent user vocabulary, and session overrides.
        Uses zero-downtime blue-green replacement: provisions the replacement glossary
        under a distinct versioned identifier and verifies it is fully READY before safely
        deleting superseded glossary resources.

        Parameters
        ----------
        user_id:
            User identifier for BYOK credential lookup.
        session_id:
            Book session identifier.
        user_choices:
            Dynamic session-level terminology overrides.
        overwrite:
            If True (default) and a session glossary already exists in GCP, creates a new
            verified replacement glossary before deleting the superseded resource.
            If False, returns existing active glossary immediately without recreation.
        """
        project_id = self._get_project_id(user_id)
        bucket_name = self._get_bucket_name(user_id)

        # 1. Check if an active glossary already exists for this session
        existing_glossaries = self._find_session_glossaries(user_id, session_id)
        if existing_glossaries and not overwrite:
            logger.info("Tier 2 session glossary already exists: %s", existing_glossaries[0].name)
            return existing_glossaries[0].name

        # 2. Compile merged TSV (Book Overrides > User Vocab > Base Dictionary)
        tsv_bytes = self._compiler.compile_tsv(
            session_overrides=user_choices,
            user_id=user_id,
            include_base=True,
            include_user_vocab=True,
        )

        # 3. Generate distinct versioned glossary ID with exact SHA-256 session token
        session_key = self._session_id_prefix(session_id)
        version_suffix = uuid.uuid4().hex[:6]
        new_glossary_id = f"{session_key}-{version_suffix}"
        new_glossary_name = self._format_glossary_name(project_id, new_glossary_id)

        # 4. Stage new TSV to GCS
        gcs_uri = f"gs://{bucket_name}/glossaries/sessions/{new_glossary_id}.tsv"
        self._upload_tsv_to_gcs(user_id, gcs_uri, tsv_bytes)

        logger.info(
            "Provisioning replacement Tier 2 glossary %s (blue-green) for user %s session %s",
            new_glossary_id,
            user_id,
            session_id,
        )

        # 5. Create new replacement glossary FIRST and await full READY status
        # Notice: Existing working glossary remains 100% active during this window!
        new_resource_name = self._create_glossary_resource(
            user_id=user_id,
            project_id=project_id,
            glossary_id=new_glossary_id,
            glossary_name=new_glossary_name,
            gcs_input_uri=gcs_uri,
        )

        # 6. ONLY AFTER the new replacement is verified live, safely clean up superseded glossaries
        if existing_glossaries:
            for old_g in existing_glossaries:
                old_name = getattr(old_g, "name", "")
                if old_name and old_name != new_resource_name:
                    logger.info("Safely retiring superseded glossary %s", old_name)
                    try:
                        self.delete_glossary(user_id, old_name)
                    except Exception:
                        logger.exception("Error retiring superseded glossary %s", old_name)

                    # Clean up old GCS TSV if available
                    if hasattr(old_g, "input_config") and hasattr(old_g.input_config, "gcs_source"):
                        old_input_uri = getattr(old_g.input_config.gcs_source, "input_uri", "")
                        if old_input_uri and old_input_uri != gcs_uri and old_input_uri.startswith("gs://"):
                            try:
                                parts = old_input_uri[5:].split("/", 1)
                                if len(parts) == 2:
                                    self._get_storage_client(user_id).bucket(parts[0]).blob(parts[1]).delete()
                                    logger.debug("Cleaned up superseded session TSV: %s", old_input_uri)
                            except Exception:
                                pass

        return new_resource_name

    def _create_glossary_resource(
        self,
        user_id: str,
        project_id: str,
        glossary_id: str,
        glossary_name: str,
        gcs_input_uri: str,
    ) -> str:
        """Dispatch create_glossary call and poll LRO to completion."""
        client = self._get_translate_client(user_id)
        parent = f"projects/{project_id}/locations/{self._location}"

        glossary = translate.Glossary(
            name=glossary_name,
            language_pair=translate.Glossary.LanguageCodePair(
                source_language_code="de",
                target_language_code="en",
            ),
            input_config=translate.GlossaryInputConfig(
                gcs_source=translate.GcsSource(input_uri=gcs_input_uri)
            ),
        )

        def _do_create() -> Any:
            return client.create_glossary(parent=parent, glossary=glossary)

        lro_operation = _retry_with_backoff(f"create_glossary({glossary_name})", _do_create)
        logger.info(
            "Dispatched create_glossary LRO | name=%s operation=%s",
            glossary_name,
            getattr(lro_operation, "operation", {}),
        )

        # Await LRO result
        created_glossary = lro_operation.result(timeout=180.0)
        logger.info("Successfully provisioned glossary: %s", created_glossary.name)
        return created_glossary.name

    def delete_glossary(self, user_id: str, glossary_id_or_name: str) -> bool:
        """Delete a glossary resource in GCP. Returns True if deleted, False if not found."""
        project_id = self._get_project_id(user_id)
        if glossary_id_or_name.startswith("projects/"):
            full_name = glossary_id_or_name
        else:
            full_name = self._format_glossary_name(
                project_id, sanitize_glossary_id(glossary_id_or_name)
            )

        client = self._get_translate_client(user_id)

        def _do_delete() -> bool:
            try:
                op = client.delete_glossary(name=full_name)
                op.result(timeout=60.0)
                logger.info("Deleted glossary: %s", full_name)
                return True
            except gcp_exceptions.NotFound:
                logger.warning("Glossary %s not found for deletion", full_name)
                return False

        return _retry_with_backoff(f"delete_glossary({full_name})", _do_delete)
