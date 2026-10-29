"""Validated filesystem path construction for externally influenced values.

Remote inputs (upload metadata, request bodies, user identifiers) must never
reach filesystem operations unvalidated. All path assembly from such values
routes through this module:

- ``safe_component`` sanitizes an identifier into a single path component
  (preserving the legacy ``[^A-Za-z0-9_-] -> _`` mapping used by the
  vocabulary and glossary stores).
- ``resolve_within`` joins sanitized components beneath a controlled base
  directory and rejects any resolution that escapes it, including via symlink.
- ``resolve_managed_path`` / ``resolve_managed_path_or_none`` verify that an
  artifact path lives inside a server-managed storage area (system temp,
  ``$GRADIO_TEMP_DIR``, or the FileHandler directories).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Final

MANAGED_FILE_DIRS: Final[tuple[str, ...]] = ("uploads", "downloads", "temp")

_NON_IDENTIFIER_CHARS_RE: Final = re.compile(r"[^A-Za-z0-9_-]")
_FILENAME_COMPONENT_RE: Final = re.compile(r"[A-Za-z0-9._-]+")
_MAX_COMPONENT_LENGTH: Final = 128


def safe_component(name: str) -> str:
    """Sanitize *name* into a single identifier path component.

    Preserves the legacy ``[^A-Za-z0-9_-] -> _`` mapping used by the vocabulary
    and glossary stores so previously persisted files stay reachable.
    """
    cleaned = _NON_IDENTIFIER_CHARS_RE.sub("_", name.strip())[:_MAX_COMPONENT_LENGTH]
    if not cleaned:
        raise ValueError(f"Identifier cannot be used as a path component: {name!r}")
    return cleaned


def _managed_roots() -> list[str]:
    roots = [tempfile.gettempdir()]
    gradio_temp = os.environ.get("GRADIO_TEMP_DIR")
    if gradio_temp:
        roots.append(gradio_temp)
    roots.extend(MANAGED_FILE_DIRS)
    return roots


def resolve_within(base_dir: Path | str, *components: str) -> Path:
    """Join *components* beneath *base_dir*, rejecting traversal and symlink escapes.

    Components must be single filename segments (letters, digits, ``. _ -``
    only); they may never contain separators, so they cannot escape *base_dir*
    by construction. The realpath containment check additionally rejects
    symlinks pointing outside and components made solely of dots.

    Raises:
        ValueError: If no components are given, a component is not a safe
            filename segment, or the resolved path escapes *base_dir*.
    """
    if not components:
        raise ValueError("At least one path component is required")
    for component in components:
        if (
            not component
            or component in {".", ".."}
            or not _FILENAME_COMPONENT_RE.fullmatch(component)
        ):
            raise ValueError(f"Unsafe path component: {component!r}")
    base_real = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(base_real, *components))
    if not resolved.startswith(base_real + os.sep):
        raise ValueError(f"Resolved path escapes base directory {base_real!r}")
    return Path(resolved)


def resolve_managed_path(path: Path | str) -> Path:
    """Resolve *path* and require it to live inside a managed storage area.

    Raises:
        ValueError: If the resolved path is outside every managed root.
    """
    resolved = os.path.realpath(os.fspath(path))
    for root in _managed_roots():
        if resolved.startswith(os.path.realpath(root) + os.sep):
            return Path(resolved)
    raise ValueError(f"Path is outside managed storage areas: {path!r}")


def resolve_managed_path_or_none(path: Path | str) -> Path | None:
    """Like :func:`resolve_managed_path` but returns None instead of raising."""
    resolved = os.path.realpath(os.fspath(path))
    for root in _managed_roots():
        if resolved.startswith(os.path.realpath(root) + os.sep):
            return Path(resolved)
    return None
