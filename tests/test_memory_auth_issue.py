#!/usr/bin/env python3
"""Directly test the memory endpoints without using the problematic fixture."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@contextmanager
def setup_test_client_with_env(test_env):
    """Helper context manager to set up a test client with specific environment variables.

    Args:
        test_env: Dictionary of environment variables to patch

    Yields:
        Tuple of (TestClient instance, enable_auth value from config)
    """
    with patch.dict("os.environ", test_env):
        # Preserve and remove relevant modules from sys.modules to ensure fresh import
        saved_modules = {}
        for module in list(sys.modules.keys()):
            if module.startswith("api.") or module == "app":
                saved_modules[module] = sys.modules.pop(module)

        try:
            # Import fresh modules with the patched environment
            from app import create_app

            with TestClient(create_app()) as client:
                print(
                    f"os.getenv('MEMORY_API_ENABLE_AUTH') = '{os.getenv('MEMORY_API_ENABLE_AUTH')}'"
                )
                # Defensive access to internal attribute
                enable_auth = None
                try:
                    auth_module = sys.modules.get("api.auth")
                    if auth_module is not None:
                        default_config = getattr(auth_module, "_default_config", None)
                        if default_config is not None:
                            enable_auth = getattr(default_config, "enable_auth", None)
                except AttributeError:
                    pass
                print(
                    f"sys.modules.get('api.auth')._default_config.enable_auth = {enable_auth}"
                )

                yield client, enable_auth
        finally:
            # Clean up any new modules imported during the test
            for module in list(sys.modules.keys()):
                if module.startswith("api.") or module == "app":
                    if module not in saved_modules:
                        del sys.modules[module]
            # Restore saved modules
            sys.modules.update(saved_modules)


@pytest.mark.parametrize(
    "test_env,expected_status",
    [
        (
            {
                "MEMORY_API_ENABLE_AUTH": "false",
                "MEMORY_API_JWT_SECRET": "test-secret",
                "MEMORY_API_KEY": "test-key",
            },
            200,
        ),
        (
            {
                "MEMORY_API_ENABLE_AUTH": "true",
                "MEMORY_API_JWT_SECRET": "test-secret",
                "MEMORY_API_KEY": "test-key",
            },
            401,
        ),
    ],
)
def test_endpoints_with_auth(test_env, expected_status):
    """Test endpoints with different authentication configurations.

    Args:
        test_env: Environment variables for the test case
        expected_status: Expected HTTP status code
    """
    auth_state = (
        "enabled" if test_env["MEMORY_API_ENABLE_AUTH"] == "true" else "disabled"
    )
    print(f"\n=== Test: Direct import with auth {auth_state} ===")

    with setup_test_client_with_env(test_env) as (client, enable_auth):
        # Test the endpoint
        response = client.get("/api/v1/memory/stats")
        print(f"\nGET /api/v1/memory/stats response: {response.status_code}")
        print(f"Response body: {response.text}")

        assert response.status_code == expected_status, (
            f"Expected status code {expected_status}, got {response.status_code}"
        )


if __name__ == "__main__":
    try:
        # Run tests with auth disabled
        with setup_test_client_with_env(
            {
                "MEMORY_API_ENABLE_AUTH": "false",
                "MEMORY_API_JWT_SECRET": "test-secret",
                "MEMORY_API_KEY": "test-key",
            }
        ) as (client, _):
            response = client.get("/api/v1/memory/stats")
            assert response.status_code == 200

        # Run tests with auth enabled
        with setup_test_client_with_env(
            {
                "MEMORY_API_ENABLE_AUTH": "true",
                "MEMORY_API_JWT_SECRET": "test-secret",
                "MEMORY_API_KEY": "test-key",
            }
        ) as (client, _):
            response = client.get("/api/v1/memory/stats")
            assert response.status_code == 401

        print("\n✅ All tests passed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback

        print(traceback.format_exc())
