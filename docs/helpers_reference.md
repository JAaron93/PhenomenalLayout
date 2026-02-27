# Project Helpers Reference

This document catalogs shared utility functions added to consolidate logic and maintain DRY principles.

## Language Identification & Text Processing
**Location:** `utils/language_utils.py`

### `DEFAULT_SUPPORTED_LANGUAGES` (Constant)
- **Description:** A canonical list of supported languages for translation and layout processing: English, Spanish, French, German, Italian, Portuguese, Russian, Chinese, Japanese, Korean, Arabic, Hindi, Dutch, Swedish, Norwegian.
- **Previous Duplication:** Was hardcoded in `ui/gradio_interface.py` (3 times) and `utils/validators.py`.
- **Usage:** Import for fallback language initialization or validation where config is unavailable.
- **Example:**
  ```python
  from utils.language_utils import DEFAULT_SUPPORTED_LANGUAGES

  def validate_language(lang: str) -> bool:
      return lang in DEFAULT_SUPPORTED_LANGUAGES
  ```

### `get_german_morphological_patterns()`
- **Description:** Returns a dictionary of regular expressions and term lists used to analyze compound words, prefixes, and philosophical suffixes in German text.
- **Previous Duplication:** An identical dictionary was duplicated in both `services/morphological_analyzer.py` and `services/neologism_detector.py`.
- **Usage:** Call to acquire the standard `dict[str, list[str | re.Pattern]]` of morphological patterns.
- **Example:**
  ```python
  from utils.language_utils import get_german_morphological_patterns

  patterns = get_german_morphological_patterns()
  prefixes = patterns.get("philosophical_prefixes", [])
  print(f"Loaded {len(prefixes)} philosophical prefixes.")
  ```

## OCR Result Processing
**Location:** `services/ocr_utils.py`

### `parse_ocr_result(result: dict[str, Any]) -> list[list[TextBlock]]`
- **Description:** Standardizes the extraction of text, bounding boxes, confidence scores, and font data from OCR service JSON payloads into domain-specific `TextBlock` and `LayoutContext` objects.
- **Previous Duplication:** This complex `_parse_ocr_result` method was duplicated across `services/async_document_processor.py` and `services/main_document_processor.py`.
- **Usage:** Pass the raw OCR dictionary to receive a structured list of text blocks per page.
- **Example:**
  ```python
  from services.ocr_utils import parse_ocr_result

  # Minimal sample payload
  raw_ocr = {"pages": [{"blocks": [{"lines": [{"words": [{"text": "Hello", "bbox": [0,0,10,10]}]}]}]}]}
  pages_blocks = parse_ocr_result(raw_ocr)
  for page_num, blocks in enumerate(pages_blocks):
      print(f"Page {page_num}: Processed {len(blocks)} blocks.")
  ```

## Database & Session State Management
**Location:** `core/dynamic_choice_engine.py`

### `create_session_for_document(manager, document_name, user_id=None, source_lang="de", target_lang="en")`
- **Description:** A unified API for initializing a document processing `ChoiceSession` regardless of whether the standard `UserChoiceManager` or the `OptimizedUserChoiceManager` is used.
  - `manager` (`UserChoiceManager | OptimizedUserChoiceManager`): The session manager instance handling state.
  - `document_name` (`str`): The name of the document being processed.
  - `user_id` (`Optional[str]`): An optional identifier for the user.
  - `source_lang` (`str`): The source language code (default: "de").
  - `target_lang` (`str`): The target language code (default: "en").
  - **Returns:** A `ChoiceSession` object tracking the state and options.
- **Previous Duplication:** Session initialization logic was directly coded within `services/philosophy_enhanced_document_processor.py`.
- **Usage:** Used primarily before triggering document-wide neologism detection pipelines to ensure state tracking.
- **Example:**
  ```python
  from core.dynamic_choice_engine import UserChoiceManager, create_session_for_document
  
  manager = UserChoiceManager()
  session = create_session_for_document(
      manager=manager,
      document_name="Kant_Critique.pdf",
      user_id="user_123"
  )
  print(f"Active session ID: {session.session_id}")
  ```
