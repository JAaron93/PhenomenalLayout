"""Core services package containing document processing, translation.

And language detection functionality.
"""

import logging

logger: logging.Logger = logging.getLogger(__name__)

# Conditional imports with external dependency handling
_available_services: list[str] = []
_service_availability: dict[str, bool] = {}

# Always available services (no external dependencies)
try:
    from .neologism_detector import NeologismDetector  # noqa: F401

    _available_services.append("NeologismDetector")
    _service_availability["NEOLOGISM_DETECTOR_AVAILABLE"] = True
    logger.debug("NeologismDetector imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import NeologismDetector: {e}")
    _service_availability["NEOLOGISM_DETECTOR_AVAILABLE"] = False

# Services with external dependencies
try:
    from .translation_service import TranslationService  # noqa: F401

    _available_services.append("TranslationService")
    _service_availability["TRANSLATION_SERVICE_AVAILABLE"] = True
    logger.debug("TranslationService imported successfully")
except ImportError as e:
    logger.debug(f"TranslationService not available: {e}")
    _service_availability["TRANSLATION_SERVICE_AVAILABLE"] = False

try:
    from core.dynamic_language_engine import (  # noqa: F401
        OptimizedLanguageDetector as LanguageDetector,
    )

    _available_services.append("LanguageDetector")
    _service_availability["LANGUAGE_DETECTOR_AVAILABLE"] = True
    logger.debug("OptimizedLanguageDetector imported successfully")
except ImportError as e:
    logger.debug(f"OptimizedLanguageDetector not available: {e}")
    _service_availability["LANGUAGE_DETECTOR_AVAILABLE"] = False

try:
    from .enhanced_document_processor import EnhancedDocumentProcessor  # noqa: F401

    _available_services.append("EnhancedDocumentProcessor")
    _service_availability["ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE"] = True
    logger.debug("EnhancedDocumentProcessor imported successfully")
except ImportError as e:
    logger.debug(f"EnhancedDocumentProcessor not available: {e}")
    _service_availability["ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE"] = False

# Dynamically build __all__ list based on successfully imported services
# Include service symbols, availability flags, and summary counters
__all__: list[str] = [
    *_available_services,
    "NEOLOGISM_DETECTOR_AVAILABLE",
    "TRANSLATION_SERVICE_AVAILABLE",
    "LANGUAGE_DETECTOR_AVAILABLE",
    "ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE",
    "services_count",
    "services_list",
    "AVAILABLE_SERVICES",
]

# Export availability flags for runtime dependency checking
NEOLOGISM_DETECTOR_AVAILABLE: bool = _service_availability[
    "NEOLOGISM_DETECTOR_AVAILABLE"
]
TRANSLATION_SERVICE_AVAILABLE: bool = _service_availability[
    "TRANSLATION_SERVICE_AVAILABLE"
]
LANGUAGE_DETECTOR_AVAILABLE: bool = _service_availability["LANGUAGE_DETECTOR_AVAILABLE"]
ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE: bool = _service_availability[
    "ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE"
]

# Log summary of available services
services_count: int = len(_available_services)
services_list: str = ", ".join(_available_services)
AVAILABLE_SERVICES: list[
    str
] = _available_services.copy()  # Machine-friendly list of available services
logger.info(
    f"Services module initialized with {services_count} "
    f"available services: {services_list}"
)
