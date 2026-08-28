"""Unit tests for consolidated foundation helper modules (Track 1).

Tests coverage for:
- utils.gcp_helpers (GCS URI parsing, blob deletion, resource naming, retry)
- utils.tsv_utils (RFC 4180 escaping and TSV byte formatting)
- utils.pdf_stream (Deterministic stream context manager)
- utils.file_handler (Atomic JSON and text writing)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core import exceptions as gcp_exceptions

# ===========================================================================
# 1. Tests for utils.gcp_helpers
# ===========================================================================


class TestGCPHelpers:
    """Test suite for utils/gcp_helpers.py."""

    def test_parse_gcs_uri_valid(self) -> None:
        from utils.gcp_helpers import parse_gcs_uri

        bucket, blob = parse_gcs_uri("gs://my-bucket/inputs/book.pdf")
        assert bucket == "my-bucket"
        assert blob == "inputs/book.pdf"

        bucket2, blob2 = parse_gcs_uri("gs://simple-bucket/file.tsv")
        assert bucket2 == "simple-bucket"
        assert blob2 == "file.tsv"

    def test_parse_gcs_uri_invalid_scheme(self) -> None:
        from utils.gcp_helpers import parse_gcs_uri

        with pytest.raises(ValueError, match="Invalid GCS URI"):
            parse_gcs_uri("https://storage.googleapis.com/b/file.pdf")

        with pytest.raises(ValueError, match="Invalid GCS URI"):
            parse_gcs_uri("/local/path/file.pdf")

    def test_parse_gcs_uri_missing_blob(self) -> None:
        from utils.gcp_helpers import parse_gcs_uri

        with pytest.raises(ValueError, match="could not extract blob path"):
            parse_gcs_uri("gs://my-bucket/")

        with pytest.raises(ValueError, match="could not extract blob path"):
            parse_gcs_uri("gs://my-bucket")

    def test_delete_gcs_blob_success(self) -> None:
        from utils.gcp_helpers import delete_gcs_blob

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = delete_gcs_blob(mock_storage, "gs://my-bucket/temp/test.tsv")
        assert result is True
        mock_storage.bucket.assert_called_once_with("my-bucket")
        mock_bucket.blob.assert_called_once_with("temp/test.tsv")
        mock_blob.delete.assert_called_once()

    def test_delete_gcs_blob_not_found(self) -> None:
        from utils.gcp_helpers import delete_gcs_blob

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.delete.side_effect = gcp_exceptions.NotFound("Blob not found")
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        # Idempotent suppression of NotFound
        result = delete_gcs_blob(mock_storage, "gs://my-bucket/already_deleted.tsv")
        assert result is True

    def test_delete_gcs_blob_error(self) -> None:
        from utils.gcp_helpers import delete_gcs_blob

        mock_storage = MagicMock()
        mock_storage.bucket.side_effect = RuntimeError("GCS connection failed")

        result = delete_gcs_blob(mock_storage, "gs://my-bucket/error.tsv")
        assert result is False

    def test_format_gcp_glossary_name(self) -> None:
        from utils.gcp_helpers import format_gcp_glossary_name

        name = format_gcp_glossary_name("my-prj", "us-central1", "glossary-123")
        assert name == "projects/my-prj/locations/us-central1/glossaries/glossary-123"

        # Normalizes already prefixed projects
        name_prefixed = format_gcp_glossary_name(
            "projects/my-prj", "us-central1", "glossary-123"
        )
        assert (
            name_prefixed
            == "projects/my-prj/locations/us-central1/glossaries/glossary-123"
        )

    def test_is_transient_gcp_error(self) -> None:
        from utils.gcp_helpers import is_transient_gcp_error

        # GoogleAPICallError with transient status
        err_429 = gcp_exceptions.ResourceExhausted("Quota exceeded")
        assert is_transient_gcp_error(err_429) is True

        err_503 = gcp_exceptions.ServiceUnavailable("Service unavailable")
        assert is_transient_gcp_error(err_503) is True

        err_404 = gcp_exceptions.NotFound("Not found")
        assert is_transient_gcp_error(err_404) is False

        err_403 = gcp_exceptions.PermissionDenied("Forbidden")
        assert is_transient_gcp_error(err_403) is False

    def test_retry_gcp_call_success_first_try(self) -> None:
        from utils.gcp_helpers import retry_gcp_call

        mock_fn = MagicMock(return_value="success")
        res = retry_gcp_call(mock_fn, "arg1", kw="val")
        assert res == "success"
        assert mock_fn.call_count == 1

    def test_retry_gcp_call_transient_retry_and_succeed(self) -> None:
        from utils.gcp_helpers import retry_gcp_call

        mock_fn = MagicMock(
            side_effect=[
                gcp_exceptions.ResourceExhausted("Rate limit"),
                gcp_exceptions.ServiceUnavailable("Down"),
                "recovered",
            ]
        )
        res = retry_gcp_call(mock_fn, max_retries=3, base_delay=0.01, max_delay=0.05)
        assert res == "recovered"
        assert mock_fn.call_count == 3

    def test_retry_gcp_call_non_transient_fails_immediately(self) -> None:
        from utils.gcp_helpers import retry_gcp_call

        mock_fn = MagicMock(side_effect=gcp_exceptions.PermissionDenied("Denied"))
        with pytest.raises(gcp_exceptions.PermissionDenied):
            retry_gcp_call(mock_fn, max_retries=3, base_delay=0.01)
        assert mock_fn.call_count == 1

    def test_retry_gcp_call_max_retries_exhausted(self) -> None:
        from utils.gcp_helpers import retry_gcp_call

        mock_fn = MagicMock(
            side_effect=gcp_exceptions.ResourceExhausted("Quota exceeded")
        )
        with pytest.raises(gcp_exceptions.ResourceExhausted):
            retry_gcp_call(mock_fn, max_retries=2, base_delay=0.01, max_delay=0.02)
        # initial try + 2 retries = 3 calls
        assert mock_fn.call_count == 3

    def test_retry_gcp_operation_decorator(self) -> None:
        from utils.gcp_helpers import retry_gcp_operation

        calls = 0

        @retry_gcp_operation(max_retries=2, base_delay=0.01, max_delay=0.02)
        def sample_operation(x: int) -> int:
            nonlocal calls
            calls += 1
            if calls < 2:
                raise gcp_exceptions.ServiceUnavailable("Unavailable")
            return x * 2

        res = sample_operation(21)
        assert res == 42
        assert calls == 2


# ===========================================================================
# 2. Tests for utils.tsv_utils
# ===========================================================================


class TestTSVUtils:
    """Test suite for utils/tsv_utils.py."""

    def test_escape_rfc4180_field_no_quotes_needed(self) -> None:
        from utils.tsv_utils import escape_rfc4180_field

        # Strings with no special characters return the exact same object
        raw = "Geist"
        assert escape_rfc4180_field(raw) == "Geist"
        assert escape_rfc4180_field("Seele") == "Seele"

    def test_escape_rfc4180_field_quotes_escaped(self) -> None:
        from utils.tsv_utils import escape_rfc4180_field

        assert escape_rfc4180_field('He said "yes"') == '"He said ""yes"""'
        assert escape_rfc4180_field('"quoted"') == '"""quoted"""'

    def test_escape_rfc4180_field_tab_and_newline(self) -> None:
        from utils.tsv_utils import escape_rfc4180_field

        assert escape_rfc4180_field("line1\nline2") == '"line1\nline2"'
        assert escape_rfc4180_field("term\tdefinition") == '"term\tdefinition"'
        assert escape_rfc4180_field("term\rreturn") == '"term\rreturn"'

    def test_format_tsv_bytes_sorted_and_encoded(self) -> None:
        from utils.tsv_utils import format_tsv_bytes

        entries = {
            "Seele": "Soul",
            "Geist": "Spirit",
            'Wirklichkeit\t"Real"': 'Reality\t"Real"',
        }

        tsv_data = format_tsv_bytes(entries)
        assert isinstance(tsv_data, bytes)
        decoded = tsv_data.decode("utf-8")
        lines = decoded.splitlines()

        assert lines[0] == "de\ten"
        # Alphabetical sorting check:
        # 1. "Geist"
        # 2. "Seele"
        # 3. 'Wirklichkeit\t"Real"'
        assert lines[1] == "Geist\tSpirit"
        assert lines[2] == "Seele\tSoul"
        assert lines[3] == '"Wirklichkeit\t""Real"""\t"Reality\t""Real"""'

    def test_format_tsv_bytes_empty(self) -> None:
        from utils.tsv_utils import format_tsv_bytes

        tsv_data = format_tsv_bytes({})
        assert tsv_data == b"de\ten\n"


# ===========================================================================
# 3. Tests for utils.pdf_stream
# ===========================================================================


class TestPDFStream:
    """Test suite for utils/pdf_stream.py."""

    def test_open_pdf_stream_with_path(self, tmp_path: Path) -> None:
        from utils.pdf_stream import open_pdf_stream

        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 sample content 1234567890")

        with open_pdf_stream(pdf_file) as (stream, size_mb):
            assert stream.read(5) == b"%PDF-"
            assert size_mb > 0
            # Stream should still be open
            assert not stream.closed

        # File descriptor must be deterministically closed on exit
        assert stream.closed

    def test_open_pdf_stream_with_str_path(self, tmp_path: Path) -> None:
        from utils.pdf_stream import open_pdf_stream

        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with open_pdf_stream(str(pdf_file)) as (stream, _size_mb):
            assert stream.read(4) == b"%PDF"
            assert not stream.closed
        assert stream.closed

    def test_open_pdf_stream_with_bytes(self) -> None:
        from utils.pdf_stream import open_pdf_stream

        raw = b"%PDF-1.4 bytes payload"
        with open_pdf_stream(raw) as (stream, size_mb):
            assert stream.read(4) == b"%PDF"
            assert size_mb > 0
            assert not stream.closed
        assert stream.closed

    def test_open_pdf_stream_with_seekable_stream(self) -> None:
        from utils.pdf_stream import open_pdf_stream

        buf = io.BytesIO(b"%PDF-1.4 external stream")
        buf.seek(10)  # Offset position

        with open_pdf_stream(buf) as (stream, size_mb):
            # Must be rewound to 0 automatically
            assert stream.tell() == 0
            assert stream.read(4) == b"%PDF"
            assert size_mb > 0
            assert not stream.closed

        # External stream must NOT be closed upon exit
        assert not buf.closed
        buf.close()

    def test_open_pdf_stream_cleanup_on_exception(self, tmp_path: Path) -> None:
        from utils.pdf_stream import open_pdf_stream

        pdf_file = tmp_path / "error.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        captured_stream = None
        with (
            pytest.raises(RuntimeError, match="Processing failed"),
            open_pdf_stream(pdf_file) as (stream, _),
        ):
            captured_stream = stream
            raise RuntimeError("Processing failed")

        assert captured_stream is not None
        assert captured_stream.closed

    def test_open_pdf_stream_invalid_type(self) -> None:
        from utils.pdf_stream import open_pdf_stream

        with (
            pytest.raises(TypeError, match="Unsupported PDF source type"),
            open_pdf_stream(12345),  # type: ignore[arg-type]
        ):
            pass

    def test_open_pdf_stream_with_non_seekable_stream(self) -> None:
        from utils.pdf_stream import open_pdf_stream

        class NonSeekableStream(io.BytesIO):
            def seek(self, _offset: int, _whence: int = 0) -> int:
                raise OSError("Stream not seekable")

        raw_bytes = b"%PDF-1.4 non-seekable content"
        stream_in = NonSeekableStream(raw_bytes)
        with open_pdf_stream(stream_in) as (stream_out, size_mb):
            assert stream_out.read() == raw_bytes
            assert size_mb > 0
            assert not stream_out.closed
        assert stream_out.closed



# ===========================================================================
# 4. Tests for utils.file_handler (atomic writes)
# ===========================================================================


class TestAtomicFileHandler:
    """Test suite for atomic write helpers in utils/file_handler.py."""

    def test_atomic_write_json(self, tmp_path: Path) -> None:
        from utils.file_handler import atomic_write_json

        target = tmp_path / "sub" / "state.json"
        data = {"session_id": "sess-1", "count": 42}

        atomic_write_json(target, data)
        assert target.exists()

        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_atomic_write_text(self, tmp_path: Path) -> None:
        from utils.file_handler import atomic_write_text

        target = tmp_path / "sub" / "output.txt"
        text = "Hello PhenomenalLayout!\nLine 2"

        atomic_write_text(target, text)
        assert target.exists()
        assert target.read_text(encoding="utf-8") == text


# ===========================================================================
# 5. Tests for utils.language_utils (German compound detection)
# ===========================================================================


class TestGermanCompoundWord:
    """Test suite for utils/language_utils.py is_german_compound_word."""

    def test_valid_philosophical_compounds(self) -> None:
        from utils.language_utils import is_german_compound_word

        # Known philosophical compound nouns
        assert is_german_compound_word("Wirklichkeitsbewusstsein")
        assert is_german_compound_word("Bewusstseinsphilosophie")
        assert is_german_compound_word("Lebensweltthematik")
        assert is_german_compound_word("Lebensphilosophie")
        assert is_german_compound_word("Weltanschauung")
        assert is_german_compound_word("Erkenntnistheorie")
        assert is_german_compound_word("Seinsverständnis")
        assert is_german_compound_word("Geisteswissenschaft")
        assert is_german_compound_word("Handlungsstruktur")
        assert is_german_compound_word("Wissensbereich")

    def test_non_compound_rejection(self) -> None:
        from utils.language_utils import is_german_compound_word

        # Single root nouns (should be excluded)
        assert not is_german_compound_word("Bewusstsein")
        assert not is_german_compound_word("Wirklichkeit")
        assert not is_german_compound_word("Erkenntnis")
        assert not is_german_compound_word("Wahrnehmung")
        assert not is_german_compound_word("Philosophie")
        assert not is_german_compound_word("Wissenschaft")
        assert not is_german_compound_word("Gesellschaft")
        assert not is_german_compound_word("Dasein")
        assert not is_german_compound_word("Existenz")

        # Ordinary derived words and adjectives (Greptile review P1 fix)
        assert not is_german_compound_word("menschlich")
        assert not is_german_compound_word("menschlichen")
        assert not is_german_compound_word("wesentlich")
        assert not is_german_compound_word("wesentliche")
        assert not is_german_compound_word("eigentlich")
        assert not is_german_compound_word("natürlich")
        assert not is_german_compound_word("körperlich")
        assert not is_german_compound_word("körperlicher")
        assert not is_german_compound_word("körperlichste")

        # Short words & particles
        assert not is_german_compound_word("das")
        assert not is_german_compound_word("und")
        assert not is_german_compound_word("der")
        assert not is_german_compound_word("die")
        assert not is_german_compound_word("ist")
        assert not is_german_compound_word("")
        assert not is_german_compound_word("Sein")

    def test_multiple_capital_letters(self) -> None:
        from utils.language_utils import is_german_compound_word

        # German noun compounds with internal capitals / camelCase
        assert is_german_compound_word("WirklichkeitsBewusstsein")
        assert is_german_compound_word("SeinsStruktur")

    def test_type_and_input_safety(self) -> None:
        from utils.language_utils import is_german_compound_word

        assert not is_german_compound_word(None)  # type: ignore[arg-type]
        assert not is_german_compound_word(12345)  # type: ignore[arg-type]

    def test_get_german_morphological_patterns(self) -> None:
        from utils.language_utils import get_german_morphological_patterns

        patterns = get_german_morphological_patterns()
        assert "compound_linking" in patterns
        assert "philosophical_prefixes" in patterns
        assert "abstract_suffixes" in patterns
        assert "philosophical_endings" in patterns
        assert "compound_patterns" in patterns

    def test_extract_text_sample_for_language_detection(self) -> None:
        from utils.language_utils import extract_text_sample_for_language_detection

        # Test non-pdf content
        sample = extract_text_sample_for_language_detection(
            {"type": "txt", "text_content": "Das ist ein philosophischer Text."}
        )
        assert sample == "Das ist ein philosophischer Text."

        # Test empty non-pdf content
        empty_sample = extract_text_sample_for_language_detection(
            {"type": "txt", "text_content": ""}
        )
        assert empty_sample == "No text content available"

        # Test pdf_advanced with first page text
        pdf_content = {
            "type": "pdf_advanced",
            "text_by_page": {0: ["First sentence.", "Second sentence."]},
        }
        pdf_sample = extract_text_sample_for_language_detection(pdf_content)
        assert pdf_sample == "First sentence. Second sentence."

        # Test pdf_advanced fallback to other page
        fallback_pdf = {
            "type": "pdf_advanced",
            "text_by_page": {0: [], 1: ["Page one text."]},
        }
        fallback_sample = extract_text_sample_for_language_detection(fallback_pdf)
        assert fallback_sample == "Page one text."

        # Test invalid structure
        invalid_sample = extract_text_sample_for_language_detection(
            {"type": "pdf_advanced", "text_by_page": None}
        )
        assert invalid_sample == "No text content available"

        error_sample = extract_text_sample_for_language_detection(None)  # type: ignore[arg-type]
        assert error_sample == "No text content available"


# ===========================================================================
# 6. Tests for models.user_choice_models (detect_choice_conflicts optimization)
# ===========================================================================


class TestOptimizedChoiceConflictDetection:
    """Test suite for hash-bucketed detect_choice_conflicts."""

    def test_detect_conflicts_basic(self) -> None:
        from models.user_choice_models import (
            ChoiceType,
            TranslationContext,
            UserChoice,
            detect_choice_conflicts,
        )

        ctx = TranslationContext(semantic_field="existentialism", author="Heidegger")

        choice_a = UserChoice(
            choice_id="choice_1",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            context=ctx,
        )
        choice_b = UserChoice(
            choice_id="choice_2",
            neologism_term="Dasein",
            choice_type=ChoiceType.PRESERVE,
            translation_result="",
            context=ctx,
        )
        choice_other = UserChoice(
            choice_id="choice_3",
            neologism_term="Sein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being",
            context=ctx,
        )

        conflicts = detect_choice_conflicts([choice_a, choice_b, choice_other])
        assert len(conflicts) == 1
        assert conflicts[0].neologism_term == "Dasein"
        assert {conflicts[0].choice_a.choice_id, conflicts[0].choice_b.choice_id} == {
            "choice_1",
            "choice_2",
        }

    def test_detect_conflicts_empty_or_single(self) -> None:
        from models.user_choice_models import (
            ChoiceType,
            TranslationContext,
            UserChoice,
            detect_choice_conflicts,
        )

        assert detect_choice_conflicts([]) == []

        ctx = TranslationContext()
        single = UserChoice(
            choice_id="c1",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            context=ctx,
        )
        assert detect_choice_conflicts([single]) == []

    def test_no_conflicts_for_disjoint_terms(self) -> None:
        from models.user_choice_models import (
            ChoiceType,
            TranslationContext,
            UserChoice,
            detect_choice_conflicts,
        )

        ctx = TranslationContext(semantic_field="ontology")
        choices = [
            UserChoice(
                choice_id=f"c_{i}",
                neologism_term=f"Term_{i}",
                choice_type=ChoiceType.TRANSLATE,
                translation_result=f"Trans_{i}",
                context=ctx,
            )
            for i in range(50)
        ]

        # All disjoint terms -> zero conflicts, fast exit
        assert detect_choice_conflicts(choices) == []

    def test_conflict_detection_performance_benchmark(self) -> None:
        """FR-08.3: 1,000 choices with 10 actual conflicts must complete in < 50ms."""
        import time

        from models.user_choice_models import (
            ChoiceType,
            TranslationContext,
            UserChoice,
            detect_choice_conflicts,
        )

        ctx = TranslationContext(semantic_field="metaphysics")
        choices: list[UserChoice] = []

        # 990 unique non-conflicting terms
        for i in range(990):
            choices.append(
                UserChoice(
                    choice_id=f"uniq_{i}",
                    neologism_term=f"UniqueTerm_{i}",
                    choice_type=ChoiceType.TRANSLATE,
                    translation_result=f"Trans_{i}",
                    context=ctx,
                )
            )

        # 5 pairs of conflicting terms (total 10 choices, yielding 5 conflicts)
        for i in range(5):
            choices.append(
                UserChoice(
                    choice_id=f"conf_a_{i}",
                    neologism_term=f"ConflictTerm_{i}",
                    choice_type=ChoiceType.TRANSLATE,
                    translation_result=f"VersionA_{i}",
                    context=ctx,
                )
            )
            choices.append(
                UserChoice(
                    choice_id=f"conf_b_{i}",
                    neologism_term=f"ConflictTerm_{i}",
                    choice_type=ChoiceType.PRESERVE,
                    translation_result="",
                    context=ctx,
                )
            )

        assert len(choices) == 1000

        start_time = time.perf_counter()
        conflicts = detect_choice_conflicts(choices)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        assert len(conflicts) == 5
        assert elapsed_ms < 50.0, f"Conflict detection took {elapsed_ms:.2f}ms (must be < 50ms)"

