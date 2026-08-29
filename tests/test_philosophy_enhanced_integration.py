"""Comprehensive integration tests for philosophy-enhanced translation system."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.neologism_models import (
    DetectedNeologism,
    NeologismAnalysis,
    NeologismType,
)
from models.user_choice_models import ChoiceType, UserChoice
from services.philosophy_enhanced_document_processor import (
    PhilosophyDocumentResult,
    PhilosophyEnhancedDocumentProcessor,
    PhilosophyProcessingProgress,
    create_philosophy_enhanced_document_processor,
    process_document_with_philosophy_awareness,
)
from services.philosophy_enhanced_translation_service import (
    NeologismPreservationResult,
    PhilosophyEnhancedTranslationService,
    PhilosophyTranslationProgress,
)


class TestPhilosophyEnhancedTranslationServiceIntegration:
    """Test integration of PhilosophyEnhancedTranslationService with existing services."""

    @pytest.fixture
    def mock_translation_service(self):
        """Create mock translation service."""
        service = MagicMock()
        service.translate_text.return_value = "translated text"
        service.translate_batch.return_value = [
            "translated text 1",
            "translated text 2",
        ]
        service.get_statistics.return_value = {"translations": 10}
        return service

    @pytest.fixture
    def mock_neologism_detector(self):
        """Create mock neologism detector."""
        detector = MagicMock()
        neologism = DetectedNeologism(
            term="Dasein",
            confidence=0.9,
            neologism_type=NeologismType.PHILOSOPHICAL_TERM,
            start_pos=0,
            end_pos=6,
            sentence_context="Dasein is a fundamental concept",
            paragraph_context="",
        )
        analysis = NeologismAnalysis(
            text_id="test_text",
            analysis_timestamp="2025-01-01T00:00:00",
            total_tokens=10,
            analyzed_chunks=1,
            detected_neologisms=[neologism],
            total_detections=1,
        )
        detector.analyze_text.return_value = analysis
        detector.get_statistics.return_value = {"analyses": 5}
        return detector

    @pytest.fixture
    def mock_user_choice_manager(self):
        """Create mock user choice manager."""
        manager = MagicMock()
        choice = UserChoice(
            choice_id="test_choice_id",
            neologism_term="Dasein",
            choice_type=ChoiceType.PRESERVE,
            session_id="test_session",
        )
        manager.get_choice_for_neologism.return_value = choice
        manager.get_statistics.return_value = {"choices": 3}
        return manager

    @pytest.fixture
    def philosophy_service(
        self,
        mock_translation_service,
        mock_neologism_detector,
        mock_user_choice_manager,
    ):
        """Create philosophy-enhanced translation service with mocked dependencies."""
        return PhilosophyEnhancedTranslationService(
            translation_service=mock_translation_service,
            neologism_detector=mock_neologism_detector,
            user_choice_manager=mock_user_choice_manager,
        )

    def test_service_initialization(self, philosophy_service):
        """Test service initializes correctly with all components."""
        assert philosophy_service.translation_service is not None
        assert philosophy_service.neologism_detector is not None
        assert philosophy_service.user_choice_manager is not None
        assert philosophy_service.preserve_marker_prefix == "NEOLOGISM_PRESERVE_"
        assert philosophy_service.preserve_marker_suffix == "_PRESERVE_END"

        # Verify only Lingo provider is available
        available_providers = philosophy_service.get_available_providers()
        assert "lingo" in available_providers
        assert len(available_providers) == 1

    def test_translate_text_with_neologism_handling(
        self, philosophy_service, mock_translation_service
    ):
        """Test text translation with neologism handling."""
        text = "Dasein is a fundamental concept in existentialism"
        result = philosophy_service.translate_text_with_neologism_handling(
            text, "en", "de", "auto", "test_session"
        )

        assert isinstance(result, NeologismPreservationResult)
        assert result.original_text == text
        assert result.translated_text == "translated text"
        assert result.neologism_analysis is not None
        assert len(result.neologisms_preserved) >= 0

        # Verify translation service was called
        mock_translation_service.translate_text.assert_called_once()

    def test_translate_batch_with_neologism_handling(
        self, philosophy_service, mock_translation_service
    ):
        """Test batch translation with neologism handling."""
        texts = ["Dasein is fundamental", "Heidegger's concept"]
        results = philosophy_service.translate_batch_with_neologism_handling(
            texts, "en", "de", "auto", "test_session"
        )

        assert len(results) == 2
        for result in results:
            assert isinstance(result, NeologismPreservationResult)
            assert result.translated_text in ["translated text 1", "translated text 2"]

        # Verify batch translation was called
        mock_translation_service.translate_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_document_with_neologism_handling(self, philosophy_service):
        """Test document translation with neologism handling using Lingo."""
        document = {
            "type": "pdf_advanced",
            "text_by_page": {
                "1": "Dasein is a fundamental concept",
                "2": "Heidegger's philosophy",
            },
            "pages": [
                {"text_blocks": [{"text": "Dasein is a fundamental concept"}]},
                {"text_blocks": [{"text": "Heidegger's philosophy"}]},
            ],
        }

        result = await philosophy_service.translate_document_with_neologism_handling(
            document,
            "en",
            "de",
            "lingo",
            "test_session",  # Use Lingo provider
        )

        assert "translated_content" in result
        assert "neologism_analysis" in result
        assert "processing_metadata" in result
        assert result["session_id"] == "test_session"

    def test_preserve_neologisms_in_text(self, philosophy_service):
        """Test neologism preservation in text."""
        text = "Dasein is a fundamental concept"
        neologisms = [
            DetectedNeologism(
                term="Dasein",
                start_pos=0,
                end_pos=6,
                sentence_context="Dasein is a fundamental concept",
                confidence=0.9,
                neologism_type=NeologismType.PHILOSOPHICAL_TERM,
            )
        ]

        preserved_text, markers = philosophy_service._preserve_neologisms_in_text(
            text, neologisms
        )

        assert "NEOLOGISM_PRESERVE_" in preserved_text
        assert "Dasein" not in preserved_text  # Should be replaced with marker
        assert len(markers) == 1

    def test_restore_neologisms_in_text(self, philosophy_service):
        """Test neologism restoration in text."""
        text = "NEOLOGISM_PRESERVE_0_PRESERVE_END is a fundamental concept"
        markers = {"NEOLOGISM_PRESERVE_0_PRESERVE_END": "Dasein"}

        restored_text = philosophy_service._restore_neologisms_in_text(text, markers)

        assert restored_text == "Dasein is a fundamental concept"
        assert "NEOLOGISM_PRESERVE_" not in restored_text

    def test_get_statistics(self, philosophy_service):
        """Test statistics collection."""
        stats = philosophy_service.get_statistics()

        assert "translation_service_stats" in stats
        assert "neologism_detector_stats" in stats
        assert "user_choice_manager_stats" in stats
        assert "philosophy_enhanced_stats" in stats


class TestPhilosophyEnhancedDocumentProcessorIntegration:
    """Test integration of PhilosophyEnhancedDocumentProcessor with existing services."""

    @pytest.fixture
    def mock_base_processor(self):
        """Create mock base document processor."""
        processor = MagicMock()
        processor.extract_content.return_value = {
            "type": "pdf_advanced",
            "text_by_page": {"1": "Dasein is a fundamental concept"},
            "pages": [{"text_blocks": [{"text": "Dasein is a fundamental concept"}]}],
        }
        processor.create_translated_document.return_value = (
            "/tmp/translated_document.pdf"
        )
        return processor

    @pytest.fixture
    def mock_philosophy_translation_service(self):
        """Create mock philosophy translation service."""
        service = MagicMock()
        service.translate_document_with_neologism_handling = AsyncMock(
            return_value={
                "translated_content": {
                    "type": "pdf_advanced",
                    "pages": [{"text_blocks": [{"text": "translated content"}]}],
                },
                "neologism_analysis": NeologismAnalysis(
                    text_id="test",
                    analysis_timestamp="2025-01-01T00:00:00",
                    total_tokens=10,
                    analyzed_chunks=1,
                    detected_neologisms=[],
                    total_detections=0,
                ),
            }
        )
        service.get_statistics.return_value = {"translations": 5}
        return service

    @pytest.fixture
    def mock_neologism_detector(self):
        """Create mock neologism detector."""
        detector = MagicMock()
        detector.analyze_text.return_value = NeologismAnalysis(
            text_id="test",
            analysis_timestamp="2025-01-01T00:00:00",
            total_tokens=10,
            analyzed_chunks=1,
            detected_neologisms=[],
            total_detections=0,
        )
        detector.get_statistics.return_value = {"analyses": 3}
        return detector

    @pytest.fixture
    def mock_user_choice_manager(self):
        """Create mock user choice manager."""
        manager = MagicMock()
        manager.create_session.return_value = MagicMock(session_id="test_session")
        manager.get_choice_for_neologism.return_value = None
        manager.get_statistics.return_value = {"choices": 2}
        return manager

    @pytest.fixture
    def philosophy_processor(
        self,
        mock_base_processor,
        mock_philosophy_translation_service,
        mock_neologism_detector,
        mock_user_choice_manager,
    ):
        """Create philosophy-enhanced document processor with mocked dependencies."""
        return PhilosophyEnhancedDocumentProcessor(
            base_processor=mock_base_processor,
            philosophy_translation_service=mock_philosophy_translation_service,
            neologism_detector=mock_neologism_detector,
            user_choice_manager=mock_user_choice_manager,
        )

    def test_processor_initialization(self, philosophy_processor):
        """Test processor initializes correctly with all components."""
        assert philosophy_processor.base_processor is not None
        assert philosophy_processor.philosophy_translation_service is not None
        assert philosophy_processor.neologism_detector is not None
        assert philosophy_processor.user_choice_manager is not None
        assert philosophy_processor.enable_batch_processing is True
        assert philosophy_processor.max_concurrent_pages == 5

    @pytest.mark.asyncio
    async def test_extract_content(self, philosophy_processor):
        """Test content extraction with philosophy enhancements."""
        content = await philosophy_processor.extract_content("/tmp/test.pdf")

        assert content["philosophy_enhanced"] is True
        assert content["neologism_detection_ready"] is True
        assert content["type"] == "pdf_advanced"

    @pytest.mark.asyncio
    async def test_process_document_with_philosophy_awareness(
        self, philosophy_processor
    ):
        """Test full document processing with philosophy awareness."""
        result = await philosophy_processor.process_document_with_philosophy_awareness(
            "/tmp/test.pdf", "en", "de", "auto", "test_user"
        )

        assert isinstance(result, PhilosophyDocumentResult)
        assert result.translated_content is not None
        assert result.original_content is not None
        assert result.document_neologism_analysis is not None
        assert result.session_id is not None
        assert result.processing_time > 0

    @pytest.mark.asyncio
    async def test_create_translated_document_with_philosophy_awareness(
        self, philosophy_processor
    ):
        """Test creating translated document with philosophy awareness."""
        # Create a mock result
        result = PhilosophyDocumentResult(
            translated_content={
                "pages": [{"text_blocks": [{"text": "translated content"}]}]
            },
            original_content={
                "pages": [{"text_blocks": [{"text": "original content"}]}]
            },
            document_neologism_analysis=NeologismAnalysis(
                text_id="test",
                analysis_timestamp="2025-01-01T00:00:00",
                total_tokens=10,
                analyzed_chunks=1,
                detected_neologisms=[],
                total_detections=0,
            ),
            page_neologism_analyses=[],
            session_id="test_session",
            total_choices_applied=0,
            processing_metadata={},
            processing_time=1.0,
            neologism_detection_time=0.5,
            translation_time=0.3,
        )

        output_path = await philosophy_processor.create_translated_document_with_philosophy_awareness(
            result, "test_output.pdf"
        )

        assert output_path == "/tmp/translated_document.pdf"

    def test_get_statistics(self, philosophy_processor):
        """Test statistics collection."""
        stats = philosophy_processor.get_statistics()

        assert "philosophy_enhanced_processor_stats" in stats
        assert "translation_service_stats" in stats
        assert "neologism_detector_stats" in stats
        assert "user_choice_manager_stats" in stats
        assert "configuration" in stats

    def test_extract_all_text_from_content(self, philosophy_processor):
        """Test text extraction from various content types."""
        # Test PDF advanced content
        pdf_content = {
            "type": "pdf_advanced",
            "text_by_page": {"1": "Page 1 text", "2": "Page 2 text"},
        }
        text = philosophy_processor._extract_all_text_from_content(pdf_content)
        assert "Page 1 text" in text
        assert "Page 2 text" in text

        # Test DOCX content
        docx_content = {"type": "docx", "text_content": "Document text content"}
        text = philosophy_processor._extract_all_text_from_content(docx_content)
        assert text == "Document text content"

        # Test TXT content
        txt_content = {"type": "txt", "text_content": "Plain text content"}
        text = philosophy_processor._extract_all_text_from_content(txt_content)
        assert text == "Plain text content"


class TestEndToEndPhilosophyWorkflow:
    """Test end-to-end philosophy-enhanced translation workflow."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(
                "Dasein is a fundamental concept in Heideggerian philosophy. "
                "The notion of Sein-zum-Tode is crucial for understanding authenticity."
            )
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_convenience_function_workflow(self, temp_file):
        """Test the convenience function for document processing."""
        with patch(
            "services.philosophy_enhanced_document_processor.create_philosophy_enhanced_document_processor"
        ) as mock_create:
            mock_processor = MagicMock()
            mock_processor.process_document_with_philosophy_awareness = AsyncMock(
                return_value=MagicMock(
                    translated_content={"pages": []},
                    original_content={"pages": []},
                    document_neologism_analysis=NeologismAnalysis(
                        text_id="test",
                        analysis_timestamp="2025-01-01T00:00:00",
                        total_tokens=10,
                        analyzed_chunks=1,
                        detected_neologisms=[],
                        total_detections=0,
                    ),
                    page_neologism_analyses=[],
                    session_id="test_session",
                    total_choices_applied=0,
                    processing_metadata={},
                    processing_time=1.0,
                    neologism_detection_time=0.5,
                    translation_time=0.3,
                )
            )
            mock_processor.create_translated_document_with_philosophy_awareness = (
                AsyncMock(return_value="/tmp/translated_output.pdf")
            )
            mock_create.return_value = mock_processor

            result, output_path = await process_document_with_philosophy_awareness(
                temp_file, "en", "de", "auto", "test_user"
            )

            assert result is not None
            assert output_path == "/tmp/translated_output.pdf"

    def test_create_philosophy_enhanced_document_processor_factory(self):
        """Test the factory function for creating processors."""
        with patch(
            "services.philosophy_enhanced_document_processor.PhilosophyEnhancedDocumentProcessor"
        ) as mock_processor_class:
            mock_processor_class.return_value = MagicMock()

            processor = create_philosophy_enhanced_document_processor(
                dpi=200,
                preserve_images=False,
                terminology_path="/tmp/terminology.json",
                db_path="/tmp/test.db",
            )

            mock_processor_class.assert_called_once()
            assert processor is not None


class TestProgressTracking:
    """Test progress tracking functionality."""

    def test_philosophy_translation_progress(self):
        """Test philosophy translation progress tracking."""
        progress = PhilosophyTranslationProgress()

        # Test initial state
        assert progress.text_processing_progress == 0
        assert progress.neologism_detection_progress == 0
        assert progress.user_choice_application_progress == 0
        assert progress.translation_progress == 0
        assert progress.overall_progress == 0.0

        # Test progress updates
        progress.text_processing_progress = 100
        progress.neologism_detection_progress = 50
        progress.user_choice_application_progress = 75
        progress.translation_progress = 25

        assert progress.overall_progress > 0
        assert progress.overall_progress < 100

    def test_philosophy_processing_progress(self):
        """Test philosophy processing progress tracking."""
        progress = PhilosophyProcessingProgress()

        # Test initial state
        assert progress.extraction_progress == 0
        assert progress.neologism_detection_progress == 0
        assert progress.user_choice_progress == 0
        assert progress.translation_progress == 0
        assert progress.reconstruction_progress == 0
        assert progress.overall_progress == 0.0

        # Test progress updates
        progress.extraction_progress = 100
        progress.neologism_detection_progress = 80
        progress.user_choice_progress = 60
        progress.translation_progress = 40
        progress.reconstruction_progress = 20

        assert progress.overall_progress > 0
        assert progress.overall_progress < 100

        # Test time tracking
        progress.start_time = 1000.0
        with patch("time.time", return_value=1010.0):
            assert progress.elapsed_time == 10.0


class TestErrorHandling:
    """Test error handling in philosophy-enhanced system."""

    def test_translation_service_error_handling(self):
        """Test error handling in translation service."""
        mock_translation_service = MagicMock()
        mock_translation_service.translate_text.side_effect = Exception(
            "Translation failed"
        )

        service = PhilosophyEnhancedTranslationService(
            translation_service=mock_translation_service
        )

        with pytest.raises(Exception, match="Translation failed"):
            service.translate_text_with_neologism_handling(
                "test text", "en", "de", "auto", "test_session"
            )

    @pytest.mark.asyncio
    async def test_document_processor_error_handling(self):
        """Test error handling in document processor."""
        mock_processor = MagicMock()
        mock_processor.extract_content.side_effect = Exception("Extraction failed")

        processor = PhilosophyEnhancedDocumentProcessor(base_processor=mock_processor)

        with pytest.raises(Exception, match="Extraction failed"):
            await processor.process_document_with_philosophy_awareness(
                "/tmp/nonexistent.pdf", "en", "de", "auto", "test_user"
            )

    def test_graceful_degradation_on_neologism_detection_failure(self):
        """Test graceful degradation when neologism detection fails."""
        mock_translation_service = MagicMock()
        mock_translation_service.translate_text.return_value = "translated text"

        mock_neologism_detector = MagicMock()
        mock_neologism_detector.analyze_text.side_effect = Exception("Detection failed")

        service = PhilosophyEnhancedTranslationService(
            translation_service=mock_translation_service,
            neologism_detector=mock_neologism_detector,
        )

        # Should still work with degraded functionality
        result = service.translate_text_with_neologism_handling(
            "test text", "en", "de", "auto", "test_session"
        )

        assert result.translated_text == "translated text"
        assert (
            result.neologism_analysis is None
            or result.neologism_analysis.total_detections == 0
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
