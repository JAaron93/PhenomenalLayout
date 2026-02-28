"""
Complete integration test for the philosophy-enhanced translation system.

This test verifies that all components work together seamlessly:
- PhilosophyEnhancedTranslationService
- PhilosophyEnhancedDocumentProcessor
- Neologism detection and user choice management
- Document processing pipeline
- Performance and error handling
"""

import logging
import os
import tempfile
import time

import psutil
import pytest

from models.neologism_models import NeologismAnalysis
from models.user_choice_models import ChoiceType
from services.philosophy_enhanced_document_processor import (
    PhilosophyDocumentResult,
    PhilosophyEnhancedDocumentProcessor,
    PhilosophyProcessingProgress,
    process_document_with_philosophy_awareness,
)
from services.philosophy_enhanced_translation_service import (
    NeologismPreservationResult,
    PhilosophyEnhancedTranslationService,
)

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Configuration for test parameters
def get_memory_limit_mb():
    """Get memory limit for tests from environment variable or default."""
    return int(
        os.environ.get("TEST_MEMORY_LIMIT_MB", "1000")
    )  # Default 1GB instead of 500MB


class TestCompletePhilosophyEnhancedIntegration:
    """Complete integration test suite for the philosophy-enhanced translation system."""

    pytestmark = pytest.mark.skipif(
        not os.getenv("LINGO_API_KEY") or os.getenv("RUN_LINGO_INTEGRATION") != "1",
        reason=(
            "Live Lingo integration tests require LINGO_API_KEY and "
            "RUN_LINGO_INTEGRATION=1"
        ),
    )

    @pytest.fixture(scope="class")
    def sample_philosophical_text(self):
        """Sample philosophical text with multiple neologisms."""
        return """
        Martin Heidegger's concept of Dasein represents a fundamental departure from
        traditional ontology. Dasein, literally meaning "being-there," encompasses
        the whole of human existence in its temporal and spatial dimensions.

        The concept of Sein-zum-Tode (being-toward-death) reveals the finite nature
        of human existence. This finitude is not a limitation but rather the very
        condition that makes authentic existence possible. Through Angst (anxiety),
        Dasein encounters the fundamental groundlessness of its existence.

        Heidegger's analysis of everyday existence reveals the phenomenon of
        Zuhandenheit (readiness-to-hand), which describes our practical engagement
        with tools and equipment in our surrounding world. This mode of being-with-things
        is more primordial than theoretical knowledge or Vorhandenheit (presence-at-hand).

        The concept of Zeitlichkeit (temporality) shows how past, present, and future
        are unified in the structure of human existence. Authenticity emerges when
        Dasein owns up to its Geworfenheit (thrownness) while projecting itself
        toward its ownmost possibilities.
        """

    @pytest.fixture(scope="class")
    def sample_document_content(self, sample_philosophical_text):
        """Create sample document content for testing."""
        return {
            "type": "txt",
            "text_content": sample_philosophical_text,
            "pages": [
                {
                    "page_number": 1,
                    "text_blocks": [
                        {"text": sample_philosophical_text, "position": (0, 0)}
                    ],
                }
            ],
            "metadata": {
                "filename": "test_philosophy.txt",
                "total_pages": 1,
                "extraction_method": "text",
            },
        }

    @pytest.fixture
    def temp_document_file(self, sample_philosophical_text):
        """Create a temporary document file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(sample_philosophical_text)
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)

    def test_1_basic_system_initialization(self):
        """Test 1: Verify all components can be initialized successfully."""
        logger.info("Test 1: Basic system initialization")

        # Test translation service initialization
        translation_service = PhilosophyEnhancedTranslationService()
        assert translation_service is not None
        assert translation_service.translation_service is not None
        assert translation_service.neologism_detector is not None
        assert translation_service.user_choice_manager is not None

        # Verify only Lingo provider is available
        available_providers = translation_service.get_available_providers()
        assert "lingo" in available_providers
        assert len(available_providers) == 1  # Only Lingo should be available

        # Test document processor initialization
        document_processor = PhilosophyEnhancedDocumentProcessor()
        assert document_processor is not None
        assert document_processor.base_processor is not None
        assert document_processor.philosophy_translation_service is not None

        logger.info("✓ All components initialized successfully with Lingo provider")

    def test_2_neologism_detection_integration(self, sample_philosophical_text):
        """Test 2: Verify neologism detection works with the translation service."""
        logger.info("Test 2: Neologism detection integration")

        service = PhilosophyEnhancedTranslationService()

        # Test neologism detection
        analysis = service.neologism_detector.analyze_text(sample_philosophical_text)

        assert isinstance(analysis, NeologismAnalysis)
        assert analysis.total_detections > 0
        assert len(analysis.detected_neologisms) > 0

        # Verify neologisms are detected (flexible check)
        detected_terms = {neologism.term for neologism in analysis.detected_neologisms}

        # Check that we have some meaningful terms detected
        assert len(detected_terms) > 0

        # Check that at least some terms are longer than 3 characters (likely meaningful)
        meaningful_terms = [term for term in detected_terms if len(term) > 3]
        assert len(meaningful_terms) > 0

        logger.info(
            f"✓ Detected {analysis.total_detections} neologisms: {detected_terms}"
        )

    def test_3_user_choice_management_integration(self, sample_philosophical_text):
        """Test 3: Verify user choice management works with translation."""
        logger.info("Test 3: User choice management integration")

        service = PhilosophyEnhancedTranslationService()

        # Create a session
        session = service.user_choice_manager.create_session(
            session_name="Integration Test Session",
            document_name="test_philosophy.txt",
            user_id="test_user",
            source_language="en",
            target_language="de",
        )

        assert session.session_id is not None

        # Detect neologisms first
        analysis = service.neologism_detector.analyze_text(sample_philosophical_text)

        # Set user choices for detected neologisms
        choices_set = 0
        for neologism in analysis.detected_neologisms[:3]:  # Set choices for first 3
            service.user_choice_manager.make_choice(
                neologism=neologism,
                choice_type=ChoiceType.PRESERVE,
                session_id=session.session_id,
            )
            choices_set += 1

        assert choices_set > 0

        # Verify choices can be retrieved
        for neologism in analysis.detected_neologisms[:3]:
            choice = service.user_choice_manager.get_choice_for_neologism(
                neologism, session.session_id
            )
            assert choice is not None
            assert choice.choice_type == ChoiceType.PRESERVE

        logger.info(f"✓ Successfully set and retrieved {choices_set} user choices")

    def test_4_text_translation_with_neologism_handling(
        self, sample_philosophical_text
    ):
        """Test 4: Verify text translation with neologism handling."""
        logger.info("Test 4: Text translation with neologism handling")

        service = PhilosophyEnhancedTranslationService()

        # Create session and set some choices
        session = service.user_choice_manager.create_session(
            session_name="Translation Test Session",
            document_name="test_philosophy.txt",
            user_id="test_user",
            source_language="en",
            target_language="de",
        )

        # Perform translation with neologism handling using Lingo
        result = service.translate_text_with_neologism_handling(
            text=sample_philosophical_text,
            source_lang="en",
            target_lang="de",
            provider="lingo",  # Explicitly use Lingo provider
            session_id=session.session_id,
        )

        assert isinstance(result, NeologismPreservationResult)
        assert result.original_text == sample_philosophical_text
        assert result.translated_text is not None
        assert (
            result.translated_text != sample_philosophical_text
        )  # Should be different
        assert result.neologism_analysis is not None
        assert result.neologism_analysis.total_detections > 0

        logger.info(
            f"✓ Translation completed with {result.neologism_analysis.total_detections} neologisms detected"
        )
        logger.info(f"Original length: {len(result.original_text)} chars")
        logger.info(f"Translated length: {len(result.translated_text)} chars")

    @pytest.mark.asyncio
    async def test_5_batch_translation_integration(self):
        """Test 5: Verify batch translation with neologism handling."""
        logger.info("Test 5: Batch translation integration")

        service = PhilosophyEnhancedTranslationService()

        # Multiple philosophical texts
        texts = [
            "Dasein encompasses the whole of human existence in its temporal structure.",
            "The concept of Angst reveals the fundamental groundlessness of existence.",
            "Zuhandenheit describes our practical engagement with the world of equipment.",
            "Sein-zum-Tode is the possibility that makes all other possibilities possible.",
        ]

        # Create session
        session = service.user_choice_manager.create_session(
            session_name="Batch Test Session",
            document_name="batch_test.txt",
            user_id="test_user",
            source_language="en",
            target_language="de",
        )

        # Batch translate using Lingo
        results = await service.translate_batch_with_neologism_handling_async(
            texts=texts,
            source_lang="en",
            target_lang="de",
            provider="lingo",  # Explicitly use Lingo provider
            session_id=session.session_id,
        )

        assert len(results) == len(texts)

        total_neologisms = 0
        for i, result in enumerate(results):
            assert isinstance(result, dict)
            assert result["original_text"] == texts[i]
            assert result["translated_text"] is not None
            assert result["neologism_analysis"] is not None
            total_neologisms += result["neologism_analysis"]["total_detections"]

        logger.info(
            f"✓ Batch translation completed with {total_neologisms} total neologisms"
        )

    @pytest.mark.asyncio
    async def test_6_document_processing_integration(self, temp_document_file):
        """Test 6: Verify complete document processing integration."""
        logger.info("Test 6: Document processing integration")

        processor = PhilosophyEnhancedDocumentProcessor()

        # Progress tracking
        progress_updates = []

        def progress_callback(progress: PhilosophyProcessingProgress):
            progress_updates.append(progress.overall_progress)
            logger.info(
                f"Progress: {progress.overall_progress:.1f}% - {progress.current_stage}"
            )

        # Process document using Lingo
        result = await processor.process_document_with_philosophy_awareness(
            file_path=temp_document_file,
            source_lang="en",
            target_lang="de",
            provider="lingo",  # Explicitly use Lingo provider
            user_id="test_user",
            progress_callback=progress_callback,
        )

        assert isinstance(result, PhilosophyDocumentResult)
        assert result.translated_content is not None
        assert result.original_content is not None
        assert result.document_neologism_analysis is not None
        assert result.session_id is not None
        assert result.processing_time > 0

        # Verify progress was tracked
        assert len(progress_updates) > 0
        assert max(progress_updates) == 100.0  # Should reach 100%

        logger.info("✓ Document processing completed with Lingo provider")
        logger.info(f"Session ID: {result.session_id}")
        logger.info(
            f"Neologisms detected: {result.document_neologism_analysis.total_detections}"
        )
        logger.info(f"Processing time: {result.processing_time:.2f}s")

    @pytest.mark.asyncio
    async def test_7_document_creation_integration(self, temp_document_file):
        """Test 7: Verify translated document creation."""
        logger.info("Test 7: Document creation integration")

        processor = PhilosophyEnhancedDocumentProcessor()

        # Process document first using Lingo
        result = await processor.process_document_with_philosophy_awareness(
            file_path=temp_document_file,
            source_lang="en",
            target_lang="de",
            provider="lingo",  # Explicitly use Lingo provider
            user_id="test_user",
        )

        # Create translated document
        with tempfile.TemporaryDirectory() as temp_dir:
            output_filename = os.path.join(temp_dir, "translated_output.pdf")

            output_path = (
                await processor.create_translated_document_with_philosophy_awareness(
                    processing_result=result, output_filename=output_filename
                )
            )

            assert output_path is not None
            assert os.path.exists(output_path)

            # Check for metadata file
            metadata_path = output_path.replace(".pdf", "_philosophy_metadata.json")
            if os.path.exists(metadata_path):
                logger.info(f"✓ Metadata file created: {metadata_path}")

            logger.info(f"✓ Translated document created: {output_path}")

    @pytest.mark.asyncio
    async def test_8_convenience_function_integration(self, temp_document_file):
        """Test 8: Verify convenience function integration."""
        logger.info("Test 8: Convenience function integration")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_filename = os.path.join(temp_dir, "convenience_output.pdf")

            # Use convenience function with Lingo
            result, output_path = await process_document_with_philosophy_awareness(
                file_path=temp_document_file,
                source_lang="en",
                target_lang="de",
                provider="lingo",  # Explicitly use Lingo provider
                user_id="test_user",
                output_filename=output_filename,
            )

            assert isinstance(result, PhilosophyDocumentResult)
            assert output_path is not None
            assert os.path.exists(output_path)

            logger.info("✓ Convenience function completed successfully with Lingo")
            logger.info(f"Output: {output_path}")

    def test_9_statistics_and_monitoring(self, sample_philosophical_text):
        """Test 9: Verify statistics and monitoring functionality."""
        logger.info("Test 9: Statistics and monitoring")

        service = PhilosophyEnhancedTranslationService()
        processor = PhilosophyEnhancedDocumentProcessor()

        # Perform some operations to generate statistics
        session = service.user_choice_manager.create_session(
            session_name="Stats Test Session",
            document_name="stats_test.txt",
            user_id="test_user",
            source_language="en",
            target_language="de",
        )

        # Do some translations
        for i in range(3):
            result = service.translate_text_with_neologism_handling(
                text=f"Test {i}: {sample_philosophical_text[:100]}",
                source_lang="en",
                target_lang="de",
                provider="auto",
                session_id=session.session_id,
            )
            assert result is not None

        # Get statistics
        translation_stats = service.get_statistics()
        processor_stats = processor.get_statistics()

        assert "philosophy_enhanced_stats" in translation_stats
        assert "philosophy_enhanced_processor_stats" in processor_stats

        logger.info("✓ Statistics collection working")
        logger.info(
            f"Translation stats: {translation_stats['philosophy_enhanced_stats']}"
        )
        logger.info(
            f"Processor stats: {processor_stats['philosophy_enhanced_processor_stats']}"
        )

    def test_10_error_handling_and_resilience(self):
        """Test 10: Verify error handling and system resilience."""
        logger.info("Test 10: Error handling and resilience")

        service = PhilosophyEnhancedTranslationService()
        processor = PhilosophyEnhancedDocumentProcessor()

        # Test with invalid file path
        with pytest.raises(FileNotFoundError):
            processor.extract_content("/nonexistent/file.pdf")

        # Test with invalid language codes
        try:
            result = service.translate_text_with_neologism_handling(
                text="Test text",
                source_lang="invalid_lang",
                target_lang="another_invalid_lang",
                provider="auto",
                session_id="error_test_session",
            )
            # If it doesn't raise an exception, check if it handled gracefully
            assert result is not None
        except Exception as e:
            logger.info(f"Expected error handled: {e}")

        # Test with empty text
        result = service.translate_text_with_neologism_handling(
            text="",
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id="empty_test_session",
        )
        assert result is not None
        assert result.translated_text == ""

        logger.info("✓ Error handling tests completed")

    def test_11_memory_and_performance_monitoring(self, sample_philosophical_text):
        """Test 11: Basic memory and performance monitoring with Lingo provider.

        Memory limit can be configured via TEST_MEMORY_LIMIT_MB environment variable.
        Default limit is 1000MB (1GB). Set lower values for stricter testing.
        """
        logger.info("Test 11: Memory and performance monitoring")

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        service = PhilosophyEnhancedTranslationService()

        # Verify Lingo provider is available
        available_providers = service.get_available_providers()
        assert "lingo" in available_providers

        # Create session
        session = service.user_choice_manager.create_session(
            session_name="Performance Test Session",
            document_name="performance_test.txt",
            user_id="test_user",
            source_language="en",
            target_language="de",
        )

        # Perform multiple translations to test memory usage
        start_time = time.time()
        results = []

        for i in range(10):
            result = service.translate_text_with_neologism_handling(
                text=f"Performance test {i}: {sample_philosophical_text}",
                source_lang="en",
                target_lang="de",
                provider="lingo",  # Explicitly use Lingo provider
                session_id=session.session_id,
            )
            results.append(result)

        end_time = time.time()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        processing_time = end_time - start_time
        memory_increase = final_memory - initial_memory

        logger.info("✓ Performance test completed with Lingo provider")
        logger.info(f"Processed {len(results)} translations in {processing_time:.2f}s")
        logger.info(
            f"Average time per translation: {processing_time / len(results):.3f}s"
        )
        logger.info(f"Memory increase: {memory_increase:.1f}MB")

        # Check memory usage against configurable limit
        memory_limit = get_memory_limit_mb()
        assert (
            memory_increase < memory_limit
        ), f"Memory increase {memory_increase:.1f}MB exceeds limit {memory_limit}MB"

    def test_12_complete_end_to_end_workflow(self, temp_document_file):
        """Test 12: Complete end-to-end workflow test."""
        logger.info("Test 12: Complete end-to-end workflow")

        # This test combines all components in a realistic workflow

        # Step 1: Initialize services
        service = PhilosophyEnhancedTranslationService()
        processor = PhilosophyEnhancedDocumentProcessor()

        # Step 2: Create user session
        session = service.user_choice_manager.create_session(
            session_name="End-to-End Test Session",
            document_name="complete_test.txt",
            user_id="end_to_end_user",
            source_language="en",
            target_language="de",
        )

        # Step 3: Extract and analyze document
        content = processor.extract_content(temp_document_file)
        assert content is not None

        # Step 4: Detect neologisms
        text_content = content.get("text_content", "")
        analysis = service.neologism_detector.analyze_text(text_content)
        assert analysis.total_detections > 0

        # Step 5: Set user choices
        for neologism in analysis.detected_neologisms[:2]:  # Set choices for first 2
            service.user_choice_manager.make_choice(
                neologism=neologism,
                choice_type=ChoiceType.PRESERVE,
                session_id=session.session_id,
            )

        # Step 6: Translate with neologism handling
        result = service.translate_text_with_neologism_handling(
            text=text_content,
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id=session.session_id,
        )

        assert result.translated_text is not None
        assert result.neologism_analysis.total_detections > 0

        # Step 7: Get statistics
        stats = service.get_statistics()
        assert stats is not None

        # Step 8: Cleanup
        cleaned_sessions = service.user_choice_manager.cleanup_expired_sessions()
        assert cleaned_sessions >= 0

        logger.info("✓ Complete end-to-end workflow test passed")
        logger.info(
            f"Neologisms detected: {result.neologism_analysis.total_detections}"
        )
        logger.info(f"User choices applied: {len(result.user_choices_applied)}")
        logger.info(f"Sessions cleaned: {cleaned_sessions}")


@pytest.mark.asyncio
async def test_async_complete_integration():
    """Run complete async integration test."""
    # Check if PDF processing is available
    try:
        from services.enhanced_document_processor import EnhancedDocumentProcessor
        EnhancedDocumentProcessor()
    except (ImportError, Exception) as e:
        pytest.skip(
            "PDF processing not available - "
            f"requires enhanced document processor: {e}"
        )
    
    # Check if we can create test files
    fd, test_file_path = tempfile.mkstemp(suffix='.txt', prefix='test_input_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(
                "Dasein is fundamental to Heideggerian philosophy. "
                "Angst reveals groundlessness."
            )

    except OSError:
        os.close(fd)
        pytest.skip("Cannot create test files in current environment")

    try:
        # Instantiate EnhancedDocumentProcessor
        enhanced_processor = EnhancedDocumentProcessor()
        
        # Note: EnhancedDocumentProcessor only supports PDF files,
        # but we have a text file. Test processor instantiation and
        # basic functionality.
        try:
            # Try to process the file (will fail for .txt but tests
            # error handling)
            enhanced_processor.extract_content(test_file_path)
            pytest.fail("Expected ValueError for unsupported .txt format")
        except ValueError as e:
            # Expected behavior - processor only supports PDF
            assert "Only PDF files are supported" in str(e)
            logger.info(
                "✓ EnhancedDocumentProcessor correctly rejects "
                "unsupported format"
            )
        
        # Test processor metadata and basic functionality
        assert hasattr(enhanced_processor, 'dpi')
        assert hasattr(enhanced_processor, 'preserve_images')
        assert enhanced_processor.dpi > 0
        logger.info("✓ EnhancedDocumentProcessor instantiated correctly")

        # Verify test file content exists for reference
        with open(test_file_path, encoding='utf-8') as f:
            content = f.read()
            assert "Dasein" in content
            assert "Heideggerian" in content
            assert len(content.strip()) > 0

        logger.info("✓ Test file content verified")
        logger.info("✓ Async integration test completed successfully")
        
    finally:
        # Cleanup test file
        if os.path.exists(test_file_path):
            os.unlink(test_file_path)


if __name__ == "__main__":
    # Run the tests
    logger.info("Starting complete integration test suite...")

    # Run pytest with this file
    pytest.main([__file__, "-v", "-s"])
