"""Coverage-gap unit tests for the dynamic validation engine.

Exercises ValidationContext cache-key branches, per-validator outcome
branches, dependency-graph edge cases, pipeline fail-fast/skip/error
paths, benchmarking/reporting helpers, and the lazy FileValidator
backward-compatibility import.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import UploadFile

import core.dynamic_validation_engine as cve
from core.dynamic_validation_engine import (
    DynamicValidationEngine,
    FileExtensionValidator,
    FileSizeValidator,
    OptimizedFileValidator,
    PDFHeaderValidator,
    PDFStructureValidator,
    ValidationContext,
    ValidationGraph,
    ValidationOutcome,
    ValidationResult,
    ValidationSeverity,
    ValidatorProtocol,
    get_validation_engine,
    register_validation_engine,
)


def _make_pdf(
    path_dir: Path, *, name: str = "sample.pdf", eof: bool = True, size_hint: int = 32
) -> str:
    """Write a minimal PDF-shaped file and return its path as a string."""
    body = b"%PDF-1.4\n" + b"x" * max(size_hint - 9, 1) + (b"%%EOF\n" if eof else b"")
    pdf_path = path_dir / name
    pdf_path.write_bytes(body)
    return str(pdf_path)


class _ConfigurableValidator(ValidatorProtocol):
    """Stub validator for graph-topology and pipeline-branch tests."""

    def __init__(
        self,
        name: str,
        dependencies: list[str] | None = None,
        *,
        priority: int = 50,
        outcome: ValidationOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self._name = name
        self._dependencies = dependencies or []
        self._priority = priority
        self._outcome = outcome
        self._error = error

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> list[str]:
        return self._dependencies

    @property
    def cache_ttl_seconds(self) -> float | None:
        return None

    @property
    def priority(self) -> int:
        return self._priority

    def can_validate(self, _context: ValidationContext) -> bool:
        return True

    def validate(self, _context: ValidationContext) -> ValidationOutcome:
        if self._error is not None:
            raise self._error
        if self._outcome is not None:
            return self._outcome
        return ValidationOutcome(
            validator_name=self._name,
            result=ValidationResult.VALID,
            severity=ValidationSeverity.INFO,
        )


class TestValidationContextCacheKey:
    """Tests for ValidationContext cache-key generation branches."""

    def test_file_ext_derived_from_path_suffix_when_missing(self) -> None:
        """__post_init__ derives the lowercase suffix when file_ext is empty."""
        context = ValidationContext(file_path="reports/Book.PDF")

        assert context.file_ext == ".pdf"

    def test_file_ext_stays_empty_for_extensionless_paths(self) -> None:
        """Extensionless paths keep an empty file_ext after post-init."""
        context = ValidationContext(file_path="archive")

        assert context.file_ext == ""

    def test_explicit_cache_key_skips_generation(self) -> None:
        """A precomputed cache_key is preserved without regenerating it."""
        context = ValidationContext(file_path="book.pdf", cache_key="preset-key")

        assert context.cache_key == "preset-key"

    def test_unmanaged_missing_path_keeps_zero_size(self) -> None:
        """Paths outside managed roots skip stat resolution and keep size 0."""
        engine = DynamicValidationEngine()

        results = engine.validate_optimized("coverage-gap-missing.pdf")

        assert results["extension"].result == ValidationResult.VALID
        assert results["file_size"].result == ValidationResult.SKIPPED

    def test_large_file_declared_size_skips_content_hashing(self, tmp_path: Path) -> None:
        """Sizes above 1MB take the mtime-only hashing branch."""
        source = Path(_make_pdf(tmp_path, name="large.pdf"))
        large = ValidationContext(file_path=str(source), file_size=2 * 1024 * 1024)
        large_again = ValidationContext(
            file_path=str(source), file_size=2 * 1024 * 1024
        )
        small = ValidationContext(file_path=str(source), file_size=16)

        assert large.cache_key == large_again.cache_key
        assert large.cache_key != small.cache_key
        assert len(large.cache_key) == 16

    def test_directory_path_falls_back_to_unknown_content_hash(self) -> None:
        """OSError while hashing (directory open) falls back to stable defaults."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = ValidationContext(file_path=tmp_dir)
            second = ValidationContext(file_path=tmp_dir)

            assert first.cache_key == second.cache_key
            assert len(first.cache_key) == 16


class TestValidatorOutcomes:
    """Parametrized outcome tests for the built-in validators."""

    @pytest.mark.parametrize(
        ("validator", "expected_ttl"),
        [
            (FileExtensionValidator(), 3600),
            (FileSizeValidator(), 1800),
            (PDFHeaderValidator(), 3600),
            (PDFStructureValidator(), 1800),
        ],
        ids=["extension", "file_size", "pdf_header", "pdf_structure"],
    )
    def test_cache_ttl_seconds_values(
        self,
        validator: ValidatorProtocol,
        expected_ttl: float,
    ) -> None:
        """Built-in validators declare their documented cache TTLs."""
        assert validator.cache_ttl_seconds == expected_ttl

    @pytest.mark.parametrize(
        ("filename", "expected_result", "expected_fragment"),
        [
            ("archive", ValidationResult.INVALID, "No file extension found"),
            ("asset.exe", ValidationResult.INVALID, "Unsupported file extension"),
            ("asset.pdf", ValidationResult.VALID, "Valid file extension"),
        ],
        ids=["no-ext", "unsupported", "supported"],
    )
    def test_extension_validator_outcomes(
        self,
        filename: str,
        expected_result: ValidationResult,
        expected_fragment: str,
    ) -> None:
        """Extension validator covers missing, unsupported, and valid paths."""
        outcome = FileExtensionValidator().validate(
            ValidationContext(file_path=filename)
        )

        assert outcome.result == expected_result
        assert expected_fragment in outcome.message
        assert outcome.validator_name == "extension"

    @pytest.mark.parametrize(
        ("max_size_mb", "file_size", "expected_result", "expected_fragment"),
        [
            (50.0, 0, ValidationResult.INVALID, "File too small"),
            (1.0, 2 * 1024 * 1024, ValidationResult.INVALID, "File too large"),
            (50.0, 2048, ValidationResult.VALID, "Valid file size"),
        ],
        ids=["too-small", "too-large", "valid"],
    )
    def test_file_size_validator_outcomes(
        self,
        max_size_mb: float,
        file_size: int,
        expected_result: ValidationResult,
        expected_fragment: str,
    ) -> None:
        """Size validator covers below-minimum, above-maximum, and valid paths."""
        outcome = FileSizeValidator(max_size_mb=max_size_mb).validate(
            ValidationContext(file_path="book.pdf", file_size=file_size)
        )

        assert outcome.result == expected_result
        assert expected_fragment in outcome.message


class TestPDFHeaderAndStructureValidators:
    """Header/structure validator branches around file contents."""

    def test_invalid_pdf_header_is_invalid(self, tmp_path: Path) -> None:
        """Non-PDF magic bytes produce an INVALID outcome with header details."""
        bad_path = tmp_path / "bad.pdf"
        bad_path.write_bytes(b"NOTPDF!!payload")

        outcome = PDFHeaderValidator().validate(
            ValidationContext(file_path=str(bad_path), file_ext=".pdf")
        )

        assert outcome.result == ValidationResult.INVALID
        assert outcome.message == "Invalid PDF header"
        assert outcome.details["header_bytes"] == b"NOTPDF!!".hex()

    def test_small_file_without_eof_marker_warns(self, tmp_path: Path) -> None:
        """Files smaller than 10 bytes use the begin-seeking branch and warn."""
        tiny_path = tmp_path / "tiny.pdf"
        tiny_path.write_bytes(b"%PDF-")

        outcome = PDFStructureValidator().validate(
            ValidationContext(file_path=str(tiny_path), file_ext=".pdf")
        )

        assert outcome.result == ValidationResult.WARNING
        assert "no %%EOF" in outcome.message

    def test_file_without_eof_marker_warns(self, tmp_path: Path) -> None:
        """A tail without %%EOF yields the incomplete-PDF warning."""
        truncated_path = tmp_path / "truncated.pdf"
        truncated_path.write_bytes(b"%PDF-1.4\n" + b"y" * 24)

        outcome = PDFStructureValidator().validate(
            ValidationContext(file_path=str(truncated_path), file_ext=".pdf")
        )

        assert outcome.result == ValidationResult.WARNING
        assert "no %%EOF" in outcome.message

    def test_structure_validator_reports_valid_for_eof(self, tmp_path: Path) -> None:
        """A tail containing %%EOF passes structure validation."""
        pdf_file = _make_pdf(tmp_path)

        outcome = PDFStructureValidator().validate(
            ValidationContext(file_path=pdf_file, file_ext=".pdf")
        )

        assert outcome.result == ValidationResult.VALID
        assert outcome.message == "Basic PDF structure appears valid"


class TestValidationGraphTopology:
    """Dependency-graph ordering, caching, cycle, and critical-path tests."""

    def test_execution_order_is_cached_after_first_computation(self) -> None:
        """Repeated get_execution_order calls reuse the cached ordering."""
        graph = ValidationGraph()
        graph.add_validator(FileExtensionValidator())

        first = graph.get_execution_order()
        second = graph.get_execution_order()

        assert first == ["extension"]
        assert second is first

    def test_circular_dependencies_raise_value_error(self) -> None:
        """Mutual dependencies abort topological sorting with a clear error."""
        graph = ValidationGraph()
        graph.add_validator(_ConfigurableValidator("cycle_a", ["cycle_b"]))
        graph.add_validator(_ConfigurableValidator("cycle_b", ["cycle_a"]))

        with pytest.raises(ValueError, match=r"Circular dependencies detected"):
            graph.get_execution_order()

    def test_critical_path_is_empty_when_every_node_has_dependents(self) -> None:
        """A graph without sinks yields an empty critical path."""
        graph = ValidationGraph()
        graph.add_validator(_ConfigurableValidator("cycle_a", ["cycle_b"]))
        graph.add_validator(_ConfigurableValidator("cycle_b", ["cycle_a"]))

        assert graph.get_critical_path() == []


class TestEnginePipelineBranches:
    """Engine pipeline tests for skip, dependency-error, and fail-fast paths."""

    def test_non_pdf_context_skips_pdf_validators(self, tmp_path: Path) -> None:
        """Inapplicable validators are recorded as SKIPPED and still complete."""
        text_file = tmp_path / "notes.txt"
        text_file.write_bytes(b"plain text" * 4)
        engine = DynamicValidationEngine(fail_fast=False)

        results = engine.validate_optimized(str(text_file), file_size=40)

        assert results["extension"].result == ValidationResult.INVALID
        assert results["pdf_header"].result == ValidationResult.SKIPPED
        assert results["pdf_structure"].result == ValidationResult.SKIPPED
        assert results["pdf_header"].message == (
            "Validator not applicable to this context"
        )

    def test_validator_error_without_fail_fast_marks_dependents(
        self, tmp_path: Path
    ) -> None:
        """With fail_fast off, an errored dependency leaves dependents unsatisfied."""
        pdf_file = _make_pdf(tmp_path)
        engine = DynamicValidationEngine(fail_fast=False)
        engine.add_validator(
            _ConfigurableValidator(
                "failer", error=RuntimeError("simulated validator failure")
            )
        )
        engine.add_validator(_ConfigurableValidator("dependent", ["failer"]))

        results = engine.validate_optimized(pdf_file, file_size=64)

        assert results["failer"].result == ValidationResult.ERROR
        assert "simulated validator failure" in results["failer"].message
        assert results["dependent"].result == ValidationResult.ERROR
        assert results["dependent"].dependencies_satisfied is False
        assert "Dependencies not satisfied" in results["dependent"].message

    def test_validator_error_with_fail_fast_stops_pipeline(self, tmp_path: Path) -> None:
        """With fail_fast on, a raising validator stops later validators."""
        pdf_file = _make_pdf(tmp_path)
        engine = DynamicValidationEngine()
        engine.add_validator(
            _ConfigurableValidator(
                "failer",
                priority=100,
                error=RuntimeError("simulated validator failure"),
            )
        )

        results = engine.validate_optimized(pdf_file, file_size=64)

        assert list(results) == ["failer"]
        assert results["failer"].result == ValidationResult.ERROR

    def test_blocking_outcome_with_fail_fast_stops_pipeline(
        self, tmp_path: Path
    ) -> None:
        """A critical blocking outcome halts subsequent validators."""
        pdf_file = _make_pdf(tmp_path)
        engine = DynamicValidationEngine()
        engine.add_validator(
            _ConfigurableValidator(
                "blocker",
                priority=100,
                outcome=ValidationOutcome(
                    validator_name="blocker",
                    result=ValidationResult.INVALID,
                    severity=ValidationSeverity.CRITICAL,
                    message="blocked on purpose",
                ),
            )
        )

        results = engine.validate_optimized(pdf_file, file_size=64)

        assert list(results) == ["blocker"]
        assert "extension" not in results

    def test_engine_error_returns_validation_error_outcome(self) -> None:
        """Undetectable contexts produce a CRITICAL engine error outcome."""
        engine = DynamicValidationEngine()

        results = engine.validate_optimized("null\x00byte.pdf")

        error_outcome = results["validation_error"]
        assert error_outcome.result == ValidationResult.ERROR
        assert error_outcome.severity == ValidationSeverity.CRITICAL
        assert error_outcome.message.startswith("Validation engine error")

    def test_inner_result_cache_returns_same_outcome_dict(self, tmp_path: Path) -> None:
        """Equivalent contexts hit the result cache even when memoize keys differ."""
        pdf_file = _make_pdf(tmp_path)
        engine = DynamicValidationEngine()

        first = engine.validate_optimized(pdf_file, file_size=64)
        second = engine.validate_optimized(pdf_file, file_size=64, metadata={"a": 1})

        assert second is first

    def test_validate_batch_runs_both_parallel_modes(self, tmp_path: Path) -> None:
        """validate_batch maps paths to results in sequential and parallel modes."""
        paths = [
            _make_pdf(tmp_path, name="first.pdf"),
            _make_pdf(tmp_path, name="second.pdf"),
        ]

        sequential = DynamicValidationEngine().validate_batch(paths)
        parallel = DynamicValidationEngine(enable_parallel=True).validate_batch(paths)

        assert list(sequential) == paths
        assert list(parallel) == paths
        assert set(parallel) == set(sequential)


class TestEngineReportingHelpers:
    """Summary, metrics, benchmark, and level-analysis helpers."""

    def test_get_validation_summary_counts_outcome_categories(self) -> None:
        """Summary aggregates success, blocking, warnings, and timing."""
        engine = DynamicValidationEngine()
        results = {
            "ok": ValidationOutcome(
                validator_name="ok",
                result=ValidationResult.VALID,
                severity=ValidationSeverity.INFO,
                duration_ms=2.0,
            ),
            "warn": ValidationOutcome(
                validator_name="warn",
                result=ValidationResult.WARNING,
                severity=ValidationSeverity.MEDIUM,
                duration_ms=3.0,
            ),
            "blocked": ValidationOutcome(
                validator_name="blocked",
                result=ValidationResult.INVALID,
                severity=ValidationSeverity.CRITICAL,
                duration_ms=5.0,
            ),
            "failed": ValidationOutcome(
                validator_name="failed",
                result=ValidationResult.ERROR,
                severity=ValidationSeverity.CRITICAL,
                duration_ms=10.0,
            ),
        }

        summary = engine.get_validation_summary(results)

        assert summary["total_validations"] == 4
        assert summary["successful"] == 2
        assert summary["blocked"] == 1
        assert summary["warnings"] == 1
        assert summary["success_rate"] == 50.0
        assert summary["total_duration_ms"] == 20.0
        assert summary["avg_duration_ms"] == 5.0
        assert len(summary["critical_issues"]) == 2
        assert "extension" in summary["execution_order"]

    def test_execution_levels_break_on_circular_dependencies(self) -> None:
        """Level computation stops when a cycle keeps validators unsatisfiable."""
        engine = DynamicValidationEngine()
        engine.add_validator(_ConfigurableValidator("cycle_a", ["cycle_b"]))
        engine.add_validator(_ConfigurableValidator("cycle_b", ["cycle_a"]))

        levels = engine._calculate_execution_levels()
        flattened = {name for level in levels for name in level}

        assert "cycle_a" not in flattened
        assert "cycle_b" not in flattened
        assert "extension" in flattened

    def test_get_performance_metrics_exposes_sections(self) -> None:
        """Performance metrics bundle engine, validator, and cache statistics."""
        engine = DynamicValidationEngine()

        metrics = engine.get_performance_metrics()

        assert set(metrics) == {
            "engine_metrics",
            "validator_metrics",
            "cache_stats",
            "memoization_stats",
            "dependency_analysis",
        }
        assert metrics["engine_metrics"] is engine.metrics
        assert "extension" in metrics["validator_metrics"]

    def test_benchmark_vs_sequential_returns_report(self, tmp_path: Path) -> None:
        """Benchmark compares optimized and sequential timing profiles."""
        pdf_file = _make_pdf(tmp_path, name="bench.pdf")
        text_file = tmp_path / "bench.txt"
        text_file.write_bytes(b"plain benchmark text" * 3)
        engine = DynamicValidationEngine()

        report = engine.benchmark_vs_sequential([pdf_file, str(text_file)], iterations=2)

        assert report["test_files"] == 2
        assert report["iterations"] == 2
        assert report["speedup_factor"] >= 0
        assert report["avg_optimized_ms"] >= 0
        assert report["avg_sequential_ms"] >= 0
        assert 0.0 <= report["cache_effectiveness"] <= 100.0

    def test_get_registered_validators_lists_defaults(self) -> None:
        """The default engine registers the four built-in validators."""
        engine = DynamicValidationEngine()

        assert engine.get_registered_validators() == [
            "extension",
            "file_size",
            "pdf_header",
            "pdf_structure",
        ]

    def test_clear_caches_tolerates_missing_memoize_attachment(self) -> None:
        """clear_caches skips the memoize hook when it is not attached."""
        engine = DynamicValidationEngine()

        def detached_cache_stub(*args: Any, **kwargs: Any) -> None:
            return None

        engine.validate_optimized = detached_cache_stub

        engine.clear_caches()

        assert engine.result_cache.size() == 0


class TestOptimizedFileValidatorCompat:
    """Backward-compatibility wrapper delegation tests."""

    def test_validate_file_reports_invalid_for_unsupported_type(self) -> None:
        """Unsupported extensions flow through as invalid with an error string."""
        validator = OptimizedFileValidator()

        result = validator.validate_file("document.exe", 1024)

        assert result["valid"] is False
        assert "Unsupported file extension" in (result["error"] or "")

    def test_delegate_methods_match_original_validator(self) -> None:
        """Language/format/upload delegation matches the wrapped validator."""
        validator = OptimizedFileValidator()
        upload = UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="a.pdf")

        language_result = validator.validate_language("de")
        format_result = validator.validate_output_format("pdf")
        upload_result = validator.validate_upload_file(upload)

        assert language_result == validator.original_validator.validate_language("de")
        assert format_result == validator.original_validator.validate_output_format(
            "pdf"
        )
        assert upload_result["valid"] is False
        assert "Unsupported content type" in (upload_result["error"] or "")


class TestLazyFileValidatorImport:
    """Lazy FileValidator import fallback branches."""

    def test_import_error_returns_none_and_init_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Import failure yields a None validator and a RuntimeError on init."""
        monkeypatch.setattr(cve, "_file_validator", None)
        monkeypatch.setitem(sys.modules, "utils.validators", None)

        assert cve._get_file_validator() is None

        with pytest.raises(RuntimeError, match=r"FileValidator could not be imported"):
            OptimizedFileValidator()


class TestValidationEngineRegistry:
    """Named-engine registry access helpers."""

    def test_register_and_get_custom_engine(self) -> None:
        """Registered factories build engines with forwarded kwargs."""
        register_validation_engine(
            "covgap-engine", lambda **kwargs: DynamicValidationEngine(**kwargs)
        )

        engine = get_validation_engine("covgap-engine", cache_size=32)

        assert isinstance(engine, DynamicValidationEngine)
        assert engine.cache_size == 32

    def test_default_engine_shortcut_builds_new_engine(self) -> None:
        """The default name constructs a fresh engine with forwarded kwargs."""
        engine = get_validation_engine(fail_fast=False)

        assert isinstance(engine, DynamicValidationEngine)
        assert engine.fail_fast is False

    def test_unregistered_engine_name_raises_key_error(self) -> None:
        """Unknown registry names raise a descriptive KeyError."""
        with pytest.raises(KeyError, match=r"not registered"):
            get_validation_engine("covgap-missing-engine")
