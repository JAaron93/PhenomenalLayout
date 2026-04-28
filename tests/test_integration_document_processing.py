from __future__ import annotations

import pytest
from core.dynamic_layout_engine import (
    OptimizedLayoutPreservationEngine as LayoutPreservationEngine,
)
from dolphin_ocr.monitoring import MonitoringService
from services.layout_aware_translation_service import (
    LayoutAwareTranslationService,
    McpLingoClient,
)
from services.main_document_processor import (
    DocumentProcessingRequest,
    DocumentProcessor,
    ProcessingOptions,
)
from services.pdf_document_reconstructor import PDFDocumentReconstructor


def _write_minimal_valid_pdf(path) -> None:
    """Write a minimal but structurally valid single-page PDF."""
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
    path.write_bytes(pdf_content)


class FakeLingo(McpLingoClient):
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        _ = source_lang, target_lang
        return text + "_tx"

    def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        _ = source_lang, target_lang
        return [t + "_tx" for t in texts]

    def translate_with_confidence(
        self, text: str, source_lang: str, target_lang: str
    ) -> tuple[str, float]:
        _ = source_lang, target_lang
        return (text + "_tx", 0.9)

    def translate_batch_with_confidence(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[tuple[str, float]]:
        _ = source_lang, target_lang
        return [(text + "_tx", 0.9) for text in texts]


def test_complete_document_processing_workflow(tmp_path, monkeypatch):
    # Create a minimal but structurally valid single-page PDF
    src_pdf = tmp_path / "sample.pdf"
    _write_minimal_valid_pdf(src_pdf)

    # Mock get_layout_sync
    def fake_get_layout_sync(_path):
        return {
            "pages": [
                {
                    "text_blocks": [
                        {
                            "text": "Hello",
                            "bbox": [10, 700, 300, 40],
                            "font_info": {
                                "family": "Helvetica",
                                "size": 12,
                                "weight": "normal",
                                "style": "normal",
                                "color": (0, 0, 0),
                            },
                            "confidence": 0.95,
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr("services.main_document_processor.get_layout_sync", fake_get_layout_sync)

    engine = LayoutPreservationEngine()
    lts = LayoutAwareTranslationService(
        lingo_client=FakeLingo(),
        layout_engine=engine,
    )
    recon = PDFDocumentReconstructor()
    monitor = MonitoringService(window_seconds=60)

    processor = DocumentProcessor(
        translation_service=lts,
        reconstructor=recon,
        monitoring=monitor,
    )

    req = DocumentProcessingRequest(
        file_path=str(src_pdf),
        source_language="en",
        target_language="de",
        options=ProcessingOptions(dpi=300, output_path=str(tmp_path / "out.pdf")),
    )

    result = processor.process_document(req)

    assert result.success is True
    assert result.output_path and result.output_path.endswith("out.pdf")
    assert result.processing_stats.pages_processed == 1
    # Progress stages should include the core phases
    assert result.progress[0] == "validated"
    assert result.progress[1] == "ocr"
    assert result.progress[-1] == "completed"
