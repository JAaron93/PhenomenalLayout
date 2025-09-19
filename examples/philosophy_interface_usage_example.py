"""
Philosophy Interface Usage Example
Demonstrates how to use the enhanced philosophy-focused translation interface
"""

import asyncio
import logging
import traceback

from core.dynamic_choice_engine import OptimizedUserChoiceManager as UserChoiceManager
from models.user_choice_models import ChoiceScope, ChoiceType
from services.neologism_detector import NeologismDetector

# Import the philosophy enhanced services
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def philosophy_translation_example():
    """Example of using the philosophy-enhanced translation interface"""

    # Initialize variables for cleanup
    user_choice_manager = None
    session = None

    try:
        print("=== Philosophy-Enhanced Translation Interface Example ===\n")

        # Initialize the philosophy-enhanced translation service
        print("1. Initializing Philosophy-Enhanced Translation Service...")

        # Initialize components
        try:
            neologism_detector = NeologismDetector(
                terminology_path="config/klages_terminology.json",
                philosophical_threshold=0.5,
            )

            user_choice_manager = UserChoiceManager(
                db_path="philosophy_example.db", auto_resolve_conflicts=True
            )

            philosophy_service = PhilosophyEnhancedTranslationService(
                neologism_detector=neologism_detector,
                user_choice_manager=user_choice_manager,
                preserve_neologisms_by_default=True,
                neologism_confidence_threshold=0.6,
            )

            print("✅ Services initialized successfully\n")

        except Exception as e:
            print(f"❌ Error initializing services: {e}")
            logger.error(f"Service initialization failed: {e}")
            raise

        # Example philosophical text (German)
        philosophical_text = """
        Die Lebensphilosophie betrachtet das Bewusstsein als einen besonderen Zustand der Seele,
        der sich durch Intuition und unmittelbare Lebenserfahrung auszeichnet. Klages entwickelt
        eine Charakterologie, die das Wesen der menschlichen Persönlichkeit durch biozentrische
        Weltanschauung erforscht. Die Pathognomik ermöglicht es, die Ausdrucksbewegungen der Seele
        zu verstehen und ihre Rhythmen zu deuten. Das Bewusstseinsphänomen steht im Gegensatz zur
        reinen Vitalität und zeigt die Spannung zwischen Geist und Leben.
        """

        print("2. Sample Philosophical Text (German):")
        print(f"   {philosophical_text[:100]}...\n")

        # Create a session for this translation
        print("3. Creating Translation Session...")
        try:
            session = user_choice_manager.create_session(
                session_name="Philosophy Example Session",
                document_name="Klages Philosophy Text",
                source_language="de",
                target_language="en",
            )
            print(f"✅ Created session: {session.session_id}\n")

        except Exception as e:
            print(f"❌ Error creating session: {e}")
            logger.error(f"Session creation failed: {e}")
            raise

        # Translate with neologism detection
        print("4. Performing Philosophy-Enhanced Translation...")

        def progress_callback(progress):
            print(
                f"   Progress: {progress.overall_progress:.1f}% "
                f"(Neologisms: {progress.processed_neologisms}/{progress.total_neologisms})"
            )

        try:
            result = await philosophy_service.translate_text_with_neologism_handling(
                text=philosophical_text,
                source_lang="de",
                target_lang="en",
                session_id=session.session_id,
                progress_callback=progress_callback,
            )

            print("\n✅ Translation completed!\n")

        except Exception as e:
            print(f"❌ Error during translation: {e}")
            logger.error(f"Translation failed: {e}")
            raise

        # Display results
        print("5. Translation Results:")
        print("=" * 50)
        print("ORIGINAL TEXT:")
        print(philosophical_text)
        print("\nTRANSLATED TEXT:")
        print(result["translated_text"])
        print("=" * 50)

        # Display neologism analysis
        print("\n6. Neologism Analysis:")
        neologism_analysis = result["neologism_analysis"]
        print(f"   Total neologisms detected: {neologism_analysis['total_detections']}")
        print(
            f"   Confidence distribution: {neologism_analysis['confidence_distribution']}"
        )
        print(f"   Type distribution: {neologism_analysis['type_distribution']}")

        print("\n   Detected Neologisms:")
        for neologism in neologism_analysis["detected_neologisms"][:5]:  # Show first 5
            print(
                f"   - {neologism['term']} (confidence: {neologism['confidence']:.2f})"
            )
            print(f"     Type: {neologism['neologism_type']}")
            print(f"     Context: {neologism['sentence_context'][:50]}...")
            print()

        # Demonstrate user choice management
        print("7. User Choice Management Example:")

        # Make some example choices
        if neologism_analysis["detected_neologisms"]:
            try:
                first_neologism_data = neologism_analysis["detected_neologisms"][0]

                # Use factory method to create neologism object from dictionary
                from models.neologism_models import DetectedNeologism

                neologism = DetectedNeologism.from_dict(first_neologism_data)

                # Make a choice to preserve the neologism
                choice = user_choice_manager.make_choice(
                    neologism=neologism,
                    choice_type=ChoiceType.PRESERVE,
                    session_id=session.session_id,
                    choice_scope=ChoiceScope.GLOBAL,
                    confidence_level=0.9,
                    user_notes="Preserving this important philosophical term",
                )

                print(f"   ✅ Made choice for '{neologism.term}': PRESERVE")
                print(f"   Choice ID: {choice.choice_id}")

            except Exception as e:
                print(f"❌ Error making user choice: {e}")
                logger.error(f"User choice creation failed: {e}")
                # Continue with rest of example

        # Export session data
        print("\n8. Exporting Session Data...")
        try:
            export_file = user_choice_manager.export_session_choices(session.session_id)
            if export_file:
                print(f"   ✅ Session data exported to: {export_file}")
            else:
                print("   ⚠️  No session data to export")

        except Exception as e:
            print(f"❌ Error exporting session data: {e}")
            logger.error(f"Session export failed: {e}")
            # Continue with rest of example

        # Get session statistics
        print("\n9. Session Statistics:")
        try:
            stats = user_choice_manager.get_statistics()
            print(
                f"   Total choices made: {stats['manager_stats']['total_choices_made']}"
            )
            print(f"   Active sessions: {stats['active_sessions']}")

        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            logger.error(f"Statistics retrieval failed: {e}")
            # Continue with cleanup

        print("\n=== Philosophy Interface Example Complete ===")

    except Exception as e:
        print(f"\n❌ Critical error in philosophy translation example: {e}")
        logger.error(f"Critical error: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")

    finally:
        # Cleanup: Complete the session if it was created
        if user_choice_manager and session:
            try:
                user_choice_manager.complete_session(session.session_id)
                print(f"✅ Session completed: {session.session_id}")
            except Exception as e:
                print(f"⚠️  Warning: Could not complete session: {e}")
                logger.warning(f"Session cleanup failed: {e}")

        # Close database connections if available
        if user_choice_manager:
            try:
                if hasattr(user_choice_manager, "close"):
                    user_choice_manager.close()
                print("✅ Resources cleaned up successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not clean up resources: {e}")
                logger.warning(f"Resource cleanup failed: {e}")


def web_interface_usage_guide():
    """Guide for using the web interface"""

    print("\n=== Web Interface Usage Guide ===\n")

    print("1. Starting the Application:")
    print("   python app.py")
    print("   Then navigate to: http://localhost:8000/philosophy\n")

    print("2. Interface Sections:")
    print("   📋 Neologism Review - Review and make choices for detected neologisms")
    print("   📚 Terminology Management - Manage philosophical terminology database")
    print(
        "   ⚙️ Philosophy Settings - Configure detection sensitivity and author context"
    )
    print("   📊 Session Analytics - View translation statistics and progress\n")

    print("3. Workflow:")
    print("   a) Upload document using main interface (/ui)")
    print("   b) Enable 'Philosophy Mode' checkbox")
    print("   c) Start translation")
    print("   d) Switch to Philosophy Interface (/philosophy)")
    print("   e) Review detected neologisms")
    print("   f) Make choices: Preserve, Translate, or Custom Translation")
    print("   g) Export/Import terminology and choices\n")

    print("4. Key Features:")
    print("   🔍 Real-time neologism detection during translation")
    print("   ⚡ Interactive user choice interface")
    print("   📈 Visual confidence indicators")
    print("   🔄 Batch operations for multiple neologisms")
    print("   💾 Export/Import functionality for terminology")
    print("   📱 Responsive design for desktop and mobile\n")

    print("5. Philosophy Settings:")
    print("   - Detection Sensitivity: Adjust neologism detection threshold")
    print("   - Author Context: Set philosophical tradition (Klages, Heidegger, etc.)")
    print("   - Auto-preserve: Automatically preserve high-confidence neologisms")
    print("   - Real-time Detection: Enable live neologism detection")
    print("   - Context Analysis: Enhanced semantic field analysis\n")

    print("6. Terminology Management:")
    print("   - View existing philosophical terminology")
    print("   - Add new terms and translations")
    print("   - Import terminology from JSON/CSV files")
    print("   - Export terminology for sharing")
    print("   - Search and filter terminology entries\n")

    print("7. Session Analytics:")
    print("   - Detection summary and statistics")
    print("   - Choice distribution visualization")
    print("   - Processing time metrics")
    print("   - Semantic field analysis")
    print("   - Export session reports\n")


def example_api_usage():
    """Example of using the Philosophy API endpoints"""

    print("=== Philosophy API Usage Examples ===\n")

    print("1. Save User Choice:")
    print(
        """
    POST /api/philosophy/choice
    {
        "term": "Bewusstseinsphänomen",
        "choice": "preserve",
        "custom_translation": "",
        "notes": "Important philosophical concept",
        "session_id": "session_123"
    }
    """
    )

    print("2. Get Detected Neologisms:")
    print(
        """
    GET /api/philosophy/neologisms?session_id=session_123

    Response:
    {
        "neologisms": [...],
        "total": 15
    }
    """
    )

    print("3. Get Progress:")
    print(
        """
    GET /api/philosophy/progress

    Response:
    {
        "total_neologisms": 15,
        "processed_neologisms": 8,
        "choices_made": 5,
        "session_id": "session_123",
        "philosophy_mode": true
    }
    """
    )

    print("4. Export Choices:")
    print(
        """
    POST /api/philosophy/export-choices
    {
        "session_id": "session_123"
    }

    Returns: JSON file download
    """
    )

    print("5. Import Choices:")
    print(
        """
    POST /api/philosophy/import-choices
    {
        "choices": {...},
        "session_id": "session_123"
    }

    Response:
    {
        "success": true,
        "count": 10,
        "message": "Imported 10 choices successfully"
    }
    """
    )

    print("6. Get Terminology:")
    print(
        """
    GET /api/philosophy/terminology

    Response:
    {
        "Lebensphilosophie": "philosophy of life",
        "Bewusstsein": "consciousness",
        "Weltanschauung": "worldview",
        ...
    }
    """
    )


if __name__ == "__main__":
    # Run the async example
    asyncio.run(philosophy_translation_example())

    # Show web interface guide
    web_interface_usage_guide()

    # Show API examples
    example_api_usage()
