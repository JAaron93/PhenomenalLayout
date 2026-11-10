"""Tests for language detection service (services/language_detector.py)."""

from __future__ import annotations

import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import services.language_detector as language_detector
from services.language_detector import LanguageDetector, env_flag

GERMAN_TEXT = (
    "Der Begriff der Dialektik ist bei Hegel von zentraler Bedeutung "
    "für das Verständnis der Philosophie."
)
ENGLISH_TEXT = (
    "The concept of the thing-in-itself is central to the philosophy "
    "of Kant and his successors."
)
FRENCH_TEXT = (
    "L'être et le néant sont des concepts essentiels de la philosophie "
    "existentialiste française du vingtième siècle."
)


def make_detector(
    detect_func: Callable[[str], str] | None,
    exception: type[Exception] = RuntimeError,
) -> LanguageDetector:
    detector = LanguageDetector()
    detector._langdetect_initialized = True
    detector._detect_func = detect_func
    detector._langdetect_exception = exception
    return detector


@pytest.fixture()
def heuristic_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", False)


class TestEnvFlag:
    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "y", "t", "TRUE", " Yes "])
    def test_truthy_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PROBE_FLAG", value)
        assert env_flag("PROBE_FLAG") is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "n", "maybe"])
    def test_falsy_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PROBE_FLAG", value)
        assert env_flag("PROBE_FLAG") is False

    def test_unset_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROBE_FLAG", raising=False)
        assert env_flag("PROBE_FLAG") is False
        assert env_flag("PROBE_FLAG", default=True) is True

    def test_empty_value_returns_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROBE_FLAG", "   ")
        assert env_flag("PROBE_FLAG") is False
        assert env_flag("PROBE_FLAG", default=True) is True


class TestDetectLanguageHeuristics:
    @pytest.mark.usefixtures("heuristic_only")
    def test_pre_extracted_german_text(self) -> None:
        detector = LanguageDetector()
        assert detector.detect_language("book.pdf", pre_extracted_text=GERMAN_TEXT) == "German"

    @pytest.mark.usefixtures("heuristic_only")
    def test_pre_extracted_english_text(self) -> None:
        detector = LanguageDetector()
        assert detector.detect_language("book.pdf", pre_extracted_text=ENGLISH_TEXT) == "English"

    @pytest.mark.usefixtures("heuristic_only")
    def test_pre_extracted_french_text(self) -> None:
        detector = LanguageDetector()
        assert detector.detect_language("book.pdf", pre_extracted_text=FRENCH_TEXT) == "French"

    @pytest.mark.usefixtures("heuristic_only")
    def test_empty_pre_extracted_text_returns_unknown(self) -> None:
        detector = LanguageDetector()
        assert detector.detect_language("book.pdf", pre_extracted_text="") == "Unknown"

    @pytest.mark.usefixtures("heuristic_only")
    def test_very_short_text_returns_unknown(self) -> None:
        detector = LanguageDetector()
        assert detector.detect_language("book.pdf", pre_extracted_text="kurz") == "Unknown"

    @pytest.mark.usefixtures("heuristic_only")
    def test_extractor_callable_is_used(self) -> None:
        detector = LanguageDetector()
        result = detector.detect_language(
            "book.pdf", text_extractor=lambda _path: GERMAN_TEXT
        )
        assert result == "German"

    @pytest.mark.usefixtures("heuristic_only")
    def test_extractor_failure_falls_back_to_sample_extraction(self) -> None:
        def broken_extractor(_path: str) -> str:
            raise RuntimeError("extractor down")

        detector = LanguageDetector()
        result = detector.detect_language("book.pdf", text_extractor=broken_extractor)
        assert result == "Unknown"


class TestOcrMinLengthBoundary:
    GERMANISH_OPAQUE = "zzz qqq vvv kkk jjj ppp www nnn m"

    def test_ocr_flag_lowers_min_length_for_langdetect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        monkeypatch.setenv("OCR_TEXT_AVAILABLE", "true")
        detector = make_detector(lambda _text: "de")
        assert detector.detect_language(
            "book.pdf", pre_extracted_text=self.GERMANISH_OPAQUE
        ) == "German"

    def test_without_ocr_flag_short_text_skips_langdetect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        monkeypatch.delenv("OCR_TEXT_AVAILABLE", raising=False)
        detector = make_detector(lambda _text: "de")
        assert detector.detect_language(
            "book.pdf", pre_extracted_text=self.GERMANISH_OPAQUE
        ) == "Unknown"


class TestLangdetectPath:
    def test_mapped_code_returns_language_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        detector = make_detector(lambda _text: "fr")
        assert detector.detect_language(
            "book.pdf", pre_extracted_text=ENGLISH_TEXT
        ) == "French"

    def test_unmapped_code_returns_uppercase_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        detector = make_detector(lambda _text: "zz")
        result = detector.detect_language(
            "book.pdf", pre_extracted_text=ENGLISH_TEXT
        )
        assert result == "ZZ"

    def test_langdetect_exception_falls_back_to_heuristic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)

        def explode(_text: str) -> str:
            raise RuntimeError("langdetect failed")

        detector = make_detector(explode)
        assert detector.detect_language(
            "book.pdf", pre_extracted_text=GERMAN_TEXT
        ) == "German"

    def test_value_error_falls_back_to_heuristic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)

        def explode(_text: str) -> str:
            raise ValueError("no features")

        detector = make_detector(explode)
        assert detector.detect_language(
            "book.pdf", pre_extracted_text=GERMAN_TEXT
        ) == "German"


class TestExtractSampleText:
    def test_non_pdf_paths_yield_empty_string(self) -> None:
        assert LanguageDetector()._extract_sample_text("notes.txt") == ""

    def test_pdf_without_ocr_dir_yields_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OCR_OUTPUT_DIR", raising=False)
        assert LanguageDetector()._extract_sample_text("book.pdf") == ""

    def test_pdf_with_matching_ocr_text_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ocr_dir = tmp_path / "ocr"
        ocr_dir.mkdir()
        (ocr_dir / "book.txt").write_text(GERMAN_TEXT, encoding="utf-8")
        monkeypatch.setenv("OCR_OUTPUT_DIR", str(ocr_dir))
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert LanguageDetector()._extract_sample_text(str(pdf)) == GERMAN_TEXT

    def test_pdf_with_missing_ocr_text_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ocr_dir = tmp_path / "ocr"
        ocr_dir.mkdir()
        monkeypatch.setenv("OCR_OUTPUT_DIR", str(ocr_dir))
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert LanguageDetector()._extract_sample_text(str(pdf)) == ""

    def test_unreadable_ocr_text_file_is_tolerated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ocr_dir = tmp_path / "ocr"
        (ocr_dir / "book.txt").mkdir(parents=True)
        monkeypatch.setenv("OCR_OUTPUT_DIR", str(ocr_dir))
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert LanguageDetector()._extract_sample_text(str(pdf)) == ""

    def test_ocr_flag_without_text_logs_and_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("OCR_OUTPUT_DIR", raising=False)
        monkeypatch.setenv("OCR_TEXT_AVAILABLE", "true")
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert LanguageDetector()._extract_sample_text(str(pdf)) == ""


class TestSimpleLanguageDetection:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (GERMAN_TEXT, "German"),
            (ENGLISH_TEXT, "English"),
            (FRENCH_TEXT, "French"),
        ],
    )
    def test_pattern_based_detection(self, text: str, expected: str) -> None:
        assert LanguageDetector()._simple_language_detection(text) == expected

    def test_short_text_returns_unknown(self) -> None:
        assert LanguageDetector()._simple_language_detection("kurz") == "Unknown"

    def test_whitespace_only_returns_unknown(self) -> None:
        assert LanguageDetector()._simple_language_detection("   \n\t ") == "Unknown"

    def test_no_pattern_matches_returns_unknown(self) -> None:
        text = "qq ww ee rr tt yy uu ii oo pp aa ss dd ff gg hh jj kk ll"
        assert LanguageDetector()._simple_language_detection(text) == "Unknown"


class TestDetectLanguageFromText:
    @pytest.mark.usefixtures("heuristic_only")
    def test_short_text_returns_unknown(self) -> None:
        assert LanguageDetector().detect_language_from_text("kurz") == "Unknown"

    @pytest.mark.usefixtures("heuristic_only")
    def test_heuristic_fallback_when_langdetect_unavailable(self) -> None:
        assert LanguageDetector().detect_language_from_text(GERMAN_TEXT) == "German"

    def test_uninitialized_langdetect_uses_heuristic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        detector = make_detector(None, exception=RuntimeError)
        assert detector.detect_language_from_text(GERMAN_TEXT) == "German"

    def test_mapped_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        detector = make_detector(lambda _text: "de")
        assert detector.detect_language_from_text(GERMAN_TEXT) == "German"

    def test_unmapped_code_returns_uppercase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        detector = make_detector(lambda _text: "zz")
        assert detector.detect_language_from_text(ENGLISH_TEXT) == "ZZ"

    def test_detection_error_returns_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)

        def explode(_text: str) -> str:
            raise RuntimeError("langdetect failed")

        detector = make_detector(explode)
        assert detector.detect_language_from_text(GERMAN_TEXT) == "Unknown"


class TestLangdetectInitialization:
    def test_unavailable_dependency_marks_initialized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", False)
        detector = LanguageDetector()
        detector._ensure_langdetect()
        assert detector._langdetect_initialized is True
        assert detector._detect_func is None

    def test_available_dependency_imports_and_caches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)
        fake_module = types.SimpleNamespace(
            LangDetectException=RuntimeError, detect=lambda _text: "de"
        )
        fake_importlib = types.SimpleNamespace(
            import_module=lambda _name: fake_module
        )
        monkeypatch.setattr(language_detector, "importlib", fake_importlib)
        detector = LanguageDetector()
        detector._ensure_langdetect()
        assert detector._langdetect_initialized is True
        assert detector._langdetect_mod is fake_module
        assert detector._langdetect_exception is RuntimeError
        assert detector._detect_func is not None

    def test_import_failure_allows_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", True)

        def raise_module_not_found(name: str) -> Any:
            raise ModuleNotFoundError(name)

        fake_importlib = types.SimpleNamespace(import_module=raise_module_not_found)
        monkeypatch.setattr(language_detector, "importlib", fake_importlib)
        detector = LanguageDetector()
        detector._ensure_langdetect()
        assert detector._langdetect_initialized is False

    def test_double_checked_lock_skips_second_init(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(language_detector, "LANGDETECT_AVAILABLE", False)
        detector = LanguageDetector()
        detector._langdetect_initialized = True
        detector._init_langdetect_locked()
        assert detector._langdetect_initialized is True


class TestSupportedLanguages:
    def test_lists_all_mapped_languages(self) -> None:
        languages = LanguageDetector().get_supported_languages()
        assert len(languages) == 15
        assert "German" in languages
        assert "English" in languages
