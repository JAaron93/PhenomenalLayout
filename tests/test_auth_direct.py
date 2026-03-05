#!/usr/bin/env python3
"""Test auth dependencies directly."""

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, AuthConfig

def test_auth_direct():
    """Test auth dependencies directly."""
    test_config = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key", 
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    # Create app with test configuration
    client = TestClient(create_app(test_config))
    
    # Create auth config for token generation
    auth_config = AuthConfig(test_config)
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN, auth_config)
    
    # Test the actual endpoint instead of dependency directly
    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    # Verify Content-Type header
    content_type = response.headers.get("Content-Type")
    assert content_type and "application/json" in content_type, (
        f"Expected application/json Content-Type, got {content_type}"
    )

    # Parse and validate response body
    response_json = response.json()
    assert isinstance(response_json, dict), (
        f"Expected dict response, got {type(response_json)}"
    )

    # Validate expected keys and their values
    success = response_json.get("success")
    assert success is True, f"Expected success=True, got {success}"

    data = response_json.get("data")
    assert data is not None, "Expected 'data' key in response"
    assert isinstance(data, dict), f"Expected data to be dict, got {type(data)}"

    message = response_json.get("message")
    assert message is not None, "Expected 'message' key in response"
    assert isinstance(message, str), (
        f"Expected message to be str, got {type(message)}"
    )

    # Validate data structure contains collected_objects
    assert "collected_objects" in data, (
        "Expected 'collected_objects' key in data"
    )
    collected = data["collected_objects"]
    assert isinstance(collected, int), (
        f"Expected collected_objects to be int, got {type(collected)}"
    )
    assert collected >= 0, (
        f"Expected collected_objects >= 0, got {collected}"
    )

if __name__ == "__main__":
    test_auth_direct()
