"""Static SPA asset parse-integrity guarantees.

CodeQL's default-setup ``javascript-typescript`` configuration surfaces
extraction diagnostics for any ``static/*.js`` file that fails to parse
(e.g. ``Invalid left-hand side in assignment`` from an optional-chain
assignment). Orphaned modules are never fetched by a browser, so the
error is invisible at runtime — this gate pins it at test time.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def test_all_static_js_modules_parse() -> None:
    """Every static/*.js asset must pass Node's syntax check."""
    js_files = sorted(_STATIC_DIR.rglob("*.js"))
    assert js_files, "static/ must exist with ES-module assets"

    failures: list[str] = []
    for js_file in js_files:
        proc = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (
                proc.stderr.strip().splitlines()[0]
                if proc.stderr.strip()
                else "no parser output"
            )
            failures.append(f"{js_file.name}: {detail}")

    assert (
        not failures
    ), "Unparseable static JS assets (skipped by CodeQL extraction): " + "; ".join(failures)


def test_parse_gate_requires_node_or_skips_cleanly() -> None:
    """Document the skip contract when node is unavailable."""
    if shutil.which("node") is None:
        pytest.skip("node not installed; parse-integrity gate not enforceable on this host")
