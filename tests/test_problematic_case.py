"""Test focusing on the problematic test case with proper fixture usage."""
import logging

import pytest


def test_problematic_case_fixed(
    reload_app_with_env,
):
    """Test the problematic scenario from the failing test."""
    auth_enabled = "false"

    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }

    client = reload_app_with_env(test_env)

    # Test endpoint - verify auth is disabled (public access)
    response = client.get('/api/v1/memory/stats')

    # Use logger for diagnostics only on failure
    logger = logging.getLogger(__name__)
    original_level = logger.level
    if response.status_code != 200:
        try:
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response text: {response.text}")
        finally:
            logger.setLevel(original_level)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}"
    )

    # Parse and validate response JSON content
    try:
        json_data = response.json()
    except Exception as e:
        pytest.fail(
            f"Failed to parse response as JSON: {e}. "
            f"Response text: {response.text}"
        )

    # Validate response is a dict
    assert isinstance(json_data, dict), (
        f"Expected response to be a dict, got {type(json_data).__name__}"
    )

    # Validate required keys exist
    assert "success" in json_data, (
        f"Response missing 'success' key: {json_data}"
    )
    assert "data" in json_data, (
        f"Response missing 'data' key: {json_data}"
    )
    assert "message" in json_data, (
        f"Response missing 'message' key: {json_data}"
    )

    # Validate expected types and values
    assert isinstance(json_data["success"], bool), (
        f"Expected 'success' to be bool, got "
        f"{type(json_data['success']).__name__}"
    )
    assert json_data["success"] is True, (
        f"Expected 'success' to be True, got {json_data['success']}"
    )
    assert isinstance(json_data["data"], dict), (
        f"Expected 'data' to be dict, got {type(json_data['data']).__name__}"
    )
    assert isinstance(json_data["message"], str), (
        f"Expected 'message' to be str, got "
        f"{type(json_data['message']).__name__}"
    )
