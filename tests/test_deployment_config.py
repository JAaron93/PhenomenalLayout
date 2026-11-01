"""Deployment validation tests for the GCP Document Translation stack.

These tests ensure minimal configuration is present and that optional
system dependencies are documented. They do not reach external networks.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "var",
    [
        "LINGO_API_KEY",
    ],
)
def test_required_env_vars_documented_and_optionally_set(var: str) -> None:
    # The variables may not be set in local runs; ensure they are documented
    # and the README exists so operators can configure them.
    readme = Path("README.md")
    assert readme.exists(), "README.md must exist for deployment guidance"
    text = readme.read_text(encoding="utf-8")
    assert var in text, f"{var} must be documented in README.md"
    # Optional: presence check, not enforced in CI unless env provided
    _ = os.getenv(var)


def test_minimum_dependency_pins_present() -> None:
    req_path = Path("requirements.txt")
    assert req_path.exists(), "requirements.txt must exist and list minimum pins"
    req = req_path.read_text(encoding="utf-8")
    import re

    def assert_version_pin(package: str) -> None:
        pattern = re.compile(
            rf"(?im)^\s*{re.escape(package)}\s*(?:>=|==)\s*[\d.]+"
        )
        assert pattern.search(
            req
        ), (
            f"{package} must be pinned with a minimum or exact version "
            f"(e.g., '{package}>=X.Y.Z' or '{package}==X.Y.Z')"
        )

    # Runtime critical dependencies must be pinned
    for pkg in ("google-cloud-translate", "google-cloud-storage", "fastapi", "pypdf"):
        assert_version_pin(pkg)

    # Legacy rasterization and UI dependencies must NOT be in runtime requirements.txt.
    # Match the package name as a whole word regardless of version operator so that
    # bare names, extras, and any PEP 440 specifier (>=, ==, ~=, !=, <, >) are caught.
    for retired_pkg in ("pdf2image", "Pillow", "pillow", "reportlab", "gradio"):
        pattern = re.compile(rf"(?im)^\s*{re.escape(retired_pkg)}\b")
        assert not pattern.search(
            req
        ), f"{retired_pkg} must not be present in runtime requirements.txt"

    # reportlab must also be absent from requirements-dev.txt (fully eradicated — PR #147)
    # Pillow was its transitive dependent; removing reportlab eliminates Pillow entirely.
    # The pattern matches any form: bare name, extras, or any PEP 440 version specifier.
    dev_req_path = Path("requirements-dev.txt")
    if dev_req_path.exists():
        dev_req = dev_req_path.read_text(encoding="utf-8")
        dev_pattern = re.compile(r"(?im)^\s*reportlab\b")
        assert not dev_pattern.search(dev_req), (
            "reportlab must not be present in requirements-dev.txt — "
            "use build_test_pdf() from tests/conftest.py for PDF test fixtures (PR #147)"
        )


def test_poppler_and_fonts_documented() -> None:
    readme = Path("README.md")
    assert readme.exists(), "README.md must exist for deployment guidance"
    text = readme.read_text(encoding="utf-8")
    assert "Poppler" in text, "Poppler installation notes must be documented"
    assert "fonts" in text.lower(), "Font installation guidance must be documented"


def test_reportlab_ban_catches_all_pep440_forms() -> None:
    """Verify the reportlab absence guard matches bare names, extras, and all
    PEP 440 version specifiers — not just >= and ==.

    Previously the pattern ``reportlab\\s*(?:>=|==)`` silently passed:
      - ``reportlab``             (bare, no specifier)
      - ``reportlab~=5.0``        (compatible-release)
      - ``reportlab[extra]>=5.0`` (with extras)
    """
    import re as _re

    pattern = _re.compile(r"(?im)^\s*reportlab\b")
    should_match = [
        "reportlab",
        "reportlab>=5.0.1,<6.0",
        "reportlab==5.0.1",
        "reportlab~=5.0",
        "reportlab[extra]>=5.0",
        "reportlab!=4.0",
        "  reportlab  >=5.0",
    ]
    should_not_match = [
        "# reportlab is banned",
        "some-reportlab-fork>=1.0",
        "pypdf>=4.0",
    ]
    for line in should_match:
        assert pattern.search(line), (
            f"Pattern must match prohibited entry: {line!r}"
        )
    for line in should_not_match:
        assert not pattern.search(line), (
            f"Pattern must NOT match non-reportlab entry: {line!r}"
        )
