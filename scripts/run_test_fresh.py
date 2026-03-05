#!/usr/bin/env python3
"""Run test with fresh Python process."""

import subprocess
import sys
from pathlib import Path

# Resolve test path relative to script location for stability regardless of CWD
test_file = (Path(__file__).parent / ".." / "tests" /
             "test_memory_api_integration.py")
test_target = str(test_file.resolve()) + "::test_memory_endpoints_with_auth"

# Run pytest with fresh Python process
result = subprocess.run([
    sys.executable, "-m", "pytest",
    test_target,
    "-v", "-s", "--tb=short"
], capture_output=True, text=True)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nReturn code: {result.returncode}")

# Propagate pytest exit code to ensure failures are surfaced
sys.exit(result.returncode)
