#!/usr/bin/env python3
"""Test file to validate Black and Ruff linting setup.

This file intentionally contains various Python constructs and formatting issues
that should trigger both Black formatting and Ruff linting rules.
"""

# Test imports (some unused, some unsorted)
import builtins
import contextlib

# Test long line that exceeds 88 characters (Black's default line length)
really_long_variable_name_that_should_trigger_line_length_formatting = "This is a very long string that will definitely exceed the 88 character limit set by Black"


# Test function with poor formatting
def poorly_formatted_function(arg1, arg2, _arg3=None):  # _arg3 unused to test ARG001
    """Docstring with trailing whitespace."""
    # Inconsistent indentation and spacing
    if arg1 == arg2:
        print("Equal values")
    else:
        print("Different values")  # inconsistent indentation (6 spaces instead of 8)

    # Dead code (Ruff F841)

    # Using deprecated syntax (for Ruff UP rules)
    f"arg1: {arg1}, arg2: {arg2}"  # Unused expression to test F841 (unused variable/expression)

    # Unnecessary parentheses
    return arg1 + arg2


# Test class with various issues
class TestClass:
    """Class docstring."""

    def __init__(self, value):
        """Initialize test class with value and unused attribute for linting tests.

        Args:
            value: The value to store in the instance for testing purposes.
        """
        self.value = value
        self.unused_attr = "unused"  # Ruff might flag this

    def method_with_complexity(self, x, y, z):
        """Test method with intentional complexity for linting demonstration."""
        # Complex conditional that could be simplified (Ruff SIM rules)
        if x:  # Should use 'if x:'
            if not y:  # Should use 'if not y:'
                if z is not None:  # Should use 'if z is not None:'
                    return True

        # Mutable default argument (Ruff B006)
        def inner_function(items=None):
            if items is None:
                items = []
            items.append(1)
            return items

        # Using bare except (Ruff E722)
        with contextlib.suppress(builtins.BaseException):
            pass

        return False


# Test list/dict comprehensions with poor formatting
messy_list = [i for i in range(10) if i % 2 == 0]
messy_dict = dict(zip(["a", "b", "c"], [1, 2, 3], strict=False))


# Test type annotations with poor spacing
def typed_function(
    _arg1: str, _arg2: int
) -> dict[str, list[int]] | None:  # Args unused to test ARG001
    """Function with type hints."""
    return None


# Test string concatenation that could use f-strings (Ruff UP rules)
name = "Test"
old_concat = "Hello " + name + "!"
old_format = f"Hello {name}!"

# Test comparison issues
value = 5
if value is None:  # Should use 'is None'
    pass
if isinstance(value, int):  # Should use isinstance()
    pass

# Test trailing whitespace and blank lines issues


# Too many blank lines above

# Missing final newline below
print("End of test file")
