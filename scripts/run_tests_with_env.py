#!/usr/bin/env python3
"""Test runner that loads environment variables from .env file."""

import os
import subprocess
import sys

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Verify that the API key is loaded
api_key = os.getenv("LINGO_API_KEY")
if api_key and api_key.strip():
    print("✓ LINGO_API_KEY loaded successfully")
else:
    print("✗ LINGO_API_KEY not found or empty")
    # A missing API key only degrades the run; a hard exit can be wired here if tests require it.

# Run pytest with the loaded environment
if __name__ == "__main__":
    # Pass any command line arguments to pytest
    pytest_args = sys.argv[1:] if len(sys.argv) > 1 else ["tests/", "-v", "--tb=short"]

    # Run pytest
    try:
        # Run pytest with current environment (including loaded .env variables)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *pytest_args], env=os.environ.copy()
        )
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("✗ Error: pytest not found. Please install pytest first.")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error running pytest: {e}")
        sys.exit(1)
