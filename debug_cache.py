#!/usr/bin/env python3

import sys

sys.path.append("/Users/pretermodernist/PhenomenalLayout")

from core.dynamic_programming import memoize

call_count = 0


@memoize(cache_size=5)
def test_func(x: int) -> int:
    global call_count
    call_count += 1
    print(f"Computing {x} (call #{call_count})")
    return x * x


def test_normalization():
    """Test the normalization function directly"""

    # Let me extract and test the normalization logic
    def _normalize_value(value):
        """Same logic as in the memoize decorator"""
        try:
            # Try to hash the value first - if it works, return as-is
            hash(value)
            return value
        except TypeError:
            # Value is unhashable, need to normalize it
            if isinstance(value, list):
                return tuple(_normalize_value(item) for item in value)
            elif isinstance(value, set):
                # Convert to sorted tuple for deterministic ordering
                try:
                    return tuple(sorted(_normalize_value(item) for item in value))
                except TypeError:
                    # Items might not be sortable, fall back to repr-based sorting
                    return tuple(
                        sorted((_normalize_value(item) for item in value), key=str)
                    )
            elif isinstance(value, dict):
                # Convert to tuple of sorted (key, value) pairs with recursive normalization
                normalized_items = []
                for k, v in sorted(value.items()):
                    normalized_items.append((_normalize_value(k), _normalize_value(v)))
                return tuple(normalized_items)
            elif hasattr(value, "__dataclass_fields__"):
                # Handle dataclass objects
                import dataclasses

                normalized_fields = []
                for field_obj in sorted(
                    dataclasses.fields(value), key=lambda f: f.name
                ):
                    field_name = field_obj.name
                    field_value = getattr(value, field_name)
                    normalized_fields.append(
                        (field_name, _normalize_value(field_value))
                    )
                return (value.__class__.__name__, tuple(normalized_fields))
            elif hasattr(value, "__dict__"):
                # Handle regular objects with __dict__
                normalized_attrs = []
                for k, v in sorted(value.__dict__.items()):
                    normalized_attrs.append((k, _normalize_value(v)))
                return (value.__class__.__name__, tuple(normalized_attrs))
            elif hasattr(value, "_name") and hasattr(value, "_value"):
                # Handle enum objects
                return (value.__class__.__name__, value._name, value._value)
            elif hasattr(value, "name") and hasattr(value, "value"):
                # Handle enum objects (alternative pattern)
                return (value.__class__.__name__, value.name, value.value)
            else:
                # For any other unhashable type, use repr as stable string representation
                return repr(value)

    # Test normalization with integers
    norm1 = _normalize_value(5)
    norm2 = _normalize_value(5)
    print(f"Normalized 5 (first time): {norm1}")
    print(f"Normalized 5 (second time): {norm2}")
    print(f"Are they equal? {norm1 == norm2}")
    print(f"Are they the same? {norm1 is norm2}")
    print(f"Hash 1: {hash(norm1)}")
    print(f"Hash 2: {hash(norm2)}")

    # Test cache key creation
    args1 = (5,)
    kwargs1 = {}
    normalized_args1 = tuple(_normalize_value(arg) for arg in args1)
    normalized_kwargs_items1 = []
    for k, v in sorted(kwargs1.items()):
        normalized_kwargs_items1.append((_normalize_value(k), _normalize_value(v)))
    normalized_kwargs1 = tuple(normalized_kwargs_items1)
    cache_key1 = (normalized_args1, normalized_kwargs1)

    args2 = (5,)
    kwargs2 = {}
    normalized_args2 = tuple(_normalize_value(arg) for arg in args2)
    normalized_kwargs_items2 = []
    for k, v in sorted(kwargs2.items()):
        normalized_kwargs_items2.append((_normalize_value(k), _normalize_value(v)))
    normalized_kwargs2 = tuple(normalized_kwargs_items2)
    cache_key2 = (normalized_args2, normalized_kwargs2)

    print(f"Cache key 1: {cache_key1}")
    print(f"Cache key 2: {cache_key2}")
    print(f"Cache keys equal? {cache_key1 == cache_key2}")


print("Testing normalization:")
test_normalization()

print("\nTesting memoized function:")
print("First call with 5:")
result1 = test_func(5)
print(f"Result: {result1}")

print("Second call with 5:")
result2 = test_func(5)
print(f"Result: {result2}")

print(f"Total calls: {call_count}")
print(f"Expected: 1, got: {call_count}")
