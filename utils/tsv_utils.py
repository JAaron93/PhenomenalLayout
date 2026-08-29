"""RFC 4180 TSV Escaping and Serialization Utilities.

Provides high-throughput, deterministic RFC 4180 TSV formatting and zero-copy
string escaping for dual-tier glossary synchronization with Google Cloud Translation.

Traceability: FR-03, US-03
"""

from __future__ import annotations

from collections.abc import Mapping

_DELIMITER_CHARS: frozenset[str] = frozenset({"\t", "\n", "\r", '"'})


def escape_rfc4180_field(val: str) -> str:
    """Escape a field value according to RFC 4180 for TSV formatting.

    Employs an early-exit fast path: if the input string contains none of the
    special characters (tab, newline, carriage return, double quote), it is
    returned directly without creating intermediate string allocations.

    If special characters are detected, internal double quotes are doubled
    (``"`` -> ``""``) and the entire field is wrapped in enclosing double quotes.

    Args:
        val: Raw string field value to escape.

    Returns:
        str: RFC 4180 sanitized field string.
    """
    # Fast path: 95%+ of dictionary terms contain only standard characters
    if not any(c in _DELIMITER_CHARS for c in val):
        return val

    escaped = val.replace('"', '""')
    return f'"{escaped}"'


def format_tsv_bytes(
    entries: Mapping[str, str],
    header: tuple[str, str] = ("de", "en"),
) -> bytes:
    """Serialize a mapping of glossary entries into RFC 4180 compliant TSV bytes.

    Entries are sorted deterministically by source term to ensure reproducible
    cryptographic hashing and idempotent glossary synchronization.

    Args:
        entries: Dictionary or mapping of ``{source_term: target_term}``.
        header: Column headers tuple, defaults to ``("de", "en")``.

    Returns:
        bytes: UTF-8 encoded TSV byte payload with trailing newline.
    """
    lines: list[str] = [f"{header[0]}\t{header[1]}"]

    for source_term in sorted(entries.keys()):
        target_term = entries[source_term]
        esc_source = escape_rfc4180_field(source_term)
        esc_target = escape_rfc4180_field(target_term)
        lines.append(f"{esc_source}\t{esc_target}")

    lines.append("")  # Ensures trailing newline
    return "\n".join(lines).encode("utf-8")
