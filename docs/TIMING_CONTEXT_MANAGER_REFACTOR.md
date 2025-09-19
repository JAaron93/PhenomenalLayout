# Timing Context Manager Refactoring

## Overview
This document describes the refactoring of duplicated timing blocks in [`core/dynamic_layout_engine.py`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_layout_engine.py) by extracting a reusable timing context manager.

## Problem Statement
The original code had duplicated timing patterns around lines 300 and 333-334:

### Pattern 1: Try-Finally Block (Lines 309-342)
```python
def determine_strategy_optimized(self, analysis: FitAnalysis) -> LayoutStrategy:
    start_time = time.perf_counter()

    try:
        # Strategy determination logic
        key = StrategyKey(...)
        builder = self.strategy_table.get(key.to_int())
        # ... more logic
        return result

    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.record_operation(duration_ms)
```

### Pattern 2: Simple Start-End Timing (Lines 397-401)
```python
def benchmark_vs_original(self, test_analyses: list[FitAnalysis], iterations: int = 1000):
    # Time the optimized approach
    start = time.perf_counter()
    for _ in range(iterations):
        for analysis in test_analyses:
            self.determine_strategy_optimized(analysis)
    optimized_time = time.perf_counter() - start
```

## Problems with Duplication
1. **Code Repetition**: Same timing pattern repeated across methods
2. **Error Prone**: Manual timing calculations in multiple places
3. **Maintenance Burden**: Changes to timing logic require updates in multiple locations
4. **Inconsistency**: Different timing patterns for similar operations
5. **DRY Violation**: Violates "Don't Repeat Yourself" principle

## Solution: Reusable Timing Context Manager

### Context Manager Implementation
```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def time_operation(metrics: PerformanceMetrics, cache_hit: bool = False) -> Generator[None, None, None]:
    """Context manager for timing operations and recording metrics.

    Args:
        metrics: PerformanceMetrics instance to record timing data
        cache_hit: Whether this operation was a cache hit

    Usage:
        with time_operation(self.metrics) as timer:
            # Your operation code here
            result = some_operation()
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_operation(duration_ms, cache_hit=cache_hit)
```

### Key Features
1. **Automatic Timing**: Start time captured on entry, duration calculated on exit
2. **Exception Safety**: `finally` block ensures timing is recorded even if exceptions occur
3. **Metrics Integration**: Direct integration with existing [`PerformanceMetrics.record_operation`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_programming.py#L68-L78)
4. **Cache Hit Support**: Optional parameter to indicate cache hits
5. **Type Hints**: Full type annotations for better IDE support

## Refactored Implementation

### Before and After: determine_strategy_optimized

**Before** (Manual timing with try-finally):
```python
@memoize(cache_size=512, ttl_seconds=300)
def determine_strategy_optimized(self, analysis: FitAnalysis) -> LayoutStrategy:
    start_time = time.perf_counter()

    try:
        # Create strategy key from analysis
        key = StrategyKey(...)
        # ... strategy logic
        return result

    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.record_operation(duration_ms)
```

**After** (Context manager):
```python
@memoize(cache_size=512, ttl_seconds=300)
def determine_strategy_optimized(self, analysis: FitAnalysis) -> LayoutStrategy:
    with time_operation(self.metrics):
        # Create strategy key from analysis
        key = StrategyKey(...)
        # ... strategy logic
        return result
```

### Before and After: benchmark_vs_original

**Before** (Manual start-end timing):
```python
def benchmark_vs_original(self, test_analyses: list[FitAnalysis], iterations: int = 1000):
    # Time the optimized approach
    start = time.perf_counter()
    for _ in range(iterations):
        for analysis in test_analyses:
            self.determine_strategy_optimized(analysis)
    optimized_time = time.perf_counter() - start

    return {
        "optimized_time_seconds": optimized_time,
        # ... other metrics
    }
```

**After** (Context manager with metrics integration):
```python
def benchmark_vs_original(self, test_analyses: list[FitAnalysis], iterations: int = 1000):
    # Time the optimized approach
    with time_operation(self.metrics):
        for _ in range(iterations):
            for analysis in test_analyses:
                self.determine_strategy_optimized(analysis)

    # Get timing data from the metrics
    optimized_time = self.metrics.total_duration_ms / 1000  # Convert to seconds

    return {
        "optimized_time_seconds": optimized_time,
        # ... other metrics
    }
```

## Benefits of Refactoring

### 1. Code Reduction
- **Eliminated 8 lines** of manual timing code from `determine_strategy_optimized`
- **Simplified 4 lines** of timing code in `benchmark_vs_original`
- **Centralized timing logic** in single reusable function

### 2. Improved Maintainability
- **Single Source of Truth**: All timing logic in one place
- **Consistent Behavior**: Same timing mechanism across all methods
- **Easy Updates**: Changes to timing logic only need to be made in one place

### 3. Enhanced Readability
- **Clear Intent**: `with time_operation(self.metrics):` clearly shows operation is being timed
- **Reduced Noise**: Less boilerplate code cluttering business logic
- **Better Structure**: Context manager provides clear boundaries for timed operations

### 4. Error Safety
- **Exception Handling**: `finally` block ensures timing is always recorded
- **Resource Management**: Context manager guarantees proper cleanup
- **Consistent Metrics**: Timing recorded even when operations fail

### 5. Flexibility
- **Cache Hit Support**: Optional parameter for different timing scenarios
- **Reusable**: Can be used throughout codebase for any timed operation
- **Extensible**: Easy to add additional timing features in future

## Usage Patterns

### Basic Operation Timing
```python
def some_operation(self):
    with time_operation(self.metrics):
        # Your operation code here
        result = complex_calculation()
        return result
```

### Cache Hit Timing
```python
def cached_operation(self, key):
    cached_result = self.cache.get(key)
    if cached_result:
        with time_operation(self.metrics, cache_hit=True):
            return cached_result

    with time_operation(self.metrics, cache_hit=False):
        result = expensive_computation()
        self.cache.put(key, result)
        return result
```

### Multiple Operations
```python
def multi_step_process(self):
    with time_operation(self.step1_metrics):
        step1_result = self.process_step1()

    with time_operation(self.step2_metrics):
        step2_result = self.process_step2(step1_result)

    return step2_result
```

## Implementation Details

### Import Requirements
```python
from contextlib import contextmanager
from typing import Generator
```

### Context Manager Signature
```python
def time_operation(
    metrics: PerformanceMetrics,
    cache_hit: bool = False
) -> Generator[None, None, None]:
```

### Exception Handling
```python
start_time = time.perf_counter()
try:
    yield  # Execute the wrapped code
finally:
    duration_ms = (time.perf_counter() - start_time) * 1000
    metrics.record_operation(duration_ms, cache_hit=cache_hit)
```

## Performance Impact

### Runtime Performance
- **No Overhead**: Context manager has negligible performance impact
- **Optimized**: Same `time.perf_counter()` calls as manual timing
- **Memory Efficient**: No additional memory allocation for timing

### Development Performance
- **Faster Development**: Less boilerplate code to write
- **Fewer Bugs**: Less manual timing code means fewer timing-related bugs
- **Easier Testing**: Consistent timing behavior makes testing more predictable

## Testing Benefits

### Unit Testing
```python
def test_operation_timing():
    """Test that operations are properly timed."""
    engine = DynamicLayoutEngine()

    # Reset metrics
    engine.metrics = PerformanceMetrics("test")

    with time_operation(engine.metrics):
        time.sleep(0.1)  # Simulate work

    assert engine.metrics.total_calls == 1
    assert engine.metrics.total_duration_ms >= 100  # At least 100ms
```

### Mock Testing
```python
def test_operation_with_mock_metrics():
    """Test timing with mock metrics."""
    mock_metrics = Mock()

    with time_operation(mock_metrics):
        result = some_operation()

    mock_metrics.record_operation.assert_called_once()
    args = mock_metrics.record_operation.call_args
    assert args[0][0] > 0  # Duration should be positive
```

## Comparison with Other Patterns

### Decorator Pattern
```python
# Alternative: Timing decorator
@time_operation_decorator
def some_method(self):
    # Method logic
    pass
```

**Context Manager Advantages:**
- More flexible - can time parts of methods
- Clearer boundaries of what's being timed
- Can be used with existing methods without modification

### Manual Timing
```python
# Manual timing approach
start = time.perf_counter()
try:
    result = operation()
finally:
    duration = time.perf_counter() - start
    metrics.record_operation(duration * 1000)
```

**Context Manager Advantages:**
- Less error-prone
- More readable
- Consistent across codebase
- Handles edge cases automatically

## Future Enhancements

### 1. Nested Timing
```python
@contextmanager
def nested_time_operation(metrics: PerformanceMetrics, operation_name: str):
    """Support for nested timing with operation names."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_named_operation(operation_name, duration_ms)
```

### 2. Conditional Timing
```python
@contextmanager
def conditional_time_operation(metrics: PerformanceMetrics, enabled: bool = True):
    """Only time operations when enabled."""
    if enabled:
        start_time = time.perf_counter()

    try:
        yield
    finally:
        if enabled:
            duration_ms = (time.perf_counter() - start_time) * 1000
            metrics.record_operation(duration_ms)
```

### 3. Threshold-Based Timing
```python
@contextmanager
def threshold_time_operation(metrics: PerformanceMetrics, min_duration_ms: float = 1.0):
    """Only record timing if operation exceeds threshold."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if duration_ms >= min_duration_ms:
            metrics.record_operation(duration_ms)
```

## Migration Guide

### Step 1: Add Context Manager
Add the `time_operation` context manager to your module.

### Step 2: Identify Timing Patterns
Look for these patterns in your code:
- `start_time = time.perf_counter()`
- `duration_ms = (time.perf_counter() - start_time) * 1000`
- `metrics.record_operation(duration_ms)`

### Step 3: Replace with Context Manager
Replace manual timing blocks with `with time_operation(metrics):`.

### Step 4: Update Imports
Add `from contextlib import contextmanager` if not already present.

### Step 5: Test
Verify that timing behavior is preserved after refactoring.

## References
- [Python Context Managers](https://docs.python.org/3/library/contextlib.html)
- [PEP 343 - The "with" Statement](https://www.python.org/dev/peps/pep-0343/)
- [contextlib.contextmanager](https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager)
