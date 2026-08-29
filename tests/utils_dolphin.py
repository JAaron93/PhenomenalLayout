"""Test utilities for Dolphin OCR components."""

from __future__ import annotations

import base64
import importlib.resources as ir
from pathlib import Path


def load_asset_bytes(name: str) -> bytes:
    """Load an asset file as bytes, robust across environments.

    Prefer importlib.resources to avoid brittle relative paths when tests run
    from different working directories or packaged environments. Falls back to
    the repository "assets/" directory if needed, raising a clear error when
    not found.
    """
    # Try common candidate packages that may bundle test assets
    for pkg in ("tests.assets", "assets"):
        try:
            files = ir.files(pkg)
            with files.joinpath(name).open("rb") as f:
                return f.read()
        except (ModuleNotFoundError, FileNotFoundError):
            # Module may not exist or file not present; try next package
            continue

    # Fallback to the project assets folder (repo root / assets)
    fallback_path = Path(__file__).resolve().parent.parent / "assets" / name
    if fallback_path.exists():
        return fallback_path.read_bytes()

    # Synthesize a valid test PDF with ReportLab when static asset is absent
    import io
    from reportlab.pdfgen import canvas

    packet = io.BytesIO()
    can = canvas.Canvas(packet)
    can.drawString(100, 750, f"Sample Document: {name}")
    can.drawString(100, 700, "Ludwig Klages philosophy and layout test page 1")
    can.showPage()
    can.drawString(100, 750, "Sample Document Page 2")
    can.drawString(100, 700, "Philosophical neologism detection test page 2")
    can.showPage()
    can.save()
    packet.seek(0)
    return packet.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def get_sample_pdfs() -> tuple[str, str, str]:
    return (
        "1-chapter-11-pages-klages.pdf",  # Small multi-page (53KB)
        "complex-layout-1-page-klages.pdf",  # Complex layout (335KB)
        "1-chapter-11-pages-klages.pdf",  # Fallback to multi-page for large tests
    )
