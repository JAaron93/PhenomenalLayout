#!/usr/bin/env python3
"""Test that replicates pytest setup."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_pytest_behavior():
    """Test that replicates how pytest runs the test."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret",
        "MEMORY_API_KEY": "test-key",
    }

    with patch.dict("os.environ", test_env):
        # Capture complete sys.modules state to restore after test
        original_modules = sys.modules.copy()

        try:
            # Import fresh
            from app import create_app

            client = TestClient(create_app())

            import api.auth

            print("=== Module info ===")
            print("Module: api.auth")
            print(f"  id: {id(api.auth)}")
            print(f"  enable_auth: {api.auth.is_auth_enabled()}")
            print(f"  ANONYMOUS_USER: {api.auth.ANONYMOUS_USER}")

            # Test endpoint
            print("\n=== Testing endpoint ===")
            response = client.get("/api/v1/memory/stats")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text}")

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}"
            )
        finally:
            # Restore sys.modules to original state: remove only modules added
            # during test and restore any mutated originals
            added = set(sys.modules) - set(original_modules)
            for name in added:
                sys.modules.pop(name, None)
            for name in original_modules:
                sys.modules[name] = original_modules[name]


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-xvs"])
