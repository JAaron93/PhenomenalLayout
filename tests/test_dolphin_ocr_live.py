import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DOLPHIN_TESTS", "false").lower()
    not in {"1", "true", "yes", "on"},
    reason="Live Dolphin OCR API tests are disabled by default.",
)
async def test_live_process_pdf_smoke(tmp_path):
    """Smoke test for live Dolphin OCR via dolphin_client."""
    from services.dolphin_client import get_layout
    
    # Create a minimal PDF
    pdf_path = tmp_path / "test.pdf"
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\n"
        b"endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000060 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n196\n"
        b"%%EOF\n"
    )
    pdf_path.write_bytes(pdf_content)

    # This will likely fail in local CI without keys, but that's what skipif is for
    out = await get_layout(pdf_path)

    assert isinstance(out, dict)
    assert "pages" in out
