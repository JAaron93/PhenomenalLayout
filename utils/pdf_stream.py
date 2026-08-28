"""Deterministic PDF Stream Normalization and Descriptor Management.

Universal input normalizer and file descriptor manager. Converts file paths,
raw byte payloads, or pre-opened binary streams into a readable binary stream
and accurate file size measurement in megabytes.

Enforces deterministic file descriptor cleanup (AGENTS.md §2.10), preventing
descriptor exhaustion in serverless runtimes.

Traceability: FR-04, US-04
"""

from __future__ import annotations

import contextlib
import io
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


@contextmanager
def open_pdf_stream(
    source: Path | str | bytes | BinaryIO,
    label: str = "PDF",
) -> Iterator[tuple[BinaryIO, float]]:
    """Context manager to normalize PDF sources into an open stream and size.

    Handles duck-typed PDF sources uniformly:
    - :class:`pathlib.Path` or :class:`str`: Opens file in ``'rb'`` mode.
      Calculates file size via :func:`os.path.getsize` without reading the file
      into memory buffers. Deterministically closes the stream upon context exit.
    - :class:`bytes`: Wraps payload in an :class:`io.BytesIO` instance.
      Deterministically closes the buffer upon context exit.
    - Seekable :class:`typing.BinaryIO`: Rewinds stream to position 0, measures
      size via :meth:`seek`, and leaves the caller-owned external stream open
      upon context exit.

    Args:
        source: PDF input represented as a Path, string file path, raw bytes,
            or an open binary stream.
        label: Descriptive label for error reporting (e.g. ``"PDF"``).

    Yields:
        tuple[BinaryIO, float]: ``(stream, file_size_mb)``.

    Raises:
        FileNotFoundError: If a given file path does not exist on disk.
        TypeError: If *source* is not a supported type.
    """
    stream: BinaryIO | None = None
    should_close: bool = False
    file_size_mb: float = 0.0

    try:
        if isinstance(source, (str, Path)):
            p = Path(source)
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"{label} file not found: {p}")
            file_size_mb = os.path.getsize(p) / (1024.0 * 1024.0)
            stream = p.open("rb")
            should_close = True

        elif isinstance(source, bytes):
            file_size_mb = len(source) / (1024.0 * 1024.0)
            stream = io.BytesIO(source)
            should_close = True

        elif hasattr(source, "read") and hasattr(source, "seek"):
            # Ensure seekable stream is rewound to beginning
            source.seek(0)
            cur_pos = source.tell()
            end_pos = source.seek(0, io.SEEK_END)
            source.seek(cur_pos)
            file_size_mb = max(0.0, end_pos) / (1024.0 * 1024.0)
            stream = source
            should_close = False

        else:
            raise TypeError(
                f"Unsupported {label} source type: {type(source).__name__}. "
                "Expected Path, str, bytes, or BinaryIO."
            )

        yield stream, file_size_mb

    finally:
        if should_close and stream is not None:
            with contextlib.suppress(Exception):
                stream.close()
