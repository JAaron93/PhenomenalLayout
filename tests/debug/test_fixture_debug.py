#!/usr/bin/env python3
"""Debug test to verify fixture behavior."""

import pytest


def test_fixture_debug(test_client):
    """Test that fixture is working correctly."""
    print(f"Test client type: {type(test_client)}")
    print(f"Test client value: {test_client}")

    # Make a simple request
    response = test_client.get("/api/v1/memory/stats")
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")

    # Assert expected behavior
    assert response.status_code == 401, (
        f"Expected 401 Unauthorized, got {response.status_code}"
    )

    response_json = response.json()
    success = response_json.get("success")
    error = response_json.get("error")
    message = response_json.get("message")

    assert success is not None, f"response missing 'success': {response_json}"
    assert error is not None, f"response missing 'error': {response_json}"
    assert message is not None, f"response missing 'message': {response_json}"

    assert not success, f"Expected success to be False, got {success}"
    assert error == "Unauthorized", (
        f"Expected 'Unauthorized' error, got {error}"
    )
    assert message == "Authentication required", (
        f"Expected 'Authentication required' message, got {message}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
