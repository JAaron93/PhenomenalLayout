"""Migration validation: ensure no legacy PDF engine or fitz usage remains."""

from __future__ import annotations

from pathlib import Path


def _walk_text_files(root: str) -> list[Path]:
    allowed_ext = {".py", ".toml", ".md", ".txt"}
    root_path = Path(root)
    results: list[Path] = []
    for p in root_path.rglob("*"):
        if p.is_dir():
            continue
        parts = set(p.parts)
        # Skip common non-source directories
        if (
            ".git" in parts
            or "node_modules" in parts
            or ".venv" in parts
            or "site-packages" in parts
            or "egg-info" in parts
            or ".kiro" in parts
            or ".qoder" in parts
        ):
            continue
        if p.suffix.lower() in allowed_ext:
            results.append(p)
    return results


def test_no_pymupdf_imports() -> None:
    repo = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in _walk_text_files(str(repo)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "import fitz" in text or "PyMuPDF" in text:
            offenders.append(str(path))
    # Allow mentions in docs folder only
    offenders = [p for p in offenders if "/docs/" not in p]
    # Ignore this test file itself and egg-info metadata
    offenders = [
        p for p in offenders if not p.endswith("test_migration_no_pymupdf.py")
    ]
    offenders = [p for p in offenders if "egg-info" not in p]
    offenders = [p for p in offenders if not p.endswith("/README.md")]
    assert offenders == [], f"Unexpected PyMuPDF/fitz references: {offenders}"
