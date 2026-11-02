"""Static SPA asset parse-integrity guarantees.

CodeQL's default-setup ``javascript-typescript`` configuration surfaces
extraction diagnostics for any ``static/*.js`` file that fails to parse
(e.g. ``Invalid left-hand side in assignment`` from an optional-chain
assignment). Orphaned modules are never fetched by a browser, so the
error is invisible at runtime — this gate pins it at test time.

Every asset is an ES module, so the gate checks them through
``node --input-type=module --check`` (stdin) instead of file mode —
file mode depends on the host Node's module auto-detection defaults
(``--check`` assumed CommonJS before ``detect-module``), while the
stdin form is deterministic on any Node that ships the flags.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def test_all_static_js_modules_parse() -> None:
    """Every static/*.js asset must parse as an ES module via Node's syntax check."""
    if shutil.which("node") is None:
        pytest.skip("node not installed; parse-integrity gate not enforceable on this host")

    js_files = sorted(_STATIC_DIR.rglob("*.js"))
    assert js_files, "static/ must exist with ES-module assets"

    failures: list[str] = []
    for js_file in js_files:
        proc = subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=js_file.read_text(encoding="utf-8"),
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
