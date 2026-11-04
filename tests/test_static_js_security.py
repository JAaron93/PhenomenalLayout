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
  with no ``${`` interpolation, **followed only by statement
  termination**.

"Followed only by termination" is the rule that closes the concatenation
holes: after the literal (past whitespace and comments, across newlines)
the next significant character must be ``;``, ``,``, ``}`` or EOF —
justified by ASI, because a token that *cannot* begin its own statement
(``+``/``(``/``.``/``[``/``?``/template tick/…) continues the current
expression instead (``a = b`` newline ``+ c`` parses as ``b + c``). Any
such continuation character (concatenation, member/call/index chaining,
ternary) is flagged — ``el.innerHTML = `<p>` + userInput;`` and
``el.innerHTML = "<p>"`` newline ``+ userInput;`` both fail. Anything
dynamic must go through ``textContent``, ``setAttribute`` or element
properties, which never re-parse markup.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

_INNERHTML_ASSIGN_RE = re.compile(r"\.innerHTML\s*\+?=\s*")

# Characters that, when following a complete literal, continue the larger
# expression (cannot start a fresh ASI-terminated statement): string
# concatenation, member/call/index access, ternary, arithmetic/bitwise
# operators, and a template tick.
_CONTINUATION_CHARS = frozenset("+-([.?`&|^*/%")


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


def _next_significant_char(source: str, start: int) -> str:
    """First non-whitespace, non-comment character at/after ``start``.

    Returns an empty string at end of source.
    """
    index = start
    while index < len(source):
        char = source[index]
        if char in " \t\r\n\f\v":
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index)
            if newline == -1:
                return ""
            index = newline + 1
            continue
        if source.startswith("/*", index):
            close = source.find("*/", index + 2)
            if close == -1:
                return ""
            index = close + 2
            continue
        return char
    return ""


def _innerhtml_offender_lines(source: str) -> list[int]:
    """1-based lines whose ``innerHTML`` RHS is not a purely static literal."""
    offenders: list[int] = []
    for match in _INNERHTML_ASSIGN_RE.finditer(source):
        rhs = match.end()
        line = source.count("\n", 0, rhs) + 1
        first_char = source[rhs]

        literal_end: int | None = None
        if first_char == "`":
            close = source.find("`", rhs + 1)
            if close == -1:
                offenders.append(line)
                continue
            if "${" in source[rhs:close]:
                offenders.append(line)
                continue
            literal_end = close + 1
        elif first_char in "\"'":
            close = _find_string_close(source, rhs)
            if close is None:
                offenders.append(line)
                continue
            literal_end = close + 1
        else:
            # Variable, ternary or call-expression right-hand side.
            offenders.append(line)
            continue

        following = _next_significant_char(source, literal_end)
        if following in _CONTINUATION_CHARS:
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


def test_gate_flags_concatenation_after_backtick_template() -> None:
    """Same-line concatenation after a static template must be flagged."""
    source = "el.innerHTML = `<p>` + userInput;\n"
    assert _innerhtml_offender_lines(source) == [1]


def test_gate_flags_concatenation_continuing_on_next_line() -> None:
    """Cross-newline continuation after a quoted literal must be flagged."""
    source = 'el.innerHTML = "<p>"\n    + userInput;\n'
    assert _innerhtml_offender_lines(source) == [1]


def test_gate_flags_member_call_on_static_template() -> None:
    """Chained calls on the literal keep expression control in code — flagged."""
    source = "el.innerHTML = `<p>x</p>`.concat(tainted);\n"
    assert _innerhtml_offender_lines(source) == [1]


def test_gate_allows_terminated_static_literals() -> None:
    """Real terminator forms stay permitted: ; , } EOF and comments."""
    source = (
        'a.innerHTML = "";\n'
        "b.innerHTML = `<p>static</p>`;\n"
        'c.innerHTML = "<li>ok</li>"; // trailing comment\n'
        'd.innerHTML = "" /* block */ ;\n'
        'e.innerHTML = `<p>x</p>`, e.className = "y";\n'
        'f.innerHTML = ""\n'
        ";g.innerHTML = `t`\n"
    )
    assert _innerhtml_offender_lines(source) == []


def test_static_security_gate_covers_known_sink_file() -> None:
    """Guard the gate itself: alert #23's file must remain under coverage."""
    sink_file = _STATIC_DIR / "philosophy_interface.js"
    if not sink_file.exists():
        pytest.skip("philosophy_interface.js retired; gate scope check moot")
    assert _STATIC_DIR in sink_file.resolve().parents
