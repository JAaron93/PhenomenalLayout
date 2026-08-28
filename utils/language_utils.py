"""Utility functions for language detection, text extraction, and linguistic compound analysis."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SUPPORTED_LANGUAGES",
    "extract_text_sample_for_language_detection",
    "get_german_morphological_patterns",
    "is_german_compound_word",
]

_PHILOSOPHICAL_ENDINGS: tuple[str, ...] = (
    "bewusstsein",
    "wirklichkeit",
    "erkenntnis",
    "wahrnehmung",
    "philosophie",
    "theorie",
    "anschauung",
    "thematik",
)

_SINGLE_ROOT_NOUNS: frozenset[str] = frozenset({
    "bewusstsein",
    "wirklichkeit",
    "erkenntnis",
    "wahrnehmung",
    "philosophie",
    "wissenschaft",
    "gesellschaft",
    "dasein",
    "existenz",
    "phänomenologie",
    "phanomenologie",
    "intentionalität",
    "intentionalitat",
    "menschlich",
    "wesentlich",
    "eigentlich",
    "natürlich",
    "körperlich",
    "sprachlich",
    "zeitlich",
    "alltäglich",
})

_PHILOSOPHICAL_PREFIX_RE: re.Pattern[str] = re.compile(
    r"^(?:welt|lebens|seins|geist|seele)\w{4,}$", re.IGNORECASE
)
_STANDARD_LINKING_RE: re.Pattern[str] = re.compile(
    r"^\w{4,}(?:s|en|er)\w{4,}$", re.IGNORECASE
)
_COMMON_DERIVATIONAL_SUFFIXES_RE: re.Pattern[str] = re.compile(
    r"^\w{3,}(?:lich|isch|haft|ig|bar|los)$", re.IGNORECASE
)


def is_german_compound_word(word: str) -> bool:
    """Identify if a word is likely a German philosophical compound noun.

    Employs module-level precompiled regular expressions, minimum-length
    filters, uppercase checks, and set lookups to detect compound structures
    with zero per-call regex compilation overhead (O(len(word)) time, O(1) space).

    Args:
        word: Token string to analyze.

    Returns:
        bool: True if the word exhibits German compound structure, False otherwise.
    """
    if not isinstance(word, str) or len(word) < 8:
        return False

    word_lower = word.lower()

    # Exclude common single root words that might otherwise match suffixes
    if word_lower in _SINGLE_ROOT_NOUNS:
        return False

    # Check for multiple capital letters (German noun compounds / CamelCase)
    capital_count = sum(1 for c in word if c.isupper())
    if capital_count >= 2:
        return True

    # Check for philosophical compounds (suffix ending with prefix >= 4 chars)
    for ending in _PHILOSOPHICAL_ENDINGS:
        if word_lower.endswith(ending) and len(word_lower) > len(ending):
            prefix = word_lower[: -len(ending)]
            if len(prefix) >= 4:
                return True

    # Check philosophical prefix compounds (e.g. Lebenswelt, Seinsstruktur)
    if _PHILOSOPHICAL_PREFIX_RE.match(word_lower):
        return True

    # Reject standard adjectival/adverbial derivational suffixes (e.g. menschlich, wesentlich)
    if _COMMON_DERIVATIONAL_SUFFIXES_RE.match(word_lower):
        return False

    # Check standard linking elements (e.g. Handlungsstruktur, Wissensbereich)
    return bool(_STANDARD_LINKING_RE.match(word_lower))


DEFAULT_SUPPORTED_LANGUAGES = (
    "English",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Russian",
    "Chinese",
    "Japanese",
    "Korean",
    "Arabic",
    "Hindi",
    "Dutch",
    "Swedish",
    "Norwegian",
)

def get_german_morphological_patterns() -> dict[str, list[str]]:
    """Return German morphological patterns for compound analysis.

    The patterns are predefined constants rather than loaded from an external
    source, providing consistent morphological analysis for German text processing.
    """
    return {
        "compound_linking": ["s", "n", "es", "en", "er", "e", "ns", "ts"],
        "philosophical_prefixes": [
            "vor",
            "nach",
            "über",
            "unter",
            "zwischen",
            "gegen",
            "mit",
            "ur",
            "proto",
            "meta",
            "anti",
            "pseudo",
            "neo",
            "para",
        ],
        "abstract_suffixes": [
            "heit",
            "keit",
            "ung",
            "schaft",
            "tum",
            "nis",
            "sal",
            "ismus",
            "ität",
            "ation",
            "logie",
            "sophie",
        ],
        "philosophical_endings": [
            "bewusstsein",
            "wirklichkeit",
            "erkenntnis",
            "wahrnehmung",
            "philosophie",
            "theorie",
            "anschauung",
            "thematik",
        ],
        "compound_patterns": [
            r"\w+(?:s|n|es|en|er|e|ns|ts)\w+",
            r"\w+(?:bewusstsein|wirklichkeit|erkenntnis|wahrnehmung)",
            r"(?:welt|lebens|seins|geist|seele)\w+",
        ],
    }

def extract_text_sample_for_language_detection(content: dict[str, Any]) -> str:
    """Extract a text sample from document content for language detection.

    This function handles various content types and provides a consistent
    way to extract meaningful text for language detection purposes.

    Args:
        content: Document content dictionary with 'type' and content data

    Returns:
        str: Text sample suitable for language detection,
             or "No text content available" if no text found
    """
    try:
        if content["type"] == "pdf_advanced":
            # Validate text_by_page exists and is a dictionary
            text_by_page = content.get("text_by_page")
            if not text_by_page or not isinstance(text_by_page, dict):
                logger.warning("text_by_page missing or invalid in PDF content")
                return "No text content available"

            # Try to get text from first page
            first_page_texts = text_by_page.get(0, [])

            # Validate that first_page_texts is iterable
            if not isinstance(first_page_texts, (list, tuple)):
                logger.warning("Invalid first page texts structure")
                first_page_texts = []

            # Filter out empty or whitespace-only texts
            meaningful_texts = [
                text
                for text in first_page_texts
                if isinstance(text, str) and text.strip()
            ]

            if meaningful_texts:
                # Use up to first 5 meaningful text elements
                return " ".join(meaningful_texts[:5])

            # Fallback: try other pages if first page is empty
            sample_text = ""

            # Safely get and sort page keys
            try:
                page_keys = list(text_by_page.keys())
                # Ensure keys are sortable (convert to int if possible)
                sortable_keys = []
                for key in page_keys:
                    try:
                        sortable_keys.append((int(key), key))
                    except (ValueError, TypeError):
                        # If key can't be converted to int,
                        # use string comparison
                        sortable_keys.append((float("inf"), key))

                # Sort by numeric value first, then by original key
                sortable_keys.sort()
                sorted_page_keys = [key for _, key in sortable_keys[:3]]

                for page_num in sorted_page_keys:
                    page_texts = text_by_page.get(page_num, [])

                    # Validate page_texts is iterable
                    if not isinstance(page_texts, (list, tuple)):
                        continue

                    meaningful_page_texts = [
                        text
                        for text in page_texts
                        if isinstance(text, str) and text.strip()
                    ]

                    if meaningful_page_texts:
                        sample_text = " ".join(meaningful_page_texts[:5])
                        break

            except Exception as e:
                logger.warning(
                    f"Error processing page keys for language detection: {e}"
                )

            # If still no text found, use a minimal sample
            if not sample_text:
                logger.warning("No meaningful text found for language detection in PDF")
                return "No text content available"

            return sample_text

        else:
            # For non-PDF files (docx, txt, etc.)
            sample_text = content.get("text_content", "")[:1000]

            # Ensure sample_text is not empty
            if not sample_text.strip():
                logger.warning(
                    f"Empty text content for language detection in "
                    f"{content['type']} file"
                )
                return "No text content available"

            return sample_text

    except Exception as e:
        logger.error(f"Error extracting text sample: {e}")
        return "No text content available"
