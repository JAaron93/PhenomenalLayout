import sys
from enum import Enum
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestEnum(Enum):
    VALUE1 = 1
    VALUE2 = 2


# Test if Enum instances are hashable
try:
    hash(TestEnum.VALUE1)
    print("Enum instances are hashable")
except TypeError:
    print("Enum instances are NOT hashable")

# Test what _normalize_value returns for an Enum
from core.dynamic_programming import _normalize_value

result = _normalize_value(TestEnum.VALUE1)
print(f"_normalize_value returned: {result}")
print(f"Type: {type(result)}")
