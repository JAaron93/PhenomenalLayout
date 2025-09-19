"""Dynamic programming implementation for validation pipeline optimization.

This module replaces sequential validation chains with dependency-aware
execution graphs, result caching, and optimized validation ordering to
minimize redundant validations and improve performance.
"""

from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from core.dynamic_programming import (
    DynamicRegistry,
    PerformanceMetrics,
    SmartCache,
    memoize,
)


class ValidationResult(Enum):
    """Validation result status."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"


class ValidationSeverity(Enum):
    """Severity levels for validation results."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ValidationOutcome:
    """Complete validation outcome with details."""

    validator_name: str
    result: ValidationResult
    severity: ValidationSeverity = ValidationSeverity.MEDIUM
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    cached: bool = False
    dependencies_satisfied: bool = True

    @property
    def is_success(self) -> bool:
        """Check if validation was successful."""
        return self.result in (
            ValidationResult.VALID,
            ValidationResult.WARNING,
            ValidationResult.SKIPPED,
        )

    @property
    def is_blocking(self) -> bool:
        """Check if validation result should block further processing."""
        return self.result == ValidationResult.INVALID and self.severity in (
            ValidationSeverity.CRITICAL,
            ValidationSeverity.HIGH,
        )


@dataclass
class ValidationContext:
    """Context for validation operations."""

    file_path: str
    file_size: int = 0
    file_ext: str = ""
    mime_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    cache_key: str = ""

    def __post_init__(self):
        if not self.cache_key:
            self.cache_key = self._generate_cache_key()

        if not self.file_ext and self.file_path:
            self.file_ext = Path(self.file_path).suffix.lower()

    def _generate_cache_key(self) -> str:
        """Generate cache key for validation context.

        Includes file metadata, modification time, content hash, and validation rules version
        to ensure cache invalidation when file content or validation rules change.
        """
        # Get file modification time for cache invalidation
        mtime = "0"
        content_hash = "unknown"

        try:
            if os.path.exists(self.file_path):
                mtime = str(int(os.path.getmtime(self.file_path)))

                # For small files, include content hash for precise invalidation
                if self.file_size <= 1024 * 1024:  # 1MB limit for content hashing
                    with open(self.file_path, "rb") as f:
                        content_bytes = f.read()
                        content_hash = hashlib.md5(
                            content_bytes, usedforsecurity=False
                        ).hexdigest()[:8]
                else:
                    # For large files, use mtime only to avoid performance impact
                    content_hash = "large_file"
        except OSError:
            # File access issues - use fallback values
            pass

        # Validation rules version - can be enhanced with actual rule versioning
        rules_version = self._get_validation_rules_version()

        # Combine all cache key components
        key_data = (
            f"{self.file_path}:{self.file_size}:{self.file_ext}:"
            f"{self.mime_type}:{mtime}:{content_hash}:{rules_version}"
        )

        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _get_validation_rules_version(self) -> str:
        """Get validation rules version for cache invalidation.

        This should be enhanced to include actual validation rule checksums
        or version numbers when validation rules become configurable.
        """
        # For now, use a simple version string
        # TODO: Implement proper rule versioning when rules become configurable
        return "v1.0"


class ValidatorProtocol(ABC):
    """Protocol for validation implementations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Validator name."""
        pass

    @property
    @abstractmethod
    def dependencies(self) -> list[str]:
        """List of validator names this validator depends on."""
        pass

    @property
    @abstractmethod
    def cache_ttl_seconds(self) -> Optional[float]:
        """Cache TTL for this validator's results."""
        pass

    @abstractmethod
    def can_validate(self, context: ValidationContext) -> bool:
        """Check if this validator can handle the given context."""
        pass

    @abstractmethod
    def validate(self, context: ValidationContext) -> ValidationOutcome:
        """Perform validation and return outcome."""
        pass

    @property
    def priority(self) -> int:
        """Validation priority (higher = earlier execution)."""
        return 50


class FileExtensionValidator(ValidatorProtocol):
    """Validates file extensions."""

    def __init__(self, allowed_extensions: set[str] = None):
        self.allowed_extensions = allowed_extensions or {".pdf"}

    @property
    def name(self) -> str:
        return "extension"

    @property
    def dependencies(self) -> list[str]:
        return []

    @property
    def cache_ttl_seconds(self) -> Optional[float]:
        return 3600  # 1 hour

    def can_validate(self, context: ValidationContext) -> bool:
        return bool(context.file_path)

    def validate(self, context: ValidationContext) -> ValidationOutcome:
        start_time = time.perf_counter()

        if not context.file_ext:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.INVALID,
                severity=ValidationSeverity.HIGH,
                message="No file extension found",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        if context.file_ext not in self.allowed_extensions:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.INVALID,
                severity=ValidationSeverity.HIGH,
                message=f"Unsupported file extension: {context.file_ext}",
                details={"allowed_extensions": list(self.allowed_extensions)},
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        return ValidationOutcome(
            validator_name=self.name,
            result=ValidationResult.VALID,
            severity=ValidationSeverity.INFO,
            message=f"Valid file extension: {context.file_ext}",
            duration_ms=(time.perf_counter() - start_time) * 1000,
        )


class FileSizeValidator(ValidatorProtocol):
    """Validates file size limits."""

    def __init__(self, max_size_mb: float = 50.0, min_size_bytes: int = 1):
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.min_size_bytes = min_size_bytes

    @property
    def name(self) -> str:
        return "file_size"

    @property
    def dependencies(self) -> list[str]:
        return ["extension"]

    @property
    def cache_ttl_seconds(self) -> Optional[float]:
        return 1800  # 30 minutes

    def can_validate(self, context: ValidationContext) -> bool:
        return context.file_size > 0

    def validate(self, context: ValidationContext) -> ValidationOutcome:
        start_time = time.perf_counter()

        if context.file_size < self.min_size_bytes:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.INVALID,
                severity=ValidationSeverity.HIGH,
                message=f"File too small: {context.file_size} bytes",
                details={"min_size_bytes": self.min_size_bytes},
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        if context.file_size > self.max_size_bytes:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.INVALID,
                severity=ValidationSeverity.HIGH,
                message=f"File too large: {context.file_size} bytes",
                details={"max_size_bytes": self.max_size_bytes},
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        return ValidationOutcome(
            validator_name=self.name,
            result=ValidationResult.VALID,
            severity=ValidationSeverity.INFO,
            message=f"Valid file size: {context.file_size} bytes",
            duration_ms=(time.perf_counter() - start_time) * 1000,
        )


class PDFHeaderValidator(ValidatorProtocol):
    """Validates PDF file headers."""

    @property
    def name(self) -> str:
        return "pdf_header"

    @property
    def dependencies(self) -> list[str]:
        return ["extension", "file_size"]

    @property
    def cache_ttl_seconds(self) -> Optional[float]:
        return 3600  # 1 hour

    def can_validate(self, context: ValidationContext) -> bool:
        return context.file_ext == ".pdf"

    def validate(self, context: ValidationContext) -> ValidationOutcome:
        start_time = time.perf_counter()

        try:
            # Read first few bytes to check PDF header
            with open(context.file_path, "rb") as f:
                header = f.read(8)

            if not header.startswith(b"%PDF-"):
                return ValidationOutcome(
                    validator_name=self.name,
                    result=ValidationResult.INVALID,
                    severity=ValidationSeverity.HIGH,
                    message="Invalid PDF header",
                    details={"header_bytes": header.hex()},
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Extract PDF version
            version_bytes = header[5:8]
            version = version_bytes.decode("ascii", errors="ignore")

            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.VALID,
                severity=ValidationSeverity.INFO,
                message=f"Valid PDF header, version: {version}",
                details={"pdf_version": version},
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        except Exception as e:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.ERROR,
                severity=ValidationSeverity.HIGH,
                message=f"Error reading PDF header: {e}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )


class PDFStructureValidator(ValidatorProtocol):
    """Validates basic PDF structure."""

    @property
    def name(self) -> str:
        return "pdf_structure"

    @property
    def dependencies(self) -> list[str]:
        return ["pdf_header"]

    @property
    def cache_ttl_seconds(self) -> Optional[float]:
        return 1800  # 30 minutes

    def can_validate(self, context: ValidationContext) -> bool:
        return context.file_ext == ".pdf"

    def validate(self, context: ValidationContext) -> ValidationOutcome:
        start_time = time.perf_counter()

        try:
            # Basic PDF structure validation
            with open(context.file_path, "rb") as f:
                # Check for %%EOF at end (if file is large enough)
                file_size = f.seek(0, 2)  # Get file size
                if file_size >= 10:
                    f.seek(-10, 2)  # Seek to near end
                else:
                    f.seek(0)  # Read from beginning for small files
                tail = f.read().decode("ascii", errors="ignore")

                if "%%EOF" not in tail:
                    return ValidationOutcome(
                        validator_name=self.name,
                        result=ValidationResult.WARNING,
                        severity=ValidationSeverity.MEDIUM,
                        message="PDF may be incomplete (no %%EOF found)",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                    )

            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.VALID,
                severity=ValidationSeverity.INFO,
                message="Basic PDF structure appears valid",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        except Exception as e:
            return ValidationOutcome(
                validator_name=self.name,
                result=ValidationResult.ERROR,
                severity=ValidationSeverity.MEDIUM,
                message=f"Error validating PDF structure: {e}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )


class ValidationGraph:
    """Dependency graph for validation execution."""

    def __init__(self):
        self.validators: dict[str, ValidatorProtocol] = {}
        self.dependencies: dict[str, set[str]] = defaultdict(set)
        self.dependents: dict[str, set[str]] = defaultdict(set)
        self._execution_order: Optional[list[str]] = None

    def add_validator(self, validator: ValidatorProtocol) -> None:
        """Add a validator to the graph."""
        self.validators[validator.name] = validator

        # Build dependency relationships
        for dep in validator.dependencies:
            self.dependencies[validator.name].add(dep)
            self.dependents[dep].add(validator.name)

        # Clear cached execution order
        self._execution_order = None

    def get_execution_order(self) -> list[str]:
        """Get optimized execution order using topological sort."""
        if self._execution_order is not None:
            return self._execution_order

        # Topological sort with priority ordering
        in_degree = defaultdict(int)
        for validator_name in self.validators:
            in_degree[validator_name] = len(self.dependencies[validator_name])

        # Use priority queue to handle priorities
        available = []
        for validator_name, degree in in_degree.items():
            if degree == 0:
                validator = self.validators[validator_name]
                available.append((validator.priority, validator_name))

        available.sort(reverse=True)  # Higher priority first
        execution_order = []

        while available:
            _, current = available.pop(0)
            execution_order.append(current)

            # Update dependencies
            for dependent in self.dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    validator = self.validators[dependent]
                    available.append((validator.priority, dependent))
                    available.sort(reverse=True)

        # Check for cycles
        if len(execution_order) != len(self.validators):
            remaining = set(self.validators.keys()) - set(execution_order)
            raise ValueError(f"Circular dependencies detected: {remaining}")

        self._execution_order = execution_order
        return execution_order

    def can_execute(self, validator_name: str, completed: set[str]) -> bool:
        """Check if validator can be executed given completed validators."""
        dependencies = self.dependencies[validator_name]
        return dependencies.issubset(completed)

    def get_critical_path(self) -> list[str]:
        """Get critical path through validation graph."""
        # Find validators with no dependents (sinks)
        sinks = [name for name in self.validators if not self.dependents[name]]

        if not sinks:
            return []

        # For simplicity, return path to first sink
        # In practice, might want to analyze all paths
        critical_path = []
        current = sinks[0]
        visited = set()

        while current and current not in visited:
            critical_path.insert(0, current)
            visited.add(current)

            # Find dependency with highest priority
            deps = self.dependencies[current]
            if deps:
                next_validator = max(deps, key=lambda x: self.validators[x].priority)
                current = next_validator
            else:
                break

        return critical_path


class DynamicValidationEngine:
    """Dynamic validation engine with dependency optimization and caching."""

    def __init__(
        self,
        cache_size: int = 512,
        enable_parallel: bool = False,
        fail_fast: bool = True,
    ):
        self.cache_size = cache_size
        self.enable_parallel = enable_parallel
        self.fail_fast = fail_fast

        # Validation graph and caching
        self.graph = ValidationGraph()
        self.result_cache: SmartCache[str, dict[str, ValidationOutcome]] = SmartCache(
            max_size=cache_size, ttl_seconds=1800  # 30 minutes default
        )

        # Performance tracking
        self.metrics = PerformanceMetrics("dynamic_validation_engine")
        self.validator_metrics: dict[str, PerformanceMetrics] = {}

        # Register default validators
        self._register_default_validators()

    def _register_default_validators(self) -> None:
        """Register default validation suite."""
        self.add_validator(FileExtensionValidator())
        self.add_validator(FileSizeValidator())
        self.add_validator(PDFHeaderValidator())
        self.add_validator(PDFStructureValidator())

    def add_validator(self, validator: ValidatorProtocol) -> None:
        """Add validator to the engine."""
        self.graph.add_validator(validator)
        self.validator_metrics[validator.name] = PerformanceMetrics(validator.name)

    @memoize(cache_size=128, ttl_seconds=300)
    def validate_optimized(
        self, file_path: str, **context_kwargs
    ) -> dict[str, ValidationOutcome]:
        """Optimized validation with dependency-aware execution and caching."""
        start_time = time.perf_counter()

        try:
            # Create validation context
            context = self._create_context(file_path, **context_kwargs)

            # Check cache
            cached_results = self.result_cache.get(context.cache_key)
            if cached_results:
                # Verify cached results are still valid (TTL check)
                valid_cache = self._validate_cache_freshness(cached_results)
                if valid_cache:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    self.metrics.record_operation(duration_ms, cache_hit=True)
                    return cached_results

            # Execute validations
            results = self._execute_validation_pipeline(context)

            # Cache results
            self.result_cache.put(context.cache_key, results)

            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_operation(duration_ms, cache_hit=False)

            return results

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_operation(duration_ms, cache_hit=False)

            # Return error result
            return {
                "validation_error": ValidationOutcome(
                    validator_name="engine",
                    result=ValidationResult.ERROR,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Validation engine error: {e}",
                    duration_ms=duration_ms,
                )
            }

    def _create_context(self, file_path: str, **kwargs) -> ValidationContext:
        """Create validation context with file analysis."""
        file_path_obj = Path(file_path)

        file_size = 0
        if file_path_obj.exists():
            file_size = file_path_obj.stat().st_size

        return ValidationContext(
            file_path=file_path,
            file_size=file_size,
            file_ext=file_path_obj.suffix.lower(),
            **kwargs,
        )

    def _validate_cache_freshness(
        self, cached_results: dict[str, ValidationOutcome]
    ) -> bool:
        """Check if cached results are still fresh based on TTL."""
        current_time = time.time()

        for outcome in cached_results.values():
            validator = self.graph.validators.get(outcome.validator_name)
            if validator and validator.cache_ttl_seconds:
                # Would need timestamp in cached results for proper TTL check
                # For now, assume cache is managed by SmartCache TTL
                pass

        return True  # SmartCache handles TTL

    def _execute_validation_pipeline(
        self, context: ValidationContext
    ) -> dict[str, ValidationOutcome]:
        """Execute validation pipeline with optimized ordering."""
        execution_order = self.graph.get_execution_order()
        results = {}
        completed = set()

        for validator_name in execution_order:
            validator = self.graph.validators[validator_name]

            # Check if validator can handle this context
            if not validator.can_validate(context):
                results[validator_name] = ValidationOutcome(
                    validator_name=validator_name,
                    result=ValidationResult.SKIPPED,
                    message="Validator not applicable to this context",
                )
                completed.add(validator_name)
                continue

            # Check dependencies
            if not self.graph.can_execute(validator_name, completed):
                results[validator_name] = ValidationOutcome(
                    validator_name=validator_name,
                    result=ValidationResult.ERROR,
                    severity=ValidationSeverity.HIGH,
                    message="Dependencies not satisfied",
                    dependencies_satisfied=False,
                )
                if self.fail_fast:
                    break
                continue

            # Execute validation
            start_time = time.perf_counter()
            try:
                outcome = validator.validate(context)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Update metrics
                self.validator_metrics[validator_name].record_operation(duration_ms)

                results[validator_name] = outcome
                completed.add(validator_name)

                # Check for critical failures
                if self.fail_fast and outcome.is_blocking:
                    break

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self.validator_metrics[validator_name].record_operation(duration_ms)

                results[validator_name] = ValidationOutcome(
                    validator_name=validator_name,
                    result=ValidationResult.ERROR,
                    severity=ValidationSeverity.HIGH,
                    message=f"Validator error: {e}",
                    duration_ms=duration_ms,
                )

                if self.fail_fast:
                    break

        return results

    def validate_batch(
        self, file_paths: list[str]
    ) -> dict[str, dict[str, ValidationOutcome]]:
        """Batch validation for improved throughput."""
        results = {}

        if self.enable_parallel:
            # Placeholder for parallel execution
            # Would use threading/multiprocessing here
            for file_path in file_paths:
                results[file_path] = self.validate_optimized(file_path)
        else:
            for file_path in file_paths:
                results[file_path] = self.validate_optimized(file_path)

        return results

    def get_validation_summary(
        self, results: dict[str, ValidationOutcome]
    ) -> dict[str, Any]:
        """Generate validation summary."""
        total_validations = len(results)
        successful = sum(1 for outcome in results.values() if outcome.is_success)
        blocked = sum(1 for outcome in results.values() if outcome.is_blocking)
        warnings = sum(
            1
            for outcome in results.values()
            if outcome.result == ValidationResult.WARNING
        )

        total_duration = sum(outcome.duration_ms for outcome in results.values())

        return {
            "total_validations": total_validations,
            "successful": successful,
            "blocked": blocked,
            "warnings": warnings,
            "success_rate": (successful / total_validations) * 100
            if total_validations > 0
            else 0,
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / total_validations
            if total_validations > 0
            else 0,
            "critical_issues": [
                outcome
                for outcome in results.values()
                if outcome.severity == ValidationSeverity.CRITICAL
            ],
            "execution_order": self.graph.get_execution_order(),
        }

    def analyze_dependency_impact(self) -> dict[str, Any]:
        """Analyze impact of dependency optimization."""
        execution_order = self.graph.get_execution_order()
        critical_path = self.graph.get_critical_path()

        # Calculate potential parallelization opportunities
        levels = self._calculate_execution_levels()

        return {
            "execution_order": execution_order,
            "critical_path": critical_path,
            "execution_levels": levels,
            "parallelization_opportunities": len(levels),
            "max_parallel_validators": max(len(level) for level in levels)
            if levels
            else 0,
            "dependency_graph_stats": {
                "total_validators": len(self.graph.validators),
                "total_dependencies": sum(
                    len(deps) for deps in self.graph.dependencies.values()
                ),
                "avg_dependencies_per_validator": sum(
                    len(deps) for deps in self.graph.dependencies.values()
                )
                / len(self.graph.validators)
                if self.graph.validators
                else 0,
            },
        }

    def _calculate_execution_levels(self) -> list[list[str]]:
        """Calculate execution levels for potential parallelization."""
        levels = []
        remaining = set(self.graph.validators.keys())
        completed = set()

        while remaining:
            current_level = []
            for validator_name in list(remaining):
                if self.graph.can_execute(validator_name, completed):
                    current_level.append(validator_name)

            if not current_level:
                # Circular dependency or other issue
                break

            levels.append(current_level)
            for validator_name in current_level:
                remaining.remove(validator_name)
                completed.add(validator_name)

        return levels

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        return {
            "engine_metrics": self.metrics,
            "validator_metrics": dict(self.validator_metrics),
            "cache_stats": self.result_cache.stats(),
            "memoization_stats": getattr(
                self.validate_optimized, "cache_stats", lambda: {}
            )(),
            "dependency_analysis": self.analyze_dependency_impact(),
        }

    def benchmark_vs_sequential(
        self, test_files: list[str], iterations: int = 10
    ) -> dict[str, Any]:
        """Benchmark optimized approach vs sequential validation."""
        # Benchmark optimized approach
        start = time.perf_counter()
        for _ in range(iterations):
            for file_path in test_files:
                self.validate_optimized(file_path)
        optimized_time = time.perf_counter() - start

        # Clear caches and simulate sequential approach
        self.clear_caches()

        start = time.perf_counter()
        for _ in range(iterations):
            for file_path in test_files:
                # Simulate sequential validation without optimization
                context = self._create_context(file_path)
                for validator_name in self.graph.validators:
                    validator = self.graph.validators[validator_name]
                    if validator.can_validate(context):
                        validator.validate(context)
        sequential_time = time.perf_counter() - start

        return {
            "optimized_time_seconds": optimized_time,
            "sequential_time_seconds": sequential_time,
            "speedup_factor": sequential_time / max(optimized_time, 0.001),
            "test_files": len(test_files),
            "iterations": iterations,
            "avg_optimized_ms": (optimized_time / (iterations * len(test_files)))
            * 1000,
            "avg_sequential_ms": (sequential_time / (iterations * len(test_files)))
            * 1000,
            "cache_effectiveness": self.metrics.cache_hit_rate,
        }

    def clear_caches(self) -> None:
        """Clear all internal caches."""
        self.result_cache.clear()
        if hasattr(self.validate_optimized, "clear_cache"):
            self.validate_optimized.clear_cache()

    def get_registered_validators(self) -> list[str]:
        """Get list of registered validator names."""
        return list(self.graph.validators.keys())


# Backward compatibility wrapper
_file_validator = None


def _get_file_validator():
    global _file_validator
    if _file_validator is None:
        try:
            from utils.validators import FileValidator

            _file_validator = FileValidator
        except ImportError:
            # Return None or a stub class
            _file_validator = None
    return _file_validator


class OptimizedFileValidator:
    """Drop-in replacement for FileValidator with dynamic programming optimizations."""

    def __init__(self):
        validator_class = _get_file_validator()
        if validator_class is None:
            raise RuntimeError("FileValidator could not be imported")
        self.original_validator = validator_class()
        self.dynamic_engine = DynamicValidationEngine()

    def validate_file(self, filename: str, file_size: int) -> dict[str, Any]:
        """Validate using optimized engine."""
        # Create temporary context for validation
        results = self.dynamic_engine.validate_optimized(filename, file_size=file_size)

        # Convert to original format
        has_errors = any(not outcome.is_success for outcome in results.values())
        error_messages = [
            outcome.message for outcome in results.values() if not outcome.is_success
        ]

        return {
            "valid": not has_errors,
            "error": "; ".join(error_messages) if error_messages else None,
        }

    def validate_upload_file(self, upload_file) -> dict[str, Any]:
        """Delegate to original implementation for upload files."""
        return self.original_validator.validate_upload_file(upload_file)

    def validate_language(self, language: str) -> dict[str, Any]:
        """Delegate to original implementation."""
        return self.original_validator.validate_language(language)

    def validate_output_format(self, format_type: str) -> dict[str, Any]:
        """Delegate to original implementation."""
        return self.original_validator.validate_output_format(format_type)


# Global registry for validation engines
VALIDATION_ENGINE_REGISTRY = DynamicRegistry[DynamicValidationEngine](
    cache_size=16, ttl_seconds=3600
)


def register_validation_engine(
    name: str, engine_factory: Callable[..., DynamicValidationEngine]
) -> None:
    """Register a custom validation engine."""
    VALIDATION_ENGINE_REGISTRY.register(name, engine_factory)


def get_validation_engine(name: str = "default", **kwargs) -> DynamicValidationEngine:
    """Get a validation engine instance."""
    if name == "default":
        return DynamicValidationEngine(**kwargs)
    return VALIDATION_ENGINE_REGISTRY.get(name, **kwargs)


# Export for backward compatibility
__all__ = [
    "DynamicValidationEngine",
    "OptimizedFileValidator",
    "ValidatorProtocol",
]
