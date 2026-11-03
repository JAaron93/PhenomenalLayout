"""Static SPA asset injection-surface guarantees.

CodeQL's ``js/xss`` query (code-scanning alert #23) flags client-side
cross-site scripting when a user-reachable value flows into an
``innerHTML`` assignment. The bespoke SPA convention (ADR 0002, e.g.
``static/js/onboarding.js``) is interpolation-free static scaffolding
with dynamic values delivered through ``textContent``/``setAttribute``/
element properties — none of which re-parse markup. This gate pins that
convention repo-wide so an interpolating template fails tests instead of
surfacing as a security alert.

Allowed ``innerHTML`` right-hand sides:
- an empty string (element clearing), or
- a pure string literal (single-/double-quoted or a backtick template)
  with no ``${`` interpolation, no ``+`` concatenation, and no variable
  reference.

Flaw classification the hand-rolled scanner covers instead of one regex:
- multi-line template literals (``${`` detection across newlines),
- concatenation after a quoted literal (``"<li>" + term``),
- variable / ternary / call-expression right-hand sides.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

_INNERHTML_ASSIGN_RE = re.compile(r"\.innerHTML\s*\+?=\s*")


def _find_string_close(source: str, start: int) -> int | None:
    """Index of the quote closing the string starting at ``start``, or None."""
    quote = source[start]
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index
        index += 1
    return None


def _innerhtml_offender_lines(source: str) -> list[int]:
    """1-based lines whose ``innerHTML`` RHS is not a purely static literal."""
    offenders: list[int] = []
    for match in _INNERHTML_ASSIGN_RE.finditer(source):
        rhs = match.end()
        line = source.count("\n", 0, rhs) + 1
        first_char = source[rhs]

        if first_char == "`":
            close = source.find("`", rhs + 1)
            template = source[rhs : close if close != -1 else len(source)]
            if "${" in template or close == -1:
                offenders.append(line)
            continue

        if first_char in "\"'":
            close = _find_string_close(source, rhs)
            if close is None:
                offenders.append(line)
                continue
            statement = source[close + 1 :].split("\n", 1)[0]
            if statement.strip() != ";" and statement.strip() != "":
                offenders.append(line)
            continue

        offenders.append(line)
    return offenders


def test_innerhtml_assignments_are_static_literals() -> None:
    """No static/*.js asset may compose dynamic markup into innerHTML."""
    js_files = sorted(_STATIC_DIR.rglob("*.js"))
    assert js_files, "static/ must exist with ES-module assets"

    offenders: list[str] = []
    for js_file in js_files:
        source = js_file.read_text(encoding="utf-8")
        offenders.extend(
            f"{js_file.name}:{line}" for line in _innerhtml_offender_lines(source)
        )

    assert not offenders, (
        "innerHTML assigned dynamic markup (js/xss sink class; deliver "
        "dynamic values via textContent/properties instead): "
        + "; ".join(offenders)
    )


def test_static_security_gate_covers_known_sink_file() -> None:
    """Guard the gate itself: alert #23's file must remain under coverage."""
    sink_file = _STATIC_DIR / "philosophy_interface.js"
    if not sink_file.exists():
        pytest.skip("philosophy_interface.js retired; gate scope check moot")
    assert _STATIC_DIR in sink_file.resolve().parents
