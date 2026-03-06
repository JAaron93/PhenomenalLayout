#!/usr/bin/env python3
"""Test auth dependencies directly."""

import importlib
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

# Shared test configuration for all auth tests
TEST_CONFIG = {
    "MEMORY_API_ENABLE_AUTH": "true",
    "MEMORY_API_JWT_SECRET": "test-secret-key",
    "MEMORY_API_KEY": "test-admin-key"
}


@pytest.fixture
def auth_module():
    """Fixture that provides auth module components with patched environment.

    This fixture imports and reloads api.auth with a patched environment,
    yields the necessary imports, and then restores original module state
    or removes the module so subsequent imports load with actual environment.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }

    # Store original module if it exists
    original_auth_module = sys.modules.get('api.auth')
    original_app_module = sys.modules.get('app')

    with patch.dict('os.environ', test_env):
        # Import and reload auth module to pick up patched environment
        import api.auth
        import app

        importlib.reload(api.auth)
        importlib.reload(app)

        # Yield the needed components from the reloaded module
        yield (
            api.auth.AuthConfig,
            api.auth.UserRole,
            api.auth.create_jwt_token,
            app.create_app
        )

    # Restore original module state if it was previously loaded
    if original_auth_module is not None:
        sys.modules['api.auth'] = original_auth_module
    else:
        # Remove so next import loads with actual environment
        sys.modules.pop('api.auth', None)
        
    if original_app_module is not None:
        sys.modules['app'] = original_app_module
    else:
        # Remove so next import loads with actual environment
        sys.modules.pop('app', None)


def test_auth_direct(auth_module):
    """Test auth dependencies directly."""
    AuthConfig, UserRole, create_jwt_token, create_app = auth_module
    
    # Create app with test configuration
    client = TestClient(create_app(TEST_CONFIG))

    # Create auth config for token generation
    auth_config = AuthConfig(TEST_CONFIG)

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
    assert isinstance(data, dict), "Expected data to be dict"

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


def test_auth_no_header(auth_module):
    """Test that missing Authorization header returns 401."""
    _, _, _, create_app = auth_module
    client = TestClient(create_app(TEST_CONFIG))

    response = client.post("/api/v1/memory/gc")

    assert response.status_code == 401, (
        f"Expected 401, got {response.status_code}: {response.text}"
    )


def test_auth_malformed_jwt(auth_module):
    """Test that malformed/invalid JWT returns 401."""
    create_app = auth_module[3]
    client = TestClient(create_app(TEST_CONFIG))

    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": "Bearer invalid-token-string"}
    )

    assert response.status_code == 401, (
        f"Expected 401, got {response.status_code}: {response.text}"
    )


def test_auth_expired_token(auth_module):
    """Test that expired JWT returns 401."""
    AuthConfig, UserRole, create_jwt_token, create_app = auth_module
    client = TestClient(create_app(TEST_CONFIG))
    auth_config = AuthConfig(TEST_CONFIG)

    # Create an expired token (expired 1 hour ago)
    expiration = datetime.now(UTC) - timedelta(hours=1)
    payload = {
        "user_id": "test_user",
        "role": UserRole.ADMIN,
        "exp": expiration,
        "iat": expiration - timedelta(hours=1),
        "type": "access"
    }
    expired_token = jwt.encode(
        payload, auth_config.jwt_secret, algorithm="HS256"
    )

    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401, (
        f"Expected 401, got {response.status_code}: {response.text}"
    )


if __name__ == "__main__":
    test_auth_direct()
    test_auth_no_header()
    test_auth_malformed_jwt()
    test_auth_expired_token()
    print("\nAll auth tests passed!")
