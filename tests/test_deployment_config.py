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

    # Legacy rasterization and UI dependencies must NOT be in runtime requirements.txt
    for retired_pkg in ("pdf2image", "Pillow", "pillow", "reportlab", "gradio"):
        pattern = re.compile(rf"(?im)^\s*{re.escape(retired_pkg)}\s*(?:>=|==)")
        assert not pattern.search(
            req
        ), f"{retired_pkg} must not be present in runtime requirements.txt"


def test_poppler_and_fonts_documented() -> None:
    readme = Path("README.md")
    assert readme.exists(), "README.md must exist for deployment guidance"
    text = readme.read_text(encoding="utf-8")
    assert "Poppler" in text, "Poppler installation notes must be documented"
    assert "fonts" in text.lower(), "Font installation guidance must be documented"
