#!/usr/bin/env python3
"""Direct test of GC endpoint."""

from datetime import datetime
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, AuthConfig

def test_gc_direct():
    """Test GC endpoint directly."""
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
    
    # Test GC endpoint
    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    # Validate response structure
    response_json = response.json()
    assert isinstance(response_json, dict), (
        f"Expected dict response, got {type(response_json)}"
    )

    # Validate top-level keys
    assert response_json.get("success") is True, (
        f"Expected success=True, got {response_json.get('success')}"
    )
    assert "data" in response_json, "Expected 'data' key in response"
    assert "message" in response_json, "Expected 'message' key in response"

    # Validate data structure
    data = response_json.get("data")
    assert isinstance(data, dict), f"Expected data to be dict, got {type(data)}"
    assert "collected_objects" in data, (
        "Expected 'collected_objects' in data"
    )
    assert isinstance(data.get("collected_objects"), int), (
        f"Expected collected_objects to be int, "
        f"got {type(data.get('collected_objects'))}"
    )
    assert data.get("collected_objects") >= 0, (
        f"Expected collected_objects >= 0, "
        f"got {data.get('collected_objects')}"
    )

    # Validate timestamp
    assert "timestamp" in data, "Expected 'timestamp' in data"
    timestamp_value = data.get("timestamp")
    assert isinstance(timestamp_value, str), (
        f"Expected timestamp to be str, got {type(timestamp_value)}"
    )
    
    # Validate timestamp format by attempting to parse it
    try:
        # Handle 'Z' suffix for UTC if present (for robustness)
        ts_str = timestamp_value.replace('Z', '+00:00') if timestamp_value.endswith('Z') else timestamp_value
        datetime.fromisoformat(ts_str)
    except (ValueError, TypeError) as e:
        raise AssertionError(
            f"Failed to parse timestamp '{timestamp_value}' "
            f"as ISO format: {e}"
        )
    
    # Also test monitoring status to make sure it works
    response2 = client.get(
        "/api/v1/memory/monitoring/status",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response2.status_code == 200, f"Expected 200, got {response2.status_code}: {response2.text}"

if __name__ == "__main__":
    test_gc_direct()
