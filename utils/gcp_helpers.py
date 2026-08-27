"""Google Cloud Platform and Storage Helper Utilities.

Centralizes common GCS URI parsing, blob management, glossary resource naming,
and resilient exponential backoff retry logic across the translation pipeline.

Traceability: FR-01, FR-02, US-01, US-02
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from google.api_core import exceptions as gcp_exceptions

logger: logging.Logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes considered transient across Google Cloud APIs
_RETRYABLE_HTTP_STATUS_CODES: frozenset[int] = frozenset({429, 503})
# gRPC status codes: RESOURCE_EXHAUSTED=8, UNAVAILABLE=14
_RETRYABLE_GRPC_CODES: frozenset[int] = frozenset({8, 14})


# ---------------------------------------------------------------------------
# GCS URI & Blob Operations
# ---------------------------------------------------------------------------


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Parse a Google Cloud Storage URI into bucket and blob components.

    Args:
        gcs_uri: Full URI string in the form ``gs://bucket-name/path/to/blob``.

    Returns:
        tuple[str, str]: ``(bucket_name, blob_name)``.

    Raises:
        ValueError: If *gcs_uri* is not a string, does not begin with ``gs://``,
            or does not contain both a bucket and a non-empty blob name.
    """
    if not isinstance(gcs_uri, str) or not gcs_uri.startswith("gs://"):
        raise ValueError(
            f"Invalid GCS URI '{gcs_uri}': must begin with 'gs://'"
        )

    path = gcs_uri[5:]  # Strip 'gs://'
    parts = path.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid GCS URI '{gcs_uri}': could not extract blob path"
        )

    return parts[0], parts[1]


def delete_gcs_blob(storage_client: Any, gcs_uri: str) -> bool:
    """Safely delete a GCS blob referenced by its ``gs://`` URI.

    Automatically catches and suppresses :class:`google.api_core.exceptions.NotFound`
    for idempotent cleanup, logging any other unexpected failures.

    Args:
        storage_client: Initialized Google Cloud Storage client instance.
        gcs_uri: Full URI string in the form ``gs://bucket/blob``.

    Returns:
        bool: ``True`` if the blob was deleted or was already not found,
            ``False`` if an unexpected error occurred.
    """
    try:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Deleted GCS blob: %s", gcs_uri)
        return True
    except gcp_exceptions.NotFound:
        logger.info("GCS blob already absent: %s", gcs_uri)
        return True
    except Exception:
        logger.exception("Error deleting GCS blob %s", gcs_uri)
        return False


def format_gcp_glossary_name(
    project_id: str, location: str, glossary_id: str
) -> str:
    """Format a fully qualified Google Cloud Translation v3 glossary resource name.

    Normalizes inputs where *project_id* might already contain a ``projects/``
    prefix.

    Args:
        project_id: GCP project identifier.
        location: Regional location string (e.g. ``"us-central1"``).
        glossary_id: Unique glossary identifier within the regional location.

    Returns:
        str: Fully qualified resource path:
            ``projects/{project_id}/locations/{location}/glossaries/{glossary_id}``.
    """
    clean_project = (
        project_id.removeprefix("projects/")
        if project_id.startswith("projects/")
        else project_id
    )
    return f"projects/{clean_project}/locations/{location}/glossaries/{glossary_id}"


# ---------------------------------------------------------------------------
# Transient Error Detection & Exponential Backoff Retry
# ---------------------------------------------------------------------------


def is_transient_gcp_error(exc: Exception) -> bool:
    """Determine whether an exception represents a transient Google Cloud error.

    Checks:
    - :class:`google.api_core.exceptions.GoogleAPICallError` gRPC/HTTP status codes.
    - Standard attributes such as ``code``, ``http_status``, and ``status_code``.
    - Known transient error substrings for fallback compatibility.

    Args:
        exc: Exception instance raised during API invocation.

    Returns:
        bool: ``True`` if the error is transient and retryable, ``False`` otherwise.
    """
    if isinstance(exc, gcp_exceptions.GoogleAPICallError):
        code = getattr(exc, "code", None)
        if code in _RETRYABLE_GRPC_CODES:
            return True

        http_status = getattr(exc, "http_status", None) or getattr(
            exc, "status_code", None
        )
        if http_status in _RETRYABLE_HTTP_STATUS_CODES:
            return True

    # Fallback string representation checks
    exc_str = str(exc)
    return any(
        code_str in exc_str
        for code_str in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
    )


def compute_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter_factor: float = 0.2,
) -> float:
    r"""Compute truncated exponential backoff delay with random jitter.

    Formula: :math:`\text{delay} = \min(\text{base} \times 2^{\text{attempt}-1}, \text{max}) \times (1 \pm \text{jitter})`.

    Args:
        attempt: Current retry attempt (1-indexed).
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum delay ceiling in seconds.
        jitter_factor: Multiplicative jitter range (e.g. 0.2 for :math:`\pm 20\%`).

    Returns:
        float: Delay duration in seconds.
    """
    raw_delay = min(base_delay * (2.0 ** max(0, attempt - 1)), max_delay)
    if jitter_factor > 0.0:
        jitter_mult = 1.0 + random.uniform(-jitter_factor, jitter_factor)
        return max(0.0, raw_delay * jitter_mult)
    return raw_delay


def retry_gcp_call(  # noqa: UP047
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> T:
    """Execute a callable with jittered exponential backoff on transient GCP errors.

    Args:
        fn: Callable to invoke.
        *args: Positional arguments forwarded to *fn*.
        max_retries: Maximum retry attempts after an initial failure.
        base_delay: Base exponential backoff delay in seconds.
        max_delay: Maximum ceiling backoff delay in seconds.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        T: Result returned by *fn* on success.

    Raises:
        Exception: The last exception raised after exhausting all retries, or
            any non-transient exception immediately on first occurrence.
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 2):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not is_transient_gcp_error(exc):
                raise
            last_exc = exc
            if attempt > max_retries:
                break

            delay = compute_backoff_delay(
                attempt, base_delay=base_delay, max_delay=max_delay
            )
            logger.warning(
                "Transient GCP error on attempt %d/%d — retrying in %.2fs: %s",
                attempt,
                max_retries,
                delay,
                type(exc).__name__,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


def retry_gcp_operation(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to apply exponential backoff retry to functions calling GCP APIs.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base exponential backoff delay in seconds.
        max_delay: Maximum ceiling backoff delay in seconds.

    Returns:
        Callable: Wrapped function with automated retry resilience.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return retry_gcp_call(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                **kwargs,
            )

        return wrapper

    return decorator
