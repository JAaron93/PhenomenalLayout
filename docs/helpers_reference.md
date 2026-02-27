# Project Helpers Reference

This document catalogs shared utility functions added to consolidate logic and maintain DRY principles.

## Language Identification & Text Processing
**Location:** `utils/language_utils.py`

### `DEFAULT_SUPPORTED_LANGUAGES` (Constant)
- **Description:** A canonical list of 15 supported languages for translation and layout processing.
- **Previous Duplication:** Was hardcoded in `ui/gradio_interface.py` (3 times) and `utils/validators.py`.
- **Usage:** Import for fallback language initialization or validation where config is unavailable.

### `get_german_morphological_patterns()`
- **Description:** Returns a dictionary of regular expressions and term lists used to analyze compound words, prefixes, and philosophical suffixes in German text.
- **Previous Duplication:** A 50-line identical dictionary was instantiated in both `services/morphological_analyzer.py` and `services/neologism_detector.py`.
- **Usage:** Call to acquire the standard `dict[str, list[str]]` of morphological patterns.

## OCR Result Processing
**Location:** `services/ocr_utils.py`

### `parse_ocr_result(result: dict[str, Any]) -> list[list[TextBlock]]`
- **Description:** Standardizes the extraction of text, bounding boxes, confidence scores, and font data from OCR service JSON payloads into domain-specific `TextBlock` and `LayoutContext` objects.
- **Previous Duplication:** This complex 40-line `_parse_ocr_result` method was duplicated across `services/async_document_processor.py` and `services/main_document_processor.py`.
- **Usage:** Pass the raw OCR dictionary to receive a structured list of text blocks per page.

## Database & Session State Management
**Location:** `core/dynamic_choice_engine.py`

### `create_session_for_document(manager, document_name, ...)`
- **Description:** A unified API for initializing a document processing `ChoiceSession` regardless of whether the standard `UserChoiceManager` or the `OptimizedUserChoiceManager` is used.
- **Previous Duplication:** Session initialization logic was directly coded within `services/philosophy_enhanced_document_processor.py`.
- **Usage:** Used primarily before triggering document-wide neologism detection pipelines to ensure state tracking.
