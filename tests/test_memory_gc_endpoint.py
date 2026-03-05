#!/usr/bin/env python3
"""Direct test of GC endpoint."""

import sys
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
        # Python 3.11+ has native 'Z' support; 3.10 and below need workaround
        if sys.version_info < (3, 11) and timestamp_value.endswith('Z'):
            ts_str = timestamp_value[:-1] + '+00:00'
        else:
            ts_str = timestamp_value
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

    assert response2.status_code == 200, (
        f"Expected 200, got {response2.status_code}: {response2.text}"
    )

    # Validate monitoring status response structure
    status_json = response2.json()
    assert isinstance(status_json, dict), (
        f"Expected dict response, got {type(status_json)}"
    )

    # Validate top-level keys
    assert status_json.get("success") is True, (
        f"Expected success=True, got {status_json.get('success')}"
    )
    assert "data" in status_json, "Expected 'data' key in response"
    assert "message" in status_json, "Expected 'message' key in response"
    assert isinstance(status_json.get("message"), str), (
        f"Expected message to be str, got {type(status_json.get('message'))}"
    )

    # Validate data structure
    status_data = status_json.get("data")
    assert isinstance(status_data, dict), (
        f"Expected data to be dict, got {type(status_data)}"
    )

    # Validate monitoring flag (boolean)
    assert "monitoring" in status_data, (
        f"Response missing 'monitoring': {status_data}"
    )
    assert isinstance(status_data.get("monitoring"), bool), (
        f"Expected monitoring to be bool, got {type(status_data.get('monitoring'))}"
    )

    # Validate check_interval (float/int)
    assert "check_interval" in status_data, (
        f"Response missing 'check_interval': {status_data}"
    )
    assert isinstance(status_data.get("check_interval"), (int, float)), (
        f"Expected check_interval to be numeric, "
        f"got {type(status_data.get('check_interval'))}"
    )
    assert status_data.get("check_interval") > 0, (
        f"Expected check_interval > 0, got {status_data.get('check_interval')}"
    )

    # Validate alert_threshold_mb (float/int)
    assert "alert_threshold_mb" in status_data, (
        f"Response missing 'alert_threshold_mb': {status_data}"
    )
    assert isinstance(status_data.get("alert_threshold_mb"), (int, float)), (
        f"Expected alert_threshold_mb to be numeric, "
        f"got {type(status_data.get('alert_threshold_mb'))}"
    )
    assert status_data.get("alert_threshold_mb") > 0, (
        f"Expected alert_threshold_mb > 0, got {status_data.get('alert_threshold_mb')}"
    )

    # Validate baseline_memory_mb (float/int or None if not started)
    assert "baseline_memory_mb" in status_data, (
        f"Response missing 'baseline_memory_mb': {status_data}"
    )
    baseline_val = status_data.get("baseline_memory_mb")
    assert baseline_val is None or isinstance(baseline_val, (int, float)), (
        f"Expected baseline_memory_mb to be numeric or None, "
        f"got {type(baseline_val)}"
    )
    if baseline_val is not None:
        assert baseline_val >= 0, (
            f"Expected baseline_memory_mb >= 0, got {baseline_val}"
        )

    # Validate peak_memory_mb (float/int or 0.0 if not started)
    assert "peak_memory_mb" in status_data, (
        f"Response missing 'peak_memory_mb': {status_data}"
    )
    peak_val = status_data.get("peak_memory_mb")
    assert isinstance(peak_val, (int, float)), (
        f"Expected peak_memory_mb to be numeric, got {type(peak_val)}"
    )
    assert peak_val >= 0, f"Expected peak_memory_mb >= 0, got {peak_val}"

if __name__ == "__main__":
    test_gc_direct()
