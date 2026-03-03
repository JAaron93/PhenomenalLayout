#!/usr/bin/env python3
"""Run test with fresh Python process."""

import subprocess
import sys

# Run pytest with fresh Python process
result = subprocess.run([
    sys.executable, "-m", "pytest", 
    "test_memory_api_integration.py::test_memory_endpoints_with_auth",
    "-v", "-s", "--capture=no", "--tb=short"
], capture_output=False, text=True)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nReturn code: {result.returncode}")
