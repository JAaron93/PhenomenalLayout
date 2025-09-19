# CompiledPattern Consistency Validation

## Summary

Added `__post_init__` validation to the [`CompiledPattern`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_language_engine.py#L45-L74) dataclass to enforce consistency between optional regex patterns and their corresponding lists, preventing invalid combinations at initialization time.

## Problem Addressed

The [`CompiledPattern`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_language_engine.py#L45-L74) dataclass previously allowed inconsistent states where:
- `words_regex` could be `None` while `word_list` contained items
- `chars_regex` could be `None` while `char_list` contained items

These inconsistencies could lead to runtime errors or unexpected behavior in pattern matching logic.

## Solution Implemented

### Validation Logic

```python
def __post_init__(self) -> None:
    """Validate consistency between regex patterns and corresponding lists."""
    # Validate words_regex and word_list consistency
    if self.words_regex is None and len(self.word_list) > 0:
        raise ValueError(
            f"Inconsistent word pattern: words_regex is None but word_list "
            f"contains {len(self.word_list)} items. If no regex pattern is "
            f"provided, word_list must be empty."
        )

    # Validate chars_regex and char_list consistency  
    if self.chars_regex is None and len(self.char_list) > 0:
        raise ValueError(
            f"Inconsistent char pattern: chars_regex is None but char_list "
            f"contains {len(self.char_list)} items. If no regex pattern is "
            f"provided, char_list must be empty."
        )
```

### Validation Rules

1. **Word Pattern Consistency**
   - If `words_regex` is `None`, then `word_list` must be empty
   - If `words_regex` is provided, `word_list` may be empty or non-empty

2. **Character Pattern Consistency**
   - If `chars_regex` is `None`, then `char_list` must be empty
   - If `chars_regex` is provided, `char_list` may be empty or non-empty

3. **Error Handling**
   - Raises `ValueError` with clear, descriptive messages
   - Includes item counts for debugging
   - Explains the consistency requirement

## Valid Combinations

| words_regex | word_list | chars_regex | char_list | Valid | Notes |
|------------|-----------|-------------|-----------|-------|-------|
| `None` | `()` | `None` | `()` | ✅ | No patterns defined |
| `Pattern` | `()` | `None` | `()` | ✅ | Regex provided, lists optional |
| `Pattern` | `('a','b')` | `Pattern` | `('x','y')` | ✅ | Both patterns with lists |
| `None` | `('a','b')` | `None` | `()` | ❌ | Inconsistent word pattern |
| `None` | `()` | `None` | `('x','y')` | ❌ | Inconsistent char pattern |

## Testing Results

### Valid Pattern Creation
```bash
✓ Valid: None regex with empty lists
✓ Valid: Regex provided with non-empty lists
✓ Valid: Regex provided with empty lists (allowed)
```

### Invalid Pattern Rejection
```bash
✓ Correctly rejected: Inconsistent word pattern: words_regex is None but word_list...
✓ Correctly rejected: Inconsistent char pattern: chars_regex is None but char_list...
```

### Integration Testing
```bash
✓ Both words and chars: Compiled successfully
✓ Only words: Compiled successfully
✓ Only chars: Compiled successfully
✓ Neither words nor chars: Compiled successfully
```

## Benefits

1. **Early Error Detection**: Catches inconsistencies at initialization rather than runtime
2. **Clear Error Messages**: Descriptive `ValueError` messages aid debugging
3. **Data Integrity**: Enforces consistent internal state
4. **Type Safety**: Validates assumptions about pattern/list relationships
5. **Maintainability**: Prevents subtle bugs from inconsistent configurations

## Error Messages

The validation provides specific, actionable error messages:

```python
# For word pattern inconsistency
"Inconsistent word pattern: words_regex is None but word_list contains 2 items.
If no regex pattern is provided, word_list must be empty."

# For char pattern inconsistency  
"Inconsistent char pattern: chars_regex is None but char_list contains 3 items.
If no regex pattern is provided, char_list must be empty."
```

## Integration Points

The validation integrates seamlessly with:
- [`_compile_pattern()`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_language_engine.py#L305-L336) method in [`DynamicLanguageDetector`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_language_engine.py#L223-L674)
- Pattern creation from [`LANGUAGE_PATTERNS`](file:///Users/pretermodernist/PhenomenalLayout/services/language_detector.py) configuration
- Runtime pattern compilation and caching

The validation automatically prevents creation of [`CompiledPattern`](file:///Users/pretermodernist/PhenomenalLayout/core/dynamic_language_engine.py#L45-L74) instances with inconsistent regex/list combinations, ensuring robust language detection behavior throughout the system.
