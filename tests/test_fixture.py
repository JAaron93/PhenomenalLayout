#!/usr/bin/env python3
"""Test to verify reload_app_with_env fixture behavior."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_reload_fixture(reload_app_with_env):
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }

    client = reload_app_with_env(test_env)

    # Verify environment variable is set as expected
    assert os.getenv("MEMORY_API_ENABLE_AUTH") == "false", (
        "MEMORY_API_ENABLE_AUTH should be set to 'false'"
    )

    # Call the stats endpoint and verify response
    response = client.get("/api/v1/memory/stats")

    # Verify status code
    assert response.status_code == 200, (
        f"Expected status 200, got {response.status_code}"
    )

    # Parse and validate JSON response
    response_data = response.json()

    # Verify expected keys in response
    assert "success" in response_data, "Response should contain 'success' key"
    assert response_data["success"] is True, "success should be True"
    assert "data" in response_data, "Response should contain 'data' key"
    assert "message" in response_data, "Response should contain 'message' key"
