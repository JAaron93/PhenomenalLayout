"""BYOK (Bring Your Own Key) credentials manager for GCP Batch Translation.

Implements TASK-1.2 requirements (FR-05, FR-08, NFR-03, NFR-05, NFR-11):
- All GCP service-account credentials live strictly in process memory.
- No credentials are ever written to disk, logs, or external stores.
- Dual-service validation (Cloud Translation + Cloud Storage) with
  exponential backoff on transient GCP errors (HTTP 429 / 503).
- Thread-safe in-memory credential store protected by a reentrant lock.
- All public methods are fully typed; every class carries a docstring.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage, translate_v3 as translate
from google.cloud.storage import Bucket, Client as StorageClient
from google.cloud.translate_v3 import TranslationServiceClient
from google.oauth2 import service_account

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# GCP region used for the Translation validation probe
_TRANSLATION_LOCATION: str = "us-central1"

# IAM permissions validated on the user's GCS bucket
_REQUIRED_BUCKET_PERMISSIONS: list[str] = [
    "storage.objects.create",
    "storage.objects.get",
    "storage.objects.delete",
    "storage.buckets.get",
    "storage.buckets.update",
]

# OAuth2 scopes required by the service account
_GCP_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/cloud-platform",
]

# Transient HTTP status codes that warrant a retry
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 503})

# Exponential-backoff configuration
_MAX_RETRIES: int = 5
_BACKOFF_BASE_S: float = 1.0   # initial wait in seconds
_BACKOFF_MULTIPLIER: float = 2.0
_BACKOFF_MAX_S: float = 32.0   # cap per retry interval

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class CredentialNotFoundError(KeyError):
    """Raised when a requested user_id has no stored credentials.

    Args:
        user_id: The identifier that was not found in the in-memory store.
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"No credentials stored for user_id={user_id!r}")
        self.user_id: str = user_id


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result returned by :meth:`BYOKCredentialsManager.validate_credentials`.

    Attributes:
        status: ``'VALID'`` when *both* service checks pass, otherwise
            ``'INVALID'``.
        translation_check_passed: Whether the Cloud Translation probe
            succeeded (``list_glossaries`` on ``us-central1``).
        storage_check_passed: Whether the Cloud Storage probe succeeded
            (``get_bucket`` + ``test_iam_permissions`` on the user's bucket).
        error_details: Human-readable description of any failure; ``None``
            when both checks pass.
    """

    status: str  # 'VALID' | 'INVALID'
    translation_check_passed: bool
    storage_check_passed: bool
    error_details: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"VALID", "INVALID"}:
            raise ValueError(f"status must be 'VALID' or 'INVALID', got {self.status!r}")


@dataclass(frozen=True)
class GuideStep:
    """A single step in the GCP BYOK onboarding guide.

    Attributes:
        step_number: 1-based ordinal position of this step.
        title: Short human-readable title.
        description: Detailed explanation of what the user should do.
        console_link: Optional URL to the relevant GCP Console page.
        gcloud_command: Optional shell snippet the user can run locally.
    """

    step_number: int
    title: str
    description: str
    console_link: str | None = None
    gcloud_command: str | None = None


@dataclass
class _CredentialRecord:
    """Internal representation of a single user's BYOK credential set.

    This is **not** exported; callers interact only through the manager's
    public interface.

    Attributes:
        user_id: Opaque identifier for the credential owner.
        project_id: GCP project ID associated with the service account.
        bucket_name: GCS bucket the user intends to use for translation I/O.
        credentials: A :class:`google.oauth2.service_account.Credentials`
            object constructed from the service-account JSON.  Never logged.
        raw_sa_info: The parsed service-account dict; held for diagnostics
            such as ``project_id`` cross-checks.  **Must never be logged.**
    """

    user_id: str
    project_id: str
    bucket_name: str
    credentials: service_account.Credentials
    raw_sa_info: dict[str, Any] = field(repr=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_retryable(exc: Exception) -> bool:
    """Return ``True`` when *exc* represents a transient GCP error.

    Checks both :mod:`google.api_core.exceptions` status codes and the
    ``status_code`` attribute that some SDK versions expose directly.
    """
    if isinstance(exc, gcp_exceptions.GoogleAPICallError):
        code = getattr(exc, "code", None)
        # gRPC status codes: RESOURCE_EXHAUSTED=8, UNAVAILABLE=14
        if code in {8, 14}:
            return True
        # HTTP status codes surfaced via ``http_status`` or similar
        http_status = getattr(exc, "http_status", None) or getattr(
            exc, "status_code", None
        )
        if http_status in _RETRYABLE_STATUS_CODES:
            return True
    # Fallback: check if any string representation contains the code
    for code_str in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"):
        if code_str in str(exc):
            return True
    return False


def _call_with_backoff(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call *fn* with up to :data:`_MAX_RETRIES` retries on transient errors.

    Uses truncated exponential backoff with a base of
    :data:`_BACKOFF_BASE_S` seconds and a ceiling of :data:`_BACKOFF_MAX_S`.

    Args:
        fn: Callable to invoke.
        *args: Positional arguments forwarded to *fn*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        Whatever *fn* returns on success.

    Raises:
        Exception: The last exception raised by *fn* after all retries are
            exhausted, or any non-retryable exception immediately.
    """
    last_exc: Exception | None = None
    wait: float = _BACKOFF_BASE_S

    for attempt in range(1, _MAX_RETRIES + 2):  # +2 so attempt 1 is the first try
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            if attempt > _MAX_RETRIES:
                break
            logger.warning(
                "Transient GCP error on attempt %d/%d — retrying in %.1fs: %s",
                attempt,
                _MAX_RETRIES,
                wait,
                type(exc).__name__,
            )
            time.sleep(wait)
            wait = min(wait * _BACKOFF_MULTIPLIER, _BACKOFF_MAX_S)

    # All retries exhausted
    assert last_exc is not None
    raise last_exc


def _parse_sa_json(sa_json_content: str | dict[str, Any]) -> dict[str, Any]:
    """Parse a service-account JSON blob into a plain ``dict``.

    Args:
        sa_json_content: Either a JSON *string* or an already-parsed ``dict``.

    Returns:
        Parsed service-account info as a ``dict``.

    Raises:
        ValueError: If the string cannot be parsed as JSON or the result is
            not a ``dict``.
    """
    if isinstance(sa_json_content, dict):
        return sa_json_content

    try:
        parsed: Any = json.loads(sa_json_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Service account JSON is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Service account JSON must be a JSON object, got {type(parsed).__name__}"
        )
    return parsed


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class BYOKCredentialsManager:
    """Thread-safe in-memory manager for user-supplied GCP service-account credentials.

    All credential material is stored exclusively in a process-local ``dict``
    guarded by a :class:`threading.RLock`.  Nothing is ever persisted to disk,
    written to a database, or emitted in log messages.

    Validation probes use non-billable GCP API calls:

    * **Translation**: ``projects.locations.glossaries.list`` with an empty
      filter string — this requires only ``roles/cloudtranslate.viewer`` and
      returns an empty page if no glossaries exist, which is fine.
    * **Storage**: ``buckets.get`` + ``buckets.testIamPermissions`` on the
      user-supplied bucket name.

    Transient errors (HTTP 429 / 503) are retried with truncated exponential
    backoff up to :data:`_MAX_RETRIES` times before being surfaced to the
    caller.

    Example usage::

        manager = BYOKCredentialsManager()
        manager.set_credentials(
            user_id="alice",
            project_id="my-gcp-project",
            bucket_name="my-translation-bucket",
            sa_json_content=open("sa.json").read(),
        )
        result = manager.validate_credentials("alice")
        if result.status == "VALID":
            client = manager.get_translation_client("alice")
    """

    def __init__(self) -> None:
        """Initialise the manager with an empty in-memory credential store."""
        # _store maps user_id -> _CredentialRecord
        self._store: dict[str, _CredentialRecord] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Credential lifecycle
    # ------------------------------------------------------------------

    def set_credentials(
        self,
        user_id: str,
        project_id: str,
        bucket_name: str,
        sa_json_content: str | dict[str, Any],
    ) -> bool:
        """Ingest and store GCP service-account credentials in process memory.

        The service-account JSON is parsed (if supplied as a string), turned
        into a scoped :class:`~google.oauth2.service_account.Credentials`
        object, and stored under *user_id*.  The raw dict is retained for
        cross-validation purposes but is **never** written to disk or logs.

        Args:
            user_id: Unique identifier for the credential owner.  Used as the
                in-memory store key.
            project_id: GCP project ID to target.
            bucket_name: GCS bucket name used for translation I/O.
            sa_json_content: Service-account JSON as a ``str`` or pre-parsed
                ``dict``.

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If *sa_json_content* cannot be parsed or is missing
                required fields.
        """
        sa_info: dict[str, Any] = _parse_sa_json(sa_json_content)

        try:
            creds: service_account.Credentials = (
                service_account.Credentials.from_service_account_info(
                    sa_info, scopes=_GCP_SCOPES
                )
            )
        except Exception as exc:
            raise ValueError(
                f"Could not construct service account credentials: {exc}"
            ) from exc

        record = _CredentialRecord(
            user_id=user_id,
            project_id=project_id,
            bucket_name=bucket_name,
            credentials=creds,
            raw_sa_info=sa_info,
        )

        with self._lock:
            self._store[user_id] = record

        logger.info("Credentials stored for user_id=%s", user_id)
        return True

    def clear_credentials(self, user_id: str) -> None:
        """Remove the stored credentials for *user_id* from process memory.

        Silently succeeds if *user_id* is not currently in the store, so
        callers do not need to check existence before clearing.

        Args:
            user_id: Identifier whose credentials should be removed.
        """
        with self._lock:
            self._store.pop(user_id, None)
        logger.info("Credentials cleared for user_id=%s", user_id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_credentials(self, user_id: str) -> ValidationResult:
        """Perform dual-service validation of the stored credentials.

        Runs two independent non-billable probes:

        1. **Translation** — ``list_glossaries`` against
           ``projects/{project_id}/locations/us-central1`` with ``filter=''``.
        2. **Storage** — ``get_bucket(bucket_name)`` followed by
           ``test_iam_permissions`` with :data:`_REQUIRED_BUCKET_PERMISSIONS`.

        Both probes use :func:`_call_with_backoff` for resilience against
        transient GCP errors.  The aggregate ``status`` is ``'VALID'`` only
        when *both* checks pass.

        Args:
            user_id: Identifier whose credentials should be validated.

        Returns:
            A :class:`ValidationResult` describing which checks passed and any
            error detail string.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)

        translation_ok: bool = False
        storage_ok: bool = False
        errors: list[str] = []

        # --- Translation probe ---
        try:
            translation_client: TranslationServiceClient = (
                self._build_translation_client(record)
            )
            parent: str = (
                f"projects/{record.project_id}/locations/{_TRANSLATION_LOCATION}"
            )
            _call_with_backoff(
                translation_client.list_glossaries,
                request={"parent": parent, "filter": ""},
            )
            translation_ok = True
            logger.info(
                "Translation validation passed for user_id=%s", user_id
            )
        except Exception as exc:
            msg = f"Translation check failed: {type(exc).__name__}: {exc}"
            logger.warning(
                "Translation validation failed for user_id=%s: %s",
                user_id,
                type(exc).__name__,
            )
            errors.append(msg)

        # --- Storage probe ---
        try:
            storage_client_obj: StorageClient = self._build_storage_client(record)
            bucket: Bucket = _call_with_backoff(
                storage_client_obj.get_bucket, record.bucket_name
            )
            granted: list[str] = _call_with_backoff(
                bucket.test_iam_permissions,
                _REQUIRED_BUCKET_PERMISSIONS,
            )
            missing: list[str] = [
                p for p in _REQUIRED_BUCKET_PERMISSIONS if p not in granted
            ]
            if missing:
                raise PermissionError(
                    f"Service account is missing bucket permissions: {missing}"
                )
            storage_ok = True
            logger.info(
                "Storage validation passed for user_id=%s", user_id
            )
        except Exception as exc:
            msg = f"Storage check failed: {type(exc).__name__}: {exc}"
            logger.warning(
                "Storage validation failed for user_id=%s: %s",
                user_id,
                type(exc).__name__,
            )
            errors.append(msg)

        status: str = "VALID" if (translation_ok and storage_ok) else "INVALID"
        error_details: str | None = "\n".join(errors) if errors else None

        return ValidationResult(
            status=status,
            translation_check_passed=translation_ok,
            storage_check_passed=storage_ok,
            error_details=error_details,
        )

    # ------------------------------------------------------------------
    # Authenticated client accessors
    # ------------------------------------------------------------------

    def get_translation_client(self, user_id: str) -> TranslationServiceClient:
        """Return a :class:`~google.cloud.translate_v3.TranslationServiceClient` for *user_id*.

        The client is constructed fresh on each call using the credentials
        held in memory.  Callers should close the client when they are done
        with it to release gRPC channel resources.

        Args:
            user_id: Identifier whose stored credentials should be used.

        Returns:
            An authenticated ``TranslationServiceClient``.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)
        logger.debug("Building TranslationServiceClient for user_id=%s", user_id)
        return self._build_translation_client(record)

    def get_storage_client(self, user_id: str) -> StorageClient:
        """Return a :class:`~google.cloud.storage.Client` for *user_id*.

        The client is constructed fresh on each call.

        Args:
            user_id: Identifier whose stored credentials should be used.

        Returns:
            An authenticated ``google.cloud.storage.Client``.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)
        logger.debug("Building StorageClient for user_id=%s", user_id)
        return self._build_storage_client(record)

    def get_credentials(self, user_id: str) -> service_account.Credentials:
        """Return the Google OAuth2 service-account credentials for *user_id*.

        Args:
            user_id: Identifier whose stored credentials should be returned.

        Returns:
            The in-memory :class:`service_account.Credentials`.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)
        return record.credentials

    def get_project_id(self, user_id: str) -> str:
        """Return the GCP project ID associated with *user_id* credentials.

        Args:
            user_id: Identifier to look up.

        Returns:
            GCP project ID string.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)
        return record.project_id

    def get_bucket_name(self, user_id: str) -> str:
        """Return the GCS bucket name associated with *user_id*.

        Args:
            user_id: Identifier to look up.

        Returns:
            GCS bucket name string.

        Raises:
            CredentialNotFoundError: If *user_id* has no stored credentials.
        """
        record = self._get_record(user_id)
        return record.bucket_name

    def has_credentials(self, user_id: str) -> bool:
        """Return True if credentials exist in memory for *user_id*.

        Args:
            user_id: Identifier to check.

        Returns:
            bool indicating whether credentials are stored.
        """
        with self._lock:
            return user_id in self._store

    # ------------------------------------------------------------------
    # Onboarding guide
    # ------------------------------------------------------------------

    @staticmethod
    def get_onboarding_guide() -> list[GuideStep]:
        """Return the six-step GCP BYOK onboarding guide.

        Each :class:`GuideStep` includes a human-readable title, description,
        an optional GCP Console link, and an optional ``gcloud`` shell snippet.

        Returns:
            An ordered list of six :class:`GuideStep` objects covering account
            creation through credential upload and validation.
        """
        return [
            GuideStep(
                step_number=1,
                title="Create a GCP Account & Claim Free Credits",
                description=(
                    "Sign in to Google Cloud at console.cloud.google.com. "
                    "New accounts receive $300 in free credits valid for 90 days, "
                    "which is more than enough to evaluate batch document translation. "
                    "No charges are incurred until you manually upgrade to a paid account."
                ),
                console_link="https://console.cloud.google.com",
                gcloud_command=None,
            ),
            GuideStep(
                step_number=2,
                title="Create a GCP Project",
                description=(
                    "A project is the top-level container for all GCP resources. "
                    "Click 'Create Project', give it a unique name (e.g., "
                    "'my-translation-project'), and note the generated Project ID — "
                    "you will need it later. All APIs, service accounts, and buckets "
                    "are scoped to this project."
                ),
                console_link="https://console.cloud.google.com/projectcreate",
                gcloud_command=None,
            ),
            GuideStep(
                step_number=3,
                title="Enable Required APIs (Cloud Translation + Cloud Storage)",
                description=(
                    "Navigate to the API Library and search for 'Cloud Translation API' "
                    "and 'Cloud Storage API'. Enable both. Without these enabled, API "
                    "calls from the service account will be rejected with a 403 error. "
                    "Alternatively, run the gcloud command shown below."
                ),
                console_link="https://console.cloud.google.com/apis/library",
                gcloud_command=(
                    "gcloud services enable translate.googleapis.com"
                    " storage.googleapis.com"
                ),
            ),
            GuideStep(
                step_number=4,
                title="Create a GCS Bucket in us-central1",
                description=(
                    "Create a Cloud Storage bucket to hold source and translated "
                    "documents. Choose a globally unique name. "
                    "Important: select 'us-central1' as the region — the GCP Batch "
                    "Translation job requires the bucket to be co-located with the "
                    "Translation API endpoint. Enable uniform bucket-level access for "
                    "simpler IAM management."
                ),
                console_link="https://console.cloud.google.com/storage/create-bucket",
                gcloud_command=(
                    "gcloud storage buckets create gs://[BUCKET]"
                    " --location=us-central1"
                ),
            ),
            GuideStep(
                step_number=5,
                title="Create a Service Account & Download JSON Key",
                description=(
                    "Create a dedicated service account for PhenomenalLayout "
                    "(e.g., 'phenomenal-sa'). Grant it the "
                    "'Cloud Translation Editor' role on the project and the "
                    "'Storage Admin' role on the bucket. Then generate a JSON key "
                    "and download it — this is the file you will paste into "
                    "PhenomenalLayout. "
                    "Replace [PROJ] with your Project ID and [BUCKET] with your "
                    "bucket name in the commands below. "
                    "Keep the downloaded JSON key secure; treat it like a password."
                ),
                console_link=(
                    "https://console.cloud.google.com/iam-admin/serviceaccounts"
                ),
                gcloud_command=(
                    "# 1. Enable APIs (if not already done)\n"
                    "gcloud services enable translate.googleapis.com"
                    " storage.googleapis.com\n\n"
                    "# 2. Create the bucket\n"
                    "gcloud storage buckets create gs://[BUCKET]"
                    " --location=us-central1\n\n"
                    "# 3. Create the service account\n"
                    "gcloud iam service-accounts create phenomenal-sa\n\n"
                    "# 4. Grant Translation Editor role on the project\n"
                    "gcloud projects add-iam-policy-binding [PROJ] \\\n"
                    "  --member=\"serviceAccount:phenomenal-sa@[PROJ]"
                    ".iam.gserviceaccount.com\" \\\n"
                    "  --role=\"roles/cloudtranslate.editor\"\n\n"
                    "# 5. Grant Storage Admin role on the bucket\n"
                    "gcloud storage buckets add-iam-policy-binding gs://[BUCKET] \\\n"
                    "  --member=\"serviceAccount:phenomenal-sa@[PROJ]"
                    ".iam.gserviceaccount.com\" \\\n"
                    "  --role=\"roles/storage.admin\"\n\n"
                    "# 6. Download the JSON key\n"
                    "gcloud iam service-accounts keys create credentials.json \\\n"
                    "  --iam-account=phenomenal-sa@[PROJ].iam.gserviceaccount.com"
                ),
            ),
            GuideStep(
                step_number=6,
                title="Upload & Validate Your Credentials",
                description=(
                    "Paste the full contents of your downloaded credentials.json "
                    "into the 'Service Account JSON' field in PhenomenalLayout, "
                    "enter your Project ID and bucket name, then click "
                    "'Validate Credentials'. "
                    "The system will perform non-billable probe calls to both the "
                    "Cloud Translation API and your GCS bucket to confirm everything "
                    "is wired up correctly. A green 'VALID' badge means you are ready "
                    "to translate documents."
                ),
                console_link=None,
                gcloud_command=None,
            ),
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_record(self, user_id: str) -> _CredentialRecord:
        """Retrieve the stored :class:`_CredentialRecord` for *user_id*.

        Args:
            user_id: Identifier to look up.

        Returns:
            The corresponding ``_CredentialRecord``.

        Raises:
            CredentialNotFoundError: If *user_id* is not in the store.
        """
        with self._lock:
            record = self._store.get(user_id)
        if record is None:
            raise CredentialNotFoundError(user_id)
        return record

    @staticmethod
    def _build_translation_client(
        record: _CredentialRecord,
    ) -> TranslationServiceClient:
        """Construct a :class:`TranslationServiceClient` from *record*.

        Args:
            record: The credential record containing a scoped
                :class:`~google.oauth2.service_account.Credentials` object.

        Returns:
            An authenticated ``TranslationServiceClient``.
        """
        return translate.TranslationServiceClient(credentials=record.credentials)

    @staticmethod
    def _build_storage_client(record: _CredentialRecord) -> StorageClient:
        """Construct a :class:`~google.cloud.storage.Client` from *record*.

        Args:
            record: The credential record containing a scoped
                :class:`~google.oauth2.service_account.Credentials` object.

        Returns:
            An authenticated ``google.cloud.storage.Client`` bound to the
            project associated with the service account.
        """
        return storage.Client(
            project=record.project_id,
            credentials=record.credentials,
        )
