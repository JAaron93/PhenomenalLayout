"""LRO Progress Monitor for GCP Batch Document Translation jobs.

Implements TASK-1.4 (FR-04, NFR-02): Polls Google Cloud Long-Running Operations
produced by ``batchTranslateDocument``, extracts ``BatchTranslateDocumentMetadata``
progress fields, and computes completion percentage and time-remaining estimates.

Key design invariants (per AGENTS.md):
- Credentials stay in session memory — never written to disk or logs.
- All GCP calls use exponential backoff on transient HTTP 429/503 errors.
- Non-blocking I/O: blocking polling is delegated to ``asyncio.to_thread`` callers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from google.api_core import exceptions as api_exceptions
from google.cloud import translate_v3 as translate
from google.protobuf import any_pb2  # noqa: F401 – available for callers

from services.byok_credentials_manager import BYOKCredentialsManager

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration (exponential backoff – NFR-02)
# ---------------------------------------------------------------------------

#: Transient HTTP status codes that warrant a retry.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({429, 503})

#: Maximum number of retry attempts for a single ``poll_once`` call.
_MAX_RETRIES: int = 5

#: Base sleep duration (seconds) for the first backoff interval.
_BASE_BACKOFF_SECONDS: float = 1.0

#: Multiplicative factor applied to the sleep interval on each retry.
_BACKOFF_MULTIPLIER: float = 2.0

# ---------------------------------------------------------------------------
# Terminal and in-progress LRO state sets
# ---------------------------------------------------------------------------

#: States that indicate a job has finished (successfully or otherwise).
_DONE_STATES: frozenset[str] = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})

#: Valid LRO state names emitted by BatchTranslateDocumentMetadata.
_ALL_STATES: frozenset[str] = frozenset(
    {"SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLING", "CANCELLED"}
)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProgressUpdate:
    """Snapshot of a single LRO poll result.

    Attributes:
        operation_name: The fully-qualified LRO resource name, e.g.
            ``projects/my-project/locations/us-central1/operations/1234``.
        state: The current ``BatchTranslateDocumentMetadata.State`` name.
            One of ``SUBMITTED``, ``RUNNING``, ``SUCCEEDED``, ``FAILED``,
            ``CANCELLING``, or ``CANCELLED``.
        total_pages: Total number of pages in the submitted document set.
        translated_pages: Number of pages successfully translated so far.
        failed_pages: Number of pages that encountered translation errors.
        completion_pct: Fractional progress expressed as a percentage
            ``0.0–100.0``.  Computed as
            ``translated_pages / total_pages * 100`` when ``total_pages > 0``,
            otherwise ``0.0``.
        is_done: ``True`` when the operation has reached a terminal state
            (``SUCCEEDED``, ``FAILED``, or ``CANCELLED``).
        error_message: Human-readable error detail populated when the
            operation is in the ``FAILED`` state or when the LRO itself
            carries a non-OK ``error`` field.  ``None`` otherwise.
    """

    operation_name: str
    state: str
    total_pages: int
    translated_pages: int
    failed_pages: int
    completion_pct: float
    is_done: bool
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Monitor implementation
# ---------------------------------------------------------------------------


class LROProgressMonitor:
    """Polls GCP Long-Running Operations for batch document translation jobs.

    Each instance is scoped to a single :class:`BYOKCredentialsManager` so
    that user credentials remain isolated in session memory.

    Example usage::

        monitor = LROProgressMonitor(credentials_manager)
        update = monitor.poll_once(user_id="u1", operation_name="projects/.../operations/123")
        if not update.is_done:
            remaining = monitor.estimate_remaining_time(update, elapsed_seconds=42.0)

    Thread / async safety:
        ``poll_once`` performs blocking I/O.  When called from an async
        context, wrap it with ``asyncio.to_thread``::

            update = await asyncio.to_thread(monitor.poll_once, user_id, op_name)
    """

    def __init__(self, credentials_manager: BYOKCredentialsManager) -> None:
        """Initialise the monitor with a BYOK credential vault.

        Args:
            credentials_manager: The session-scoped credential store.  Must
                already hold validated credentials for any ``user_id`` passed
                to :meth:`poll_once`.
        """
        self._credentials_manager: BYOKCredentialsManager = credentials_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def poll_once(self, user_id: str, operation_name: str) -> ProgressUpdate:
        """Fetch the current state of a batch translation LRO.

        Retrieves the LRO via
        ``TranslationServiceClient.get_operation({'name': operation_name})``,
        deserialises the ``BatchTranslateDocumentMetadata`` payload, and
        returns a :class:`ProgressUpdate` snapshot.

        Transient ``ResourceExhausted`` (HTTP 429) and
        ``ServiceUnavailable`` (HTTP 503) errors are retried with
        exponential backoff up to :data:`_MAX_RETRIES` times.

        Args:
            user_id: The BYOK session identifier used to retrieve the
                authenticated :class:`~google.cloud.translate_v3.TranslationServiceClient`.
            operation_name: The fully-qualified LRO resource name returned
                by :func:`~services.gcp_batch_translation_service.GCPBatchTranslationService.submit_batch_job`.

        Returns:
            A :class:`ProgressUpdate` reflecting the latest LRO state.

        Raises:
            google.api_core.exceptions.GoogleAPICallError: Re-raised after
                all retries are exhausted for non-transient errors, or for
                transient errors that exceed :data:`_MAX_RETRIES`.
            RuntimeError: If credentials for ``user_id`` have not been
                registered with the credentials manager.
        """
        translation_client: translate.TranslationServiceClient = (
            self._credentials_manager.get_translation_client(user_id)
        )

        last_exc: Exception | None = None
        sleep_seconds: float = _BASE_BACKOFF_SECONDS

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                operation = translation_client.get_operation(
                    {"name": operation_name}
                )
                return self._parse_operation(operation_name, operation)

            except api_exceptions.ResourceExhausted as exc:
                last_exc = exc
                logger.warning(
                    "LROProgressMonitor: HTTP 429 on attempt %d/%d for %s; "
                    "backing off %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    operation_name,
                    sleep_seconds,
                )

            except api_exceptions.ServiceUnavailable as exc:
                last_exc = exc
                logger.warning(
                    "LROProgressMonitor: HTTP 503 on attempt %d/%d for %s; "
                    "backing off %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    operation_name,
                    sleep_seconds,
                )

            except api_exceptions.GoogleAPICallError:
                # Non-transient errors are re-raised immediately.
                raise

            if attempt < _MAX_RETRIES:
                time.sleep(sleep_seconds)
                sleep_seconds *= _BACKOFF_MULTIPLIER

        # All retries exhausted — re-raise the last transient exception.
        assert last_exc is not None  # guaranteed by loop logic above
        raise last_exc

    def estimate_remaining_time(
        self, progress: ProgressUpdate, elapsed_seconds: float
    ) -> float | None:
        """Estimate how many seconds remain until the job completes.

        Uses a linear extrapolation based on the observed translation rate::

            remaining = (total_pages - translated_pages) * (elapsed / translated_pages)

        Args:
            progress: The most recent :class:`ProgressUpdate` from
                :meth:`poll_once`.
            elapsed_seconds: Wall-clock time that has passed since the
                batch job was submitted, in seconds.

        Returns:
            Estimated remaining seconds as a :class:`float`, or ``None``
            when:

            * ``translated_pages == 0`` (no throughput data yet); or
            * the job is not in the ``RUNNING`` state (e.g. already done
              or still ``SUBMITTED``).
        """
        if progress.translated_pages == 0 or progress.state != "RUNNING":
            return None

        remaining_pages: int = progress.total_pages - progress.translated_pages
        rate: float = elapsed_seconds / progress.translated_pages  # seconds/page
        return remaining_pages * rate

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_operation(
        self,
        operation_name: str,
        operation: Any,
    ) -> ProgressUpdate:
        """Extract a :class:`ProgressUpdate` from a raw LRO ``Operation`` object.

        Handles both proto-plus wrapped objects and raw protobuf ``Any``
        metadata via a two-stage deserialisation strategy.

        Args:
            operation_name: The LRO resource name (used to populate the
                returned :class:`ProgressUpdate`).
            operation: The ``google.longrunning.operations_pb2.Operation``
                (or proto-plus equivalent) returned by ``get_operation``.

        Returns:
            A fully-populated :class:`ProgressUpdate`.
        """
        metadata_obj: Any = getattr(operation, "metadata", None)
        error_message: str | None = self._extract_error_message(operation)

        # ------------------------------------------------------------------
        # Stage 1: deserialise metadata into BatchTranslateDocumentMetadata.
        # Strategy A — use the proto-plus ``deserialize`` class method on the
        # raw protobuf bytes stored in ``metadata.value``.
        # Strategy B — fall back to direct attribute access when the runtime
        # already returns a proto-plus or dict-like object (e.g. in unit tests
        # backed by mock stubs).
        # ------------------------------------------------------------------
        parsed: Any = None

        if metadata_obj is not None:
            parsed = self._deserialise_metadata(metadata_obj)

        if parsed is None:
            # Cannot parse metadata; emit a safe zero-progress sentinel.
            logger.warning(
                "LROProgressMonitor: could not deserialise metadata for %s; "
                "returning zero-progress sentinel.",
                operation_name,
            )
            done_via_flag: bool = getattr(operation, "done", False)
            return ProgressUpdate(
                operation_name=operation_name,
                state="SUBMITTED",
                total_pages=0,
                translated_pages=0,
                failed_pages=0,
                completion_pct=0.0,
                is_done=done_via_flag,
                error_message=error_message,
            )

        # ------------------------------------------------------------------
        # Extract scalar progress fields.
        # ------------------------------------------------------------------
        total_pages: int = int(
            _get_attr_or_zero(parsed, "total_pages", "total_pages_count")
        )
        translated_pages: int = int(
            _get_attr_or_zero(parsed, "translated_pages", "translated_pages_count")
        )
        failed_pages: int = int(
            _get_attr_or_zero(parsed, "failed_pages", "failed_pages_count")
        )

        # ------------------------------------------------------------------
        # Extract state as a string name.
        # The ``state`` attribute may be:
        #   * a proto-plus enum member with a ``.name`` property, or
        #   * an integer enum value (raw protobuf), or
        #   * already a string (test stubs).
        # ------------------------------------------------------------------
        raw_state: Any = getattr(parsed, "state", None)
        state_str: str = _normalise_state(raw_state, parsed)

        # ------------------------------------------------------------------
        # Compute derived fields.
        # ------------------------------------------------------------------
        completion_pct: float = (
            (translated_pages / total_pages * 100.0) if total_pages > 0 else 0.0
        )
        is_done: bool = state_str in _DONE_STATES

        # Enrich error_message from metadata when the LRO error field is absent.
        if error_message is None and state_str == "FAILED":
            error_message = _get_str_attr(parsed, "error_detail", "error_message")

        logger.debug(
            "LROProgressMonitor: %s — state=%s translated=%d/%d failed=%d (%.1f%%)",
            operation_name,
            state_str,
            translated_pages,
            total_pages,
            failed_pages,
            completion_pct,
        )

        return ProgressUpdate(
            operation_name=operation_name,
            state=state_str,
            total_pages=total_pages,
            translated_pages=translated_pages,
            failed_pages=failed_pages,
            completion_pct=completion_pct,
            is_done=is_done,
            error_message=error_message,
        )

    @staticmethod
    def _deserialise_metadata(metadata_obj: Any) -> Any | None:
        """Attempt two-stage deserialisation of the LRO metadata payload.

        Stage A: call ``translate.types.BatchTranslateDocumentMetadata.deserialize``
        on the raw ``bytes`` stored in ``metadata_obj.value`` (standard
        protobuf ``Any`` container pattern).

        Stage B: treat ``metadata_obj`` itself as the typed object when it
        already exposes ``translated_pages_count`` or ``translated_pages``
        directly (proto-plus or mock).

        Args:
            metadata_obj: The raw ``metadata`` field from the LRO
                ``Operation`` object.

        Returns:
            A ``BatchTranslateDocumentMetadata`` instance (or equivalent
            duck-typed object), or ``None`` if deserialisation fails.
        """
        # Stage A — raw protobuf Any bytes path.
        raw_bytes: bytes | None = getattr(metadata_obj, "value", None)
        if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes:
            try:
                parsed = translate.types.BatchTranslateDocumentMetadata.deserialize(
                    raw_bytes
                )
                logger.debug(
                    "LROProgressMonitor: deserialised metadata via Stage A (bytes)."
                )
                return parsed
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "LROProgressMonitor: Stage A deserialisation failed (%s); "
                    "falling back to Stage B.",
                    exc,
                )

        # Stage B — check for direct attribute access (proto-plus / mock objects).
        for attr in (
            "translated_pages_count",
            "translated_pages",
            "total_pages_count",
            "total_pages",
        ):
            if hasattr(metadata_obj, attr):
                logger.debug(
                    "LROProgressMonitor: deserialised metadata via Stage B "
                    "(direct attr '%s').",
                    attr,
                )
                return metadata_obj

        return None

    @staticmethod
    def _extract_error_message(operation: Any) -> str | None:
        """Pull a human-readable error string from the LRO ``error`` field.

        The ``error`` field is a ``google.rpc.Status`` message with ``code``
        and ``message`` sub-fields.  It is only populated when the operation
        has failed at the transport / scheduling level.

        Args:
            operation: The raw LRO ``Operation`` object.

        Returns:
            A non-empty error string, or ``None``.
        """
        error_field: Any = getattr(operation, "error", None)
        if error_field is None:
            return None

        # Avoid false positives from zero-valued proto status codes.
        code: int = getattr(error_field, "code", 0)
        message: str = getattr(error_field, "message", "") or ""
        if code != 0 or message:
            return message or f"GCP error code {code}"
        return None


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _get_attr_or_zero(obj: Any, *attr_names: str) -> int:
    """Return the first non-``None`` integer attribute from ``obj``.

    Tries each name in ``attr_names`` in order and returns the value of the
    first attribute that exists and is not ``None``.  Falls back to ``0``.

    Args:
        obj: The object to inspect.
        *attr_names: Candidate attribute names in priority order.

    Returns:
        An integer value, defaulting to ``0`` if no attribute matches.
    """
    for name in attr_names:
        val: Any = getattr(obj, name, None)
        if val is None:
            continue
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str):
            try:
                return int(val.strip())
            except ValueError:
                continue
    return 0


def _get_str_attr(obj: Any, *attr_names: str) -> str | None:
    """Return the first non-empty string attribute from ``obj``.

    Args:
        obj: The object to inspect.
        *attr_names: Candidate attribute names in priority order.

    Returns:
        A non-empty :class:`str`, or ``None`` if no matching attribute is found.
    """
    for name in attr_names:
        val: Any = getattr(obj, name, None)
        if val is not None:
            s: str = str(val).strip()
            if s:
                return s
    return None


def _normalise_state(raw_state: Any, metadata_obj: Any) -> str:
    """Coerce a raw ``state`` value into a validated state name string.

    Handles three representations:

    1. Proto-plus enum member (has a ``.name`` attribute).
    2. Raw integer enum value — resolve via the ``State`` descriptor on
       :class:`~google.cloud.translate_v3.types.BatchTranslateDocumentMetadata`.
    3. Plain string (test stubs or future API changes).

    Falls back to ``"SUBMITTED"`` for unknown/zero-valued states.

    Args:
        raw_state: The ``state`` attribute value from the metadata object.
        metadata_obj: The metadata object itself (used to access the enum
            descriptor when ``raw_state`` is an integer).

    Returns:
        A validated state name from :data:`_ALL_STATES`, defaulting to
        ``"SUBMITTED"``.
    """
    if raw_state is None:
        return "SUBMITTED"

    # Proto-plus enum member path.
    name_attr: Any = getattr(raw_state, "name", None)
    if isinstance(name_attr, str) and name_attr in _ALL_STATES:
        return name_attr

    # Plain string path.
    if isinstance(raw_state, str):
        upper: str = raw_state.upper()
        return upper if upper in _ALL_STATES else "SUBMITTED"

    # Integer enum path — attempt resolution via the descriptor.
    try:
        int_val: int = int(raw_state)
        # Resolve via the BatchTranslateDocumentMetadata.State enum descriptor.
        state_enum = translate.types.BatchTranslateDocumentMetadata.State
        resolved = state_enum(int_val)
        resolved_name: str = getattr(resolved, "name", str(resolved))
        upper_resolved: str = resolved_name.upper()
        if upper_resolved in _ALL_STATES:
            return upper_resolved
    except Exception:  # noqa: BLE001
        pass

    logger.warning(
        "LROProgressMonitor: unknown state value %r; defaulting to 'SUBMITTED'.",
        raw_state,
    )
    return "SUBMITTED"
