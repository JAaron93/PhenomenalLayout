#!/usr/bin/env python3
"""Test to verify endpoint behavior with authentication disabled."""

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_endpoint_debugging():
    """Test that endpoints are accessible when authentication is disabled."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret",
        "MEMORY_API_KEY": "test-key",
    }
    # Order matters: dependencies (api.auth) must be reloaded before dependents
    modules_to_reload = ["api.auth", "api.memory_routes", "api.rate_limit", "app"]
    original_modules = {
        mod_name: sys.modules[mod_name]
        for mod_name in modules_to_reload
        if mod_name in sys.modules
    }

    try:
        with patch.dict("os.environ", test_env):
            # Use importlib.reload() for specific modules instead of deleting
            # all matching sys.modules
            for mod_name in modules_to_reload:
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])
                else:
                    # Import if not yet loaded
                    importlib.import_module(mod_name)

            from app import create_app

            with TestClient(create_app()) as client:
                # Import the auth module after app creation
                import api.auth

                assert not api.auth.is_auth_enabled(), (
                    "Authentication should be disabled"
                )

                # Try to access the endpoint
                response = client.get("/api/v1/memory/stats")
                assert response.status_code == 200, (
                    f"Expected status 200, got {response.status_code}"
                )

                # Verify response contains expected fields
                # (adjust based on actual API response)
                json_response = response.json()
                assert json_response["success"] is True, (
                    "Response should indicate success"
                )
                assert "data" in json_response, "Response should contain data field"
                data = json_response["data"]
                assert "current_memory_mb" in data, (
                    "Response should contain current_memory_mb"
                )
                assert "gc_stats" in data, "Response should contain gc_stats"

                # Check what's in sys.modules after request
                assert sys.modules["api.auth"] is api.auth, (
                    "Module reference should be consistent"
                )
                assert not sys.modules["api.auth"].is_auth_enabled(), (
                    "Authentication should still be disabled after request"
                )
    finally:
        for mod_name in modules_to_reload:
            if mod_name in original_modules:
                sys.modules[mod_name] = original_modules[mod_name]
            else:
                sys.modules.pop(mod_name, None)


if __name__ == "__main__":
    test_endpoint_debugging()
