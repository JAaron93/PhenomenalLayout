"""
services/gcp_batch_translation_service.py
==========================================
Track 1 — GCP Batch Translation Migration  (FR-03, FR-10, NFR-01, NFR-02, NFR-07)

Provides :class:`GCPBatchTranslationService`, a fully-async-compatible service
that submits PDF books to the Google Cloud Translation v3 *batch_translate_document*
API and streams translated output directly from GCS.

Design invariants
-----------------
- **Zero host PDF storage** — source and translated PDFs are never written to the
  local filesystem; all I/O is streamed directly to/from GCS.
- **Credentials in session memory only** — GCP credentials are obtained via
  :class:`~services.byok_credentials_manager.BYOKCredentialsManager` and are never
  written to disk or emitted to logs.
- **Exponential backoff** — transient HTTP 429 / 503 errors on ``submit_batch_job``
  are retried up to ``MAX_RETRIES`` times with jittered exponential delays.
- **Full type annotations** — every public symbol is annotated; the file begins with
  ``from __future__ import annotations`` so forward references are safe on Python 3.9+.
"""

from __future__ import annotations

import io
import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from google.cloud import translate_v3 as translate

from services.byok_credentials_manager import BYOKCredentialsManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry constants (NFR-02 — exponential backoff)
# ---------------------------------------------------------------------------
MAX_RETRIES: int = 5
_RETRY_BASE_DELAY_S: float = 1.0
_RETRY_MAX_DELAY_S: float = 60.0
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 503})
_RETRYABLE_GCP_EXCEPTIONS: tuple[type[Exception], ...] = (
    gcp_exceptions.TooManyRequests,
    gcp_exceptions.ServiceUnavailable,
)


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass
class BatchJobHandle:
    """Lightweight handle returned after a successful batch job submission.

    Attributes
    ----------
    operation_name:
        The fully-qualified LRO name returned by GCP, e.g.
        ``projects/my-project/locations/us-central1/operations/abc123``.
    gcs_output_uri_prefix:
        The GCS URI prefix under which translated output files will appear.
    user_id:
        Identifier of the end-user who owns this job (used for audit / BYOK
        credential look-up).
    source_lang:
        BCP-47 source language code, e.g. ``"de"``.
    target_lang:
        BCP-47 target language code, e.g. ``"en-US"``.
    submitted_at:
        Unix timestamp (seconds) at which the job was submitted.
    """

    operation_name: str
    gcs_output_uri_prefix: str
    user_id: str
    source_lang: str
    target_lang: str
    submitted_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GCPBatchTranslationService:
    """Orchestrates PDF book translation via the GCP Batch Document Translation API.

    The service is intentionally **stateless per request** — all per-user
    GCP clients are built lazily from credentials supplied by
    :class:`~services.byok_credentials_manager.BYOKCredentialsManager`, which
    keeps secrets in session memory only.

    Parameters
    ----------
    credentials_manager:
        Injected :class:`BYOKCredentialsManager` instance responsible for
        vending GCP :class:`google.oauth2.credentials.Credentials` objects for
        each ``user_id``.
    project_id:
        GCP project ID used as the parent resource for Translation API calls.
    location:
        GCP region for Translation API operations (default ``"us-central1"``).

    Example
    -------
    ::

        svc = GCPBatchTranslationService(
            credentials_manager=mgr,
            project_id="my-gcp-project",
        )
        gs_uri = await asyncio.to_thread(
            svc.upload_book_to_gcs,
            user_id="user-42",
            source=Path("/tmp/book.pdf"),
            gcs_destination_uri="gs://my-bucket/inputs/book.pdf",
        )
        handle = svc.submit_batch_job(
            user_id="user-42",
            gcs_input_uri=gs_uri,
            gcs_output_uri_prefix="gs://my-bucket/outputs/book/",
        )
        stream = svc.stream_translated_book(
            user_id="user-42",
            gcs_output_uri="gs://my-bucket/outputs/book/book_de_en-US.pdf",
        )
    """

    def __init__(
        self,
        credentials_manager: BYOKCredentialsManager,
        project_id: str | None = None,
        location: str = "us-central1",
    ) -> None:
        self._creds_manager = credentials_manager
        self._project_id = project_id
        self._location = location

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_project_id(self, user_id: str) -> str:
        if self._project_id:
            return self._project_id
        return self._creds_manager.get_project_id(user_id)

    def _get_storage_client(self, user_id: str) -> storage.Client:
        """Build a :class:`google.cloud.storage.Client` for *user_id*.

        Credentials are retrieved from session memory via
        :class:`BYOKCredentialsManager` and are **never** persisted to disk.

        Parameters
        ----------
        user_id:
            The end-user whose BYOK credentials should be used.

        Returns
        -------
        storage.Client
            An authenticated GCS client scoped to the user's credentials.
        """
        credentials = self._creds_manager.get_credentials(user_id)
        project_id = self._get_project_id(user_id)
        return storage.Client(project=project_id, credentials=credentials)

    def _get_translate_client(self, user_id: str) -> translate.TranslationServiceClient:
        """Build a :class:`~google.cloud.translate_v3.TranslationServiceClient` for *user_id*.

        Parameters
        ----------
        user_id:
            The end-user whose BYOK credentials should be used.

        Returns
        -------
        translate.TranslationServiceClient
            An authenticated Translation v3 client.
        """
        credentials = self._creds_manager.get_credentials(user_id)
        return translate.TranslationServiceClient(credentials=credentials)

    @staticmethod
    def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
        """Split a ``gs://bucket/blob`` URI into ``(bucket_name, blob_name)``.

        Parameters
        ----------
        gcs_uri:
            A fully-qualified GCS URI, e.g. ``"gs://my-bucket/path/to/file.pdf"``.

        Returns
        -------
        tuple[str, str]
            ``(bucket_name, blob_name)`` extracted from the URI.

        Raises
        ------
        ValueError
            If *gcs_uri* does not start with ``"gs://"`` or has no blob component.
        """
        if not gcs_uri.startswith("gs://"):
            raise ValueError(
                f"Invalid GCS URI — expected 'gs://bucket/blob', got: {gcs_uri!r}"
            )
        without_scheme = gcs_uri[len("gs://"):]
        parts = without_scheme.split("/", 1)
        if len(parts) != 2 or not parts[1]:
            raise ValueError(
                f"Invalid GCS URI — could not extract blob path from: {gcs_uri!r}"
            )
        bucket_name, blob_name = parts
        return bucket_name, blob_name

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Return a jittered exponential backoff delay for *attempt* (0-indexed).

        The delay is capped at :data:`_RETRY_MAX_DELAY_S` seconds and a random
        jitter of ±20 % is applied to avoid thundering-herd effects.

        Parameters
        ----------
        attempt:
            Zero-indexed retry attempt number.

        Returns
        -------
        float
            Seconds to sleep before the next attempt.
        """
        base = min(
            _RETRY_BASE_DELAY_S * math.pow(2, attempt),
            _RETRY_MAX_DELAY_S,
        )
        jitter = base * 0.2 * (2 * random.random() - 1)  # ±20 %
        return max(0.0, base + jitter)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Return ``True`` if *exc* represents a transient GCP error worth retrying.

        Parameters
        ----------
        exc:
            The exception raised by a GCP API call.

        Returns
        -------
        bool
            ``True`` for HTTP 429 / 503 GCP exceptions.
        """
        return isinstance(exc, _RETRYABLE_GCP_EXCEPTIONS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_book_to_gcs(
        self,
        user_id: str,
        source: str | BinaryIO | Path,
        gcs_destination_uri: str,
    ) -> str:
        """Stream a PDF book directly to GCS without touching the host filesystem.

        The method accepts three flavours of *source*:

        * ``str`` — treated as a filesystem path and opened as a binary stream.
        * :class:`pathlib.Path` — opened and streamed directly.
        * file-like object — streamed as-is (must be in ``'rb'`` mode).

        In all cases **zero bytes** of PDF content are buffered in memory beyond
        what the underlying GCS client requires for a single chunk.

        Parameters
        ----------
        user_id:
            Identifier of the requesting user; used to fetch BYOK credentials.
        source:
            PDF source — a filesystem path (``str`` or :class:`~pathlib.Path`)
            or an already-open binary file-like object.
        gcs_destination_uri:
            Target ``gs://bucket/path/to/file.pdf`` URI.

        Returns
        -------
        str
            The fully-qualified ``gs://…`` URI of the uploaded object, identical
            to *gcs_destination_uri*.

        Raises
        ------
        ValueError
            If *gcs_destination_uri* is malformed.
        FileNotFoundError
            If *source* is a path that does not exist.
        google.cloud.exceptions.GoogleCloudError
            On unrecoverable GCS errors.
        """
        bucket_name, blob_name = self._parse_gcs_uri(gcs_destination_uri)

        # Enforce 7-day auto-delete staging lifecycle policy if uploaded to staging prefix
        if blob_name.startswith("inputs/"):
            if not self.ensure_staging_lifecycle_policy(
                user_id=user_id,
                bucket_name=bucket_name,
                staging_prefix="inputs/",
                age_days=7,
            ):
                raise RuntimeError(
                    f"Failed to ensure 7-day auto-delete staging lifecycle policy on bucket '{bucket_name}' "
                    f"for staging object '{blob_name}'."
                )

        storage_client = self._get_storage_client(user_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        logger.info(
            "Uploading PDF to GCS | user=%s destination=%s",
            user_id,
            gcs_destination_uri,
        )

        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(
                    f"PDF source path does not exist: {source_path}"
                )
            # Open the file and stream it directly — no intermediate buffer
            with source_path.open("rb") as fh:
                blob.upload_from_file(fh, content_type="application/pdf")
        else:
            # Treat as an already-open binary file-like object (BinaryIO)
            blob.upload_from_file(source, content_type="application/pdf")

        logger.info(
            "Upload complete | user=%s gs_uri=%s size_bytes=%s",
            user_id,
            gcs_destination_uri,
            blob.size,
        )
        return gcs_destination_uri

    def ensure_staging_lifecycle_policy(
        self,
        user_id: str,
        bucket_name: str,
        staging_prefix: str = "inputs/",
        age_days: int = 7,
    ) -> bool:
        """Ensure a Delete lifecycle rule exists for the staging prefix on *bucket_name*.

        Idempotent — if a matching rule already exists the method returns ``True``
        immediately without patching the bucket.

        A rule is considered **matching** if:

        * ``rule['action']['type'] == 'Delete'``
        * *staging_prefix* appears in ``rule['condition']['matchesPrefix']``

        If no such rule is found, a new one is appended and the bucket is patched.

        Parameters
        ----------
        user_id:
            Identifier of the requesting user; used to fetch BYOK credentials.
        bucket_name:
            Name of the GCS bucket (without the ``gs://`` scheme).
        staging_prefix:
            Object name prefix to which the Delete rule should apply
            (default ``"inputs/"``).
        age_days:
            Number of days after which matching objects are deleted
            (default ``7``).

        Returns
        -------
        bool
            ``True`` if the lifecycle policy already existed or was successfully
            applied; ``False`` if an unexpected error prevented the patch
            (callers should treat ``False`` as a non-fatal warning).

        Raises
        ------
        google.cloud.exceptions.GoogleCloudError
            On unrecoverable GCS errors when fetching or patching the bucket.
        """
        storage_client = self._get_storage_client(user_id)
        bucket = storage_client.get_bucket(bucket_name)

        # Reload to ensure lifecycle_rules is populated
        bucket.reload()

        existing_rules: list[dict] = list(bucket.lifecycle_rules)

        for rule in existing_rules:
            action = rule.get("action", {})
            condition = rule.get("condition", {})
            if (
                action.get("type") == "Delete"
                and staging_prefix in condition.get("matchesPrefix", [])
                and condition.get("age") == age_days
            ):
                logger.info(
                    "Lifecycle policy already exists | user=%s bucket=%s prefix=%s age_days=%d",
                    user_id,
                    bucket_name,
                    staging_prefix,
                    age_days,
                )
                return True

        # No matching rule — append and patch
        new_rule: dict = {
            "action": {"type": "Delete"},
            "condition": {"age": age_days, "matchesPrefix": [staging_prefix]},
        }
        existing_rules.append(new_rule)
        bucket.lifecycle_rules = existing_rules

        try:
            bucket.patch()
        except Exception:
            logger.exception(
                "Failed to patch lifecycle policy | user=%s bucket=%s prefix=%s",
                user_id,
                bucket_name,
                staging_prefix,
            )
            return False

        logger.info(
            "Lifecycle policy applied | user=%s bucket=%s prefix=%s age_days=%d",
            user_id,
            bucket_name,
            staging_prefix,
            age_days,
        )
        return True

    def submit_batch_job(
        self,
        user_id: str,
        gcs_input_uri: str,
        gcs_output_uri_prefix: str,
        source_lang: str = "de",
        target_lang: str = "en-US",
        glossary_resource_name: str | None = None,
    ) -> str:
        """Submit a GCP batch document translation job and return the LRO name.

        The call is wrapped in an exponential-backoff retry loop (up to
        :data:`MAX_RETRIES` attempts) that retries on HTTP 429 and 503 errors.

        Parameters
        ----------
        user_id:
            Identifier of the requesting user; used to fetch BYOK credentials.
        gcs_input_uri:
            ``gs://`` URI pointing to the source PDF in GCS.
        gcs_output_uri_prefix:
            ``gs://`` URI prefix under which translated output will be written.
        source_lang:
            BCP-47 source language code (default ``"de"``).
        target_lang:
            BCP-47 target language code (default ``"en-US"``).
        glossary_resource_name:
            Optional fully-qualified glossary resource name, e.g.
            ``"projects/p/locations/us-central1/glossaries/my-glossary"``.
            When provided, the glossary is attached to every target-language
            config in the request.

        Returns
        -------
        str
            The fully-qualified LRO operation name returned by GCP, e.g.
            ``"projects/my-project/locations/us-central1/operations/abc123"``.

        Raises
        ------
        google.api_core.exceptions.GoogleAPICallError
            If all retry attempts are exhausted or the error is non-retryable.
        """
        # Enforce 7-day auto-delete staging lifecycle policy if input is in staging prefix
        in_bucket, in_blob = self._parse_gcs_uri(gcs_input_uri)
        if in_blob.startswith("inputs/"):
            if not self.ensure_staging_lifecycle_policy(
                user_id=user_id,
                bucket_name=in_bucket,
                staging_prefix="inputs/",
                age_days=7,
            ):
                raise RuntimeError(
                    f"Failed to ensure 7-day auto-delete staging lifecycle policy on bucket '{in_bucket}' "
                    f"for staging input '{in_blob}'."
                )

        translate_client = self._get_translate_client(user_id)
        project_id = self._get_project_id(user_id)
        parent = f"projects/{project_id}/locations/{self._location}"

        input_config = translate.BatchDocumentInputConfig(
            gcs_source=translate.GcsSource(input_uri=gcs_input_uri)
        )
        output_config = translate.BatchDocumentOutputConfig(
            gcs_destination=translate.GcsDestination(
                output_uri_prefix=gcs_output_uri_prefix
            )
        )

        # Build optional glossary config
        glossary_config: translate.TranslateTextGlossaryConfig | None = None
        if glossary_resource_name:
            glossary_config = translate.TranslateTextGlossaryConfig(
                glossary=glossary_resource_name
            )

        request_kwargs: dict = {
            "parent": parent,
            "source_language_code": source_lang,
            "target_language_codes": [target_lang],
            "input_configs": [input_config],
            "output_config": output_config,
        }
        if glossary_config is not None:
            request_kwargs["glossaries"] = {target_lang: glossary_config}

        request = translate.BatchTranslateDocumentRequest(**request_kwargs)

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    "Submitting batch translation job | user=%s input=%s "
                    "output_prefix=%s src=%s tgt=%s attempt=%d/%d",
                    user_id,
                    gcs_input_uri,
                    gcs_output_uri_prefix,
                    source_lang,
                    target_lang,
                    attempt + 1,
                    MAX_RETRIES,
                )
                operation = translate_client.batch_translate_document(request=request)
                operation_name: str = operation.operation.name
                logger.info(
                    "Batch job submitted | user=%s operation=%s",
                    user_id,
                    operation_name,
                )
                return operation_name

            except _RETRYABLE_GCP_EXCEPTIONS as exc:
                last_exc = exc
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Retryable GCP error on batch submit | user=%s attempt=%d/%d "
                    "error=%s sleeping=%.2fs",
                    user_id,
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)

            except Exception as exc:
                # Non-retryable — bubble up immediately
                logger.error(
                    "Non-retryable error on batch submit | user=%s error=%s",
                    user_id,
                    exc,
                )
                raise

        # All retries exhausted
        assert last_exc is not None  # guaranteed by loop structure
        logger.error(
            "All %d retry attempts exhausted for batch job | user=%s",
            MAX_RETRIES,
            user_id,
        )
        raise last_exc

    def stream_translated_book(
        self,
        user_id: str,
        gcs_output_uri: str,
    ) -> BinaryIO:
        """Open a streaming reader for a translated PDF stored in GCS.

        Uses :meth:`google.cloud.storage.Blob.open` in ``'rb'`` mode, which
        returns a server-side streaming object that reads lazily from GCS without
        buffering the entire file into memory and **without writing any bytes to
        the host disk**.

        Parameters
        ----------
        user_id:
            Identifier of the requesting user; used to fetch BYOK credentials.
        gcs_output_uri:
            ``gs://`` URI of the translated PDF object.

        Returns
        -------
        BinaryIO
            A readable, non-seekable binary stream backed by GCS.  Callers are
            responsible for closing the stream when finished.

        Raises
        ------
        ValueError
            If *gcs_output_uri* is malformed.
        google.cloud.exceptions.NotFound
            If the object does not exist at *gcs_output_uri*.
        google.cloud.exceptions.GoogleCloudError
            On other unrecoverable GCS errors.

        Notes
        -----
        The returned stream is **not** seekable.  If random-access is required
        the caller must buffer the stream themselves.
        """
        bucket_name, blob_name = self._parse_gcs_uri(gcs_output_uri)
        storage_client = self._get_storage_client(user_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        logger.info(
            "Opening streaming reader for translated PDF | user=%s uri=%s",
            user_id,
            gcs_output_uri,
        )

        # blob.open('rb') returns a google.cloud.storage.fileio.BlobReader which
        # satisfies the BinaryIO protocol and reads in lazy chunks from GCS.
        return blob.open("rb")  # type: ignore[return-value]
