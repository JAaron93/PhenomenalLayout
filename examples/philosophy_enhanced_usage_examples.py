"""
Comprehensive examples demonstrating the philosophy-enhanced translation system.

This script provides practical examples of how to use the
PhilosophyEnhancedTranslationService and PhilosophyEnhancedDocumentProcessor
for various translation scenarios involving philosophical texts with neologisms.
"""

import logging
from typing import Any

from core.dynamic_choice_engine import OptimizedUserChoiceManager as UserChoiceManager
from models.user_choice_models import ChoiceSession, ChoiceType
from services.philosophy_enhanced_document_processor import (
    create_philosophy_enhanced_document_processor,
    process_document_with_philosophy_awareness,
)
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
    PhilosophyTranslationProgress,
)


def _configure_logging() -> None:
    """Configure logging for the examples."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )


logger: logging.Logger = logging.getLogger(__name__)


class PhilosophyTranslationExamples:
    """Examples demonstrating philosophy-enhanced text translation."""

    def __init__(self) -> None:
        self.service: PhilosophyEnhancedTranslationService = (
            PhilosophyEnhancedTranslationService()
        )
        self.user_choice_manager: UserChoiceManager = UserChoiceManager()

    def example_1_basic_text_translation(self) -> Any:
        """Example 1: Basic text translation with neologism detection."""
        print("EXAMPLE 1: Basic Text Translation with Neologism Detection")
        print("=" * 80)

        # Sample philosophical text with neologisms
        text: str = """
        Dasein is a fundamental concept in Heideggerian philosophy. The notion of
        Sein-zum-Tode (being-toward-death) reveals the authenticity of human existence.
        Heidegger's concept of Zuhandenheit (readiness-to-hand) describes our
        relationship with tools and equipment in our everyday world.
        """

        print(f"Original text: {text.strip()}")
        print("Translating from English to German...")

        # Translate with neologism handling
        result: Any = self.service.translate_text_with_neologism_handling(
            text=text.strip(),
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id="example_session_1",
        )

        print(f"Translated text: {result.translated_text}")
        print(f"Neologisms detected: {result.neologism_analysis.total_neologisms}")
        print(f"Neologisms preserved: {len(result.neologisms_preserved)}")

        if result.neologism_analysis.detected_neologisms:
            print("Detected neologisms:")
            for neologism in result.neologism_analysis.detected_neologisms:
                print(f"  - {neologism.term} (confidence: {neologism.confidence:.2f})")
        return result

    def example_2_batch_translation(self) -> list[Any]:
        """Example 2: Batch translation of multiple philosophical texts."""
        print("\n" + "=" * 80)
        print("EXAMPLE 2: Batch Translation with Neologism Handling")
        print("=" * 80)

        # Multiple philosophical texts
        texts: list[str] = [
            "Dasein encompasses the whole of human existence in its temporal structure.",
            "The concept of Angst reveals the fundamental groundlessness of existence.",
            "Zuhandenheit describes our practical engagement with the world of equipment.",
            "Sein-zum-Tode is the possibility that makes all other possibilities possible.",
        ]

        print(f"Translating {len(texts)} philosophical texts...")

        # Batch translate with neologism handling
        results: list[Any] = self.service.translate_batch_with_neologism_handling(
            texts=texts,
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id="example_session_2",
        )

        print("Results:")
        for i, result in enumerate(results):
            print(f"\n  Text {i + 1}:")
            print(f"    Original: {texts[i]}")
            print(f"    Translated: {result.translated_text}")
            print(f"    Neologisms: {result.neologism_analysis.total_neologisms}")

        return results

    def example_3_user_choice_management(self) -> tuple[Any, ChoiceSession]:
        """Example 3: Managing user choices for neologism handling."""
        print("\n" + "=" * 80)
        print("EXAMPLE 3: User Choice Management for Neologisms")
        print("=" * 80)

        # Create a session for user choices
        session: ChoiceSession = self.user_choice_manager.create_session(
            session_name="Philosophy Translation Session",
            document_name="Heidegger Analysis",
            user_id="philosopher_user",
            source_language="en",
            target_language="de",
        )

        print(f"Created session: {session.session_id}")

        # Sample text with neologisms
        text: str = (
            "The concept of Dasein is central to understanding Heidegger's Angst."
        )

        # First, detect neologisms
        analysis: Any = self.service.neologism_detector.analyze_text(text)
        print(f"Detected {analysis.total_neologisms} neologisms")

        # Set user choices for specific neologisms
        for neologism in analysis.detected_neologisms:
            if neologism.term == "Dasein":
                self.user_choice_manager.set_choice(
                    neologism=neologism,
                    choice_type=ChoiceType.PRESERVE,
                    session_id=session.session_id,
                    custom_translation=None,
                )
                print(f"Set choice for '{neologism.term}': PRESERVE")
            elif neologism.term == "Angst":
                self.user_choice_manager.set_choice(
                    neologism=neologism,
                    choice_type=ChoiceType.CUSTOM,
                    session_id=session.session_id,
                    custom_translation="Anxiety",
                )
                print(f"Set choice for '{neologism.term}': CUSTOM (Anxiety)")

        # Now translate with applied choices
        result: Any = self.service.translate_text_with_neologism_handling(
            text=text,
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id=session.session_id,
        )

        print(f"Translation with user choices: {result.translated_text}")

        return result, session

    def example_4_progress_tracking(self) -> Any:
        """Example 4: Progress tracking during translation."""
        print("\n" + "=" * 80)
        print("EXAMPLE 4: Progress Tracking During Translation")
        print("=" * 80)

        # Progress callback function
        def progress_callback(progress: PhilosophyTranslationProgress) -> None:
            logger.info(
                "Progress: %.1f%% - Stage: %s",
                progress.overall_progress,
                progress.current_stage,
            )
            logger.info(
                "  Text Processing: %s%%",
                progress.text_processing_progress,
            )
            logger.info(
                "  Neologism Detection: %s%%",
                progress.neologism_detection_progress,
            )
            logger.info(
                "  User Choice Application: %s%%",
                progress.user_choice_application_progress,
            )
            logger.info("  Translation: %s%%", progress.translation_progress)

        # Long philosophical text for demonstration
        long_text: str = """
        Martin Heidegger's concept of Dasein fundamentally challenges traditional ontology.
        The notion of Sein-zum-Tode (being-toward-death) reveals the temporal structure
        of human existence. The concept of Zuhandenheit (readiness-to-hand) describes
        our practical engagement with the world of equipment. Angst (anxiety) reveals
        the fundamental groundlessness of human existence.
        """

        print("Translating long philosophical text with progress tracking...")

        # Translate with progress tracking
        result: Any = self.service.translate_text_with_neologism_handling(
            text=long_text.strip(),
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id="example_session_4",
            progress_callback=progress_callback,
        )

        print(f"Translation completed: {result.translated_text[:100]}...")
        return result

    def example_5_document_processing(self) -> Any:
        """Example 5: Processing complete documents with philosophy awareness."""
        print("\n" + "=" * 80)
        print("EXAMPLE 5: Document Processing with Philosophy Awareness")
        print("=" * 80)

        # Create document processor
        processor = create_philosophy_enhanced_document_processor()

        # Sample document content (simplified for example)
        document_content: dict[str, Any] = {
            "type": "philosophy_document",
            "title": "Heidegger's Being and Time Analysis",
            "content": [
                "The concept of Dasein is central to understanding human existence.",
                "Sein-zum-Tode reveals the authentic temporal structure of being.",
                "Zuhandenheit describes our practical world engagement.",
            ],
            "metadata": {
                "author": "Martin Heidegger",
                "genre": "philosophy",
                "language": "en",
            },
        }

        # Validate required document fields before processing
        required_fields = ["type", "title", "content", "metadata"]
        missing_fields = [
            field for field in required_fields if field not in document_content
        ]
        if missing_fields:
            raise ValueError(f"Missing required document fields: {missing_fields}")

        # Validate metadata contains required fields
        if "metadata" in document_content:
            required_metadata = ["author", "genre", "language"]
            missing_metadata = [
                field
                for field in required_metadata
                if field not in document_content["metadata"]
            ]
            if missing_metadata:
                raise ValueError(
                    f"Missing required metadata fields: {missing_metadata}"
                )

        print("Processing document with philosophy awareness...")

        # Process document
        result: Any = process_document_with_philosophy_awareness(
            document_content=document_content,
            target_language="de",
            processor=processor,
        )

        print("Document processed successfully")
        print(f"Translated content: {len(result.translated_content)} sections")
        print(f"Neologisms handled: {result.neologism_summary.total_detections}")

        return result

    def example_6_error_handling(self) -> None:
        """Example 6: Error handling and fallback strategies."""
        print("\n" + "=" * 80)
        print("EXAMPLE 6: Error Handling and Fallback Strategies")
        print("=" * 80)

        # Test with problematic text
        problematic_text: str = (
            "This text contains very long technical terms that might cause issues."
        )

        try:
            result: Any = self.service.translate_text_with_neologism_handling(
                text=problematic_text,
                source_lang="en",
                target_lang="de",
                provider="auto",
                session_id="example_session_6",
            )
            print(f"Translation successful: {result.translated_text}")
        except Exception as e:
            logger.error("Translation failed: %s", e)
            print(f"Translation failed: {e}")

        # Test fallback behavior
        try:
            result: Any = self.service.translate_text_with_neologism_handling(
                text=problematic_text,
                source_lang="en",
                target_lang="de",
                provider="fallback",
                session_id="example_session_6",
                fallback_to_basic=True,
            )
            print(f"Fallback translation: {result.translated_text}")
        except Exception as e:
            logger.error("Fallback translation failed: %s", e)
            print(f"Fallback translation failed: {e}")

    def example_7_performance_optimization(self) -> None:
        """Example 7: Performance optimization techniques."""
        print("\n" + "=" * 80)
        print("EXAMPLE 7: Performance Optimization Techniques")
        print("=" * 80)

        # Large batch of texts for performance testing
        large_texts: list[str] = [
            f"Philosophical text {i} with neologisms and complex terminology."
            for i in range(100)
        ]

        print(f"Processing {len(large_texts)} texts for performance testing...")

        # Measure performance
        import time

        start_time: float = time.perf_counter()

        results: list[Any] = self.service.translate_batch_with_neologism_handling(
            texts=large_texts[
                :10
            ],  # Limited to 10 texts for quick demonstration; adjust for actual performance testing
            source_lang="en",
            target_lang="de",
            provider="auto",
            session_id="example_session_7",
            batch_size=5,  # Optimize batch size
        )

        end_time: float = time.perf_counter()
        processing_time: float = end_time - start_time

        print(f"Processed {len(results)} texts in {processing_time:.2f} seconds")
        avg_time = processing_time / len(results) if results else 0.0
        print(f"Average time per text: {avg_time:.3f} seconds")

    def run_all_examples(self) -> None:
        """Run all examples in sequence."""
        print("Running Philosophy-Enhanced Translation Examples")
        print("=" * 80)

        try:
            # Run examples and capture return values for logging
            print("Running example 1: Basic text translation...")
            result1 = self.example_1_basic_text_translation()
            print(f"Example 1 completed. Translation result type: {type(result1)}")

            print("Running example 2: Batch translation...")
            results2 = self.example_2_batch_translation()
            print(f"Example 2 completed. Translated {len(results2)} texts")

            print("Running example 3: User choice management...")
            result3, session3 = self.example_3_user_choice_management()
            print(
                f"Example 3 completed. Session: {session3.session_id}, "
                f"Result type: {type(result3)}"
            )

            print("Running example 4: Progress tracking...")
            result4 = self.example_4_progress_tracking()
            print(f"Example 4 completed. Result type: {type(result4)}")

            print("Running example 5: Document processing...")
            result5 = self.example_5_document_processing()
            print(f"Example 5 completed. Result type: {type(result5)}")

            print("Running example 6: Error handling...")
            self.example_6_error_handling()
            print("Example 6 completed (no return value)")

            print("Running example 7: Performance optimization...")
            self.example_7_performance_optimization()
            print("Example 7 completed (no return value)")

            print("\n" + "=" * 80)
            print("All examples completed successfully!")
            print("=" * 80)

        except Exception as e:
            logger.error("Example execution failed: %s", e)
            print(f"Example execution failed: {e}")


def main() -> None:
    """Main function to run the examples."""
    _configure_logging()

    examples = PhilosophyTranslationExamples()
    examples.run_all_examples()


if __name__ == "__main__":
    main()
