"""Language detection service.

This module provides simple language detection utilities intended for
PDF-only workflows. It optionally uses ``langdetect`` when available
and falls back to lightweight heuristics otherwise. The utilities are
designed to fail closed (returning "Unknown") on errors rather than
raising exceptions to callers.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, TypedDict

# Optional dependency detection without importing at module import time
LANGDETECT_AVAILABLE: bool = importlib.util.find_spec("langdetect") is not None

# Module-level lock for thread-safe langdetect initialization
_LANGDETECT_LOCK = threading.Lock()

logger: logging.Logger = logging.getLogger(__name__)

# Accepted truthy values for environment flags (normalized to lower-case)
TRUE_VALUES: frozenset[str] = frozenset({"true", "1", "yes", "on", "y", "t"})


def env_flag(name: str, default: bool = False) -> bool:
    """Check if an environment variable flag is set to a truthy value.

    Reads the environment variable, normalizes it by stripping whitespace and converting to lowercase,
    then checks if it matches any of the accepted truthy values. Returns the default value
    if the environment variable is not set or is empty after normalization.

    Args:
        name: Environment variable name to check
        default: Default value to return if the environment variable is not set or empty

    Returns:
        bool: True if the environment variable contains a truthy value, False if falsy,
              or the default value if the variable is not set
    """
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in TRUE_VALUES


LANGUAGE_MAP: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
}


class LanguagePattern(TypedDict):
    """Heuristic language pattern configuration for a language.

    Keys:
        words: Common function words for the language (lowercase).
        chars: Distinctive characters/diacritics typical for the language.
        word_weight: Weight applied to word matches in scoring.
        char_weight: Weight applied to character matches in scoring.
    """

    words: list[str]
    chars: list[str]
    word_weight: float
    char_weight: float


LANGUAGE_PATTERNS: dict[str, LanguagePattern] = {
    "German": {
        "words": [
            "der",
            "die",
            "das",
            "und",
            "ist",
            "ein",
            "eine",
            "mit",
            "von",
            "zu",
        ],
        "chars": ["ä", "ö", "ü", "ß"],
        "word_weight": 1.0,
        "char_weight": 2.0,
    },
    "English": {
        "words": [
            "the",
            "and",
            "is",
            "a",
            "an",
            "with",
            "of",
            "to",
            "in",
            "for",
        ],
        "chars": [],
        "word_weight": 1.0,
        "char_weight": 0.0,
    },
    "Spanish": {
        "words": [
            "el",
            "la",
            "y",
            "es",
            "un",
            "una",
            "con",
            "de",
            "en",
            "para",
        ],
        "chars": ["ñ", "á", "é", "í", "ó", "ú"],
        "word_weight": 1.0,
        "char_weight": 2.0,
    },
    "French": {
        "words": [
            "le",
            "la",
            "et",
            "est",
            "un",
            "une",
            "avec",
            "de",
            "en",
            "pour",
        ],
        "chars": ["à", "é", "è", "ê", "ç", "ô"],
        "word_weight": 1.0,
        "char_weight": 2.0,
    },
}


class LanguageDetector:
    """Detects language of document content."""

    def __init__(self) -> None:
        """Initialize detector with module-level language mappings."""
        self.language_map: dict[str, str] = LANGUAGE_MAP
        # Caches for optional langdetect dependency
        self._langdetect_initialized: bool = False
        self._langdetect_mod: Optional[Any] = None
        self._langdetect_exception: Optional[Any] = None
        self._detect_func: Optional[Any] = None

    def _ensure_langdetect(self) -> None:
        """Lazily import and cache langdetect modules/functions.

        This avoids repeated dynamic imports on every call while
        remaining resilient when the optional dependency is missing.
        Uses double-checked locking to prevent race conditions in multi-threaded environments.
        """
        # First check without lock for performance
        if self._langdetect_initialized:
            return

        # Use lock to prevent race conditions during initialization
        with _LANGDETECT_LOCK:
            # Second check inside lock (double-checked locking pattern)
            if self._langdetect_initialized:
                return

            # Set initialized if langdetect is confirmed unavailable
            if not LANGDETECT_AVAILABLE:
                self._langdetect_initialized = True
                return

            try:
                mod: Any = importlib.import_module("langdetect")
                fallback_exc: type = type(
                    "LocalLangDetectException", (RuntimeError,), {}
                )
                # Get LangDetectException from the top-level module instead of importing submodule
                exc: Any = getattr(mod, "LangDetectException", fallback_exc)
                detect_func: Optional[Any] = getattr(mod, "detect", None)
                self._langdetect_mod = mod
                self._langdetect_exception = exc
                self._detect_func = detect_func
                # Only mark as initialized after successful import and caching
                self._langdetect_initialized = True
            except (ModuleNotFoundError, ImportError, AttributeError) as err:
                logger.debug("langdetect import failed: %s", err)
                # Don't set initialized flag on import errors to allow retry on transient failures

    def detect_language(
        self,
        file_path: str,
        text_extractor: Optional[Callable[[str], str]] = None,
        pre_extracted_text: Optional[str] = None,
    ) -> str:
        """Detect the language of a document from its file path.

        Extracts sample text from the document and uses language
        detection algorithms to identify the language. Project scope is
        PDF-only.

        Args:
            file_path: Path to the document file to analyze. Supported
                format is ``.pdf``.
            text_extractor: Optional callable that takes a file path and returns
                extracted text. If provided, this overrides the default extraction.
            pre_extracted_text: Optional pre-extracted text to use instead of
                extracting from the file. Useful when text is already available
                from upstream OCR processing.

        Returns:
            str: Detected language name (e.g., "German", "English") or
            "Unknown" if the language cannot be determined or if an
            error occurs. Language codes are mapped to full language
            names using the internal ``language_map`` dictionary.

        Note:
            This method uses the langdetect library if available,
            otherwise falls back to simple heuristic-based detection.
            Errors are handled internally and result in "Unknown"
            rather than propagating to the caller.
        """
        # Use pre-extracted text if provided, otherwise extract from file
        if pre_extracted_text is not None:
            sample_text = pre_extracted_text
        elif text_extractor is not None:
            try:
                sample_text = text_extractor(file_path)
            except Exception as e:
                logger.warning(
                    "Text extractor failed for %s: %s. Falling back to sample text extraction",
                    file_path,
                    str(e),
                    exc_info=True,
                )
                try:
                    sample_text = self._extract_sample_text(file_path)
                except Exception as fallback_e:
                    logger.error(
                        "Both text extractor and fallback failed for %s: %s",
                        file_path,
                        str(fallback_e),
                        exc_info=True,
                    )
                    sample_text = None
        else:
            sample_text = self._extract_sample_text(file_path)

        # Check for OCR environment flag to lower threshold when text is provided
        ocr_text_available = env_flag("OCR_TEXT_AVAILABLE")

        # Adjust minimum length based on whether OCR text is expected
        # OCR text tends to be cleaner; set langdetect thresholds accordingly
        min_length = 20 if ocr_text_available else 50

        if not sample_text:
            return "Unknown"
        text_len = len(sample_text.strip())
        if text_len < 10:
            return "Unknown"

        # If we have enough text for langdetect, try it; else use heuristics
        if LANGDETECT_AVAILABLE and text_len >= min_length:
            self._ensure_langdetect()
            if self._detect_func is not None and self._langdetect_exception is not None:
                # At this point, sample_text is guaranteed to be not None and have length >= 10
                assert (
                    sample_text is not None
                ), "sample_text should not be None at this point"
                try:
                    detected_code: str = self._detect_func(sample_text)
                    mapped_lang = self.language_map.get(detected_code, "Unknown")
                    if mapped_lang == "Unknown":
                        # Return uppercase language code for unmapped codes instead of "Unknown"
                        logger.debug(
                            "Unmapped language code '%s' detected, returning uppercase code",
                            detected_code,
                        )
                        return detected_code.upper()
                    return mapped_lang
                except (self._langdetect_exception, ValueError) as e:
                    logger.warning(
                        "Language detection error: %s. Falling back to heuristic detection",
                        e,
                        exc_info=True,
                    )
                    # Fall back to the same heuristic detection used elsewhere in the module
                    return self._simple_language_detection(sample_text)

        # Fallback to simple heuristics for shorter texts (≥10 chars)
        return self._simple_language_detection(sample_text)

    def _extract_sample_text(self, file_path: str) -> str:
        """Extract sample text for language detection from PDF files.

        The project is PDF-only. For ``.pdf`` files, language detection
        relies on OCR upstream. This method checks for configured OCR
        output paths and environment variables to find pre-extracted text.

        Args:
            file_path: Path to the document file to extract text from

        Returns:
            str: Extracted text sample or empty string if unsupported or if
            an error occurs during text extraction
        """
        try:
            file_ext: str = Path(file_path).suffix.lower()

            if file_ext == ".pdf":
                # Check for OCR output path configuration
                ocr_output_dir = os.getenv("OCR_OUTPUT_DIR")
                if ocr_output_dir:
                    # Look for corresponding text file in OCR output directory
                    pdf_name = Path(file_path).stem
                    text_file_path = Path(ocr_output_dir) / f"{pdf_name}.txt"
                    if text_file_path.exists():
                        try:
                            with open(text_file_path, encoding="utf-8") as f:
                                text = f.read().strip()
                                if text:
                                    logger.debug(
                                        "Found OCR text for %s in %s",
                                        os.path.basename(file_path),
                                        text_file_path,
                                    )
                                    return text
                        except (OSError, UnicodeDecodeError) as e:
                            logger.warning(
                                "Failed to read OCR text file %s: %s",
                                text_file_path,
                                e,
                            )

                # Check for OCR text available flag
                if env_flag("OCR_TEXT_AVAILABLE"):
                    logger.debug(
                        "OCR_TEXT_AVAILABLE flag set but no text found for %s",
                        os.path.basename(file_path),
                    )
                else:
                    # OCR-first pipeline: PDF text must be pre-extracted upstream
                    # Provide explicit guidance for operators on where to look
                    logger.debug(
                        (
                            "PDF text not available locally; expecting upstream OCR. "
                            "Verify OCR service/pipeline "
                            "(env: OCR_SERVICE/OCR_PIPELINE) "
                            "is configured and producing text for: %s"
                        ),
                        os.path.basename(file_path),
                    )
                return ""

            return ""

        except (OSError, UnicodeDecodeError) as e:
            logger.error("Text extraction error: %s", e)
            return ""

    def _simple_language_detection(self, text: str) -> str:
        """Simple language detection based on character patterns.

        Args:
            text: Input text to analyze

        Returns:
            str: Detected language or 'Unknown' if not confident
        """
        # Early return for insufficient input
        if not text or len(text.strip()) < 10:
            return "Unknown"

        text = text.lower()
        words: list[str] = text.split()
        word_count: int = len(words)

        if word_count == 0:
            return "Unknown"

        # Use precomputed language patterns defined at module scope
        language_patterns: dict[str, LanguagePattern] = LANGUAGE_PATTERNS

        # Compute once to speed up membership checks
        words_set: set[str] = set(words)

        # Precompute denominators to avoid redundant calculations
        denom: float = float(word_count)
        char_denom: float = float(len(text.strip()))

        # Calculate normalized scores
        scores: dict[str, float] = {}
        for lang, patterns in language_patterns.items():
            # Count matching words and characters
            pattern_words: list[str] = patterns["words"]
            pattern_chars: list[str] = patterns["chars"]
            word_weight: float = patterns["word_weight"]
            char_weight: float = patterns["char_weight"]
            word_matches: int = sum(1 for token in pattern_words if token in words_set)
            char_matches: int = sum(1 for ch in pattern_chars if ch in text)

            # Calculate normalized scores (word_score per 100 words, char_score per 100 characters)
            word_score: float = (word_matches * word_weight) / denom * 100
            char_score: float = (char_matches * char_weight) / char_denom * 100

            # Combine scores with weights
            scores[lang] = (word_score * 0.7) + (char_score * 0.3)

        # Get language with highest score if above threshold
        if scores:
            best_lang: str = max(scores.items(), key=lambda kv: kv[1])[0]
            # Only return result if score is above minimum threshold
            # At least 0.5 matches per 100 words
            if scores[best_lang] > 0.5:
                return best_lang

        return "Unknown"

    def detect_language_from_text(self, text: str) -> str:
        """Detect language from provided text using a two-path approach.

        This function validates the input, then uses the best available
        detection method.

        1. Validation: Require at least 10 non-whitespace characters,
           otherwise return "Unknown" without attempting detection.
        2. Detection: Prefer ``langdetect`` if installed; fall back to a
           simple heuristic based on common words and characters.

        Args:
            text: Text to analyze for language detection. Should contain
                  at least 10 characters for reliable detection.

        Returns:
            str: Detected language name (e.g., "German", "English") or
            "Unknown" if the language cannot be determined.

        Note:
            This function is resilient to missing dependencies and errors.
        """
        if not text or len(text.strip()) < 10:
            return "Unknown"

        if LANGDETECT_AVAILABLE:
            self._ensure_langdetect()
            detect_func: Optional[Any] = self._detect_func
            lang_exc: Optional[Any] = self._langdetect_exception
            if detect_func is None or lang_exc is None:
                return self._simple_language_detection(text)
            try:
                detected_code: str = detect_func(text)
            except (lang_exc, ValueError) as e:  # type: ignore[misc]
                logger.warning("Language detection error: %s", e)
                return "Unknown"
            mapped_lang = self.language_map.get(detected_code, detected_code.upper())
            if mapped_lang == detected_code.upper():
                logger.debug(
                    "Unmapped language code '%s', falling back to uppercase '%s'",
                    detected_code,
                    mapped_lang,
                )
            return mapped_lang

        # Fallback to simple heuristics
        return self._simple_language_detection(text)

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages.

        Returns:
            List[str]: Human-readable names (e.g., ["English", "German"]).
        """
        return list(self.language_map.values())
