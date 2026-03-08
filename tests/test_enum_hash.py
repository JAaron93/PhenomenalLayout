import sys
from enum import Enum
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestEnum(Enum):
    VALUE1 = 1
    VALUE2 = 2


import sys
from enum import Enum
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.dynamic_programming import _normalize_value


class TestEnum(Enum):
    VALUE1 = 1
    VALUE2 = 2


class TestEnumHash:
    def test_enum_instances_are_hashable(self):
        """Verify that Enum instances can be used as dictionary keys."""
        hash_value = hash(TestEnum.VALUE1)
        assert isinstance(hash_value, int)

    def test_normalize_value_handles_enum(self):
        """Verify _normalize_value correctly processes Enum members."""
        result = _normalize_value(TestEnum.VALUE1)
        # Add appropriate assertion based on expected behavior
        assert result is not None  # Replace with actual expected value
