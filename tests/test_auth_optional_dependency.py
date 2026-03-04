"""Tests for optional dependency authentication functionality."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_env(monkeypatch):
    """Provide authentication environment variables for tests."""
    monkeypatch.setenv("MEMORY_API_JWT_SECRET", "test-secret-key-for-testing")
    monkeypatch.setenv("MEMORY_API_KEY", "test-admin-key-for-testing")
    monkeypatch.setenv("MEMORY_API_ENABLE_AUTH", "true")


class MockRequest:
    """Mock request for testing dependencies."""

    def __init__(self, headers):
        """Initialize mock request with headers."""
        self.headers = headers


@pytest.mark.asyncio
async def test_get_current_user_optional_dependency(auth_env):
    """Test the optional dependency function directly."""
    # Import after environment is set
    from api.auth import (
        UserRole,
        create_jwt_token,
        get_current_user_optional_dependency,
    )

    # Create read token
    read_token = create_jwt_token("read_user", UserRole.READ_ONLY)

    request = MockRequest({"Authorization": f"Bearer {read_token}"})

    # Test the optional dependency function
    user = await get_current_user_optional_dependency(request)

    # Verify the result
    assert user is not None
    assert user["user_id"] == "read_user"
    assert user["role"] == UserRole.READ_ONLY
    assert user["authenticated"] is True
    assert user["method"] == "jwt"


def test_optional_dependency_via_fastapi_client(auth_env):
    """Test optional dependency through FastAPI client."""
    # Import after environment is set
    from api.auth import UserRole, create_jwt_token
    from app import create_app

    app = create_app()

    # Create read token
    read_token = create_jwt_token("read_user", UserRole.READ_ONLY)

    # Test through FastAPI client with proper context management
    with TestClient(app) as client:
        response = client.get(
            '/api/v1/memory/stats',
            headers={'Authorization': f'Bearer {read_token}'}
        )

    # Verify the response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "current_memory_mb" in data["data"]


def test_optional_dependency_no_token(auth_env):
    """Test optional dependency with no authentication token."""
    from app import create_app

    app = create_app()
    with TestClient(app) as client:
        # Test without authentication token
        response = client.get('/api/v1/memory/stats')

        # Should fail with 401 Unauthorized when auth is enabled
        assert response.status_code == 401, (
            f"Expected 401 Unauthorized, got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_optional_dependency_invalid_token(auth_env):
    """Test optional dependency with invalid authentication token."""
    from api.auth import get_current_user_optional_dependency

    request = MockRequest({"Authorization": "Bearer invalid_token"})

    # Test with invalid token
    user = await get_current_user_optional_dependency(request)

    # Should return None for invalid token
    assert user is None
