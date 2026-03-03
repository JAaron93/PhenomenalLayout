#!/usr/bin/env python3
"""Integration test for memory API endpoints with authentication."""

import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, verify_jwt_token, UserRole

@pytest.fixture
def test_client():
    """Pytest fixture providing a test client with test environment."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100", 
        "MEMORY_API_ADMIN_RATE_LIMIT": "100"
    }
    
    with patch.dict('os.environ', test_env):
        # Reload modules to pick up environment
        import importlib
        import api.auth
        import api.memory_routes
        import api.rate_limit
        import app  # Also reload app to pick up changes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        importlib.reload(api.rate_limit)
        importlib.reload(app)
        
        # Create test client with patched environment
        client = TestClient(create_app())
        return client

@pytest.fixture
def read_token():
    """Pytest fixture providing a read-only token."""
    return create_jwt_token("read_user", UserRole.READ_ONLY)

@pytest.fixture
def admin_token():
    """Pytest fixture providing an admin token."""
    return create_jwt_token("admin_user", UserRole.ADMIN)

@pytest.mark.parametrize("user_role", ["read_only", "admin"])
def test_memory_endpoints_with_auth(test_client, user_role, read_token, admin_token):
    """Test memory endpoints with authentication."""
    print(f"Testing memory endpoints with {user_role} authentication...", flush=True)
    print(f"Using test_client: {type(test_client)}", flush=True)
    print(f"ENABLE_AUTH env: {os.getenv('MEMORY_API_ENABLE_AUTH')}", flush=True)
    
    # Get appropriate token
    if user_role == "read_only":
        token = read_token
    elif user_role == "admin":
        token = admin_token
    else:
        pytest.skip(f"Unsupported user role: {user_role}")
    
    # Test GET /memory/stats with read token
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    assert response.status_code == 200, f"Stats endpoint should work with read token: {response.text}"
    
    # Test GET /memory/stats with admin token
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Stats endpoint should work with admin token: {response.text}"
        
        # Test GET /memory/monitoring/status with read token
    response = test_client.get(
        "/api/v1/memory/monitoring/status",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 200, f"Status endpoint should work with read token: {response.text}"
        
        # Test POST /memory/gc with admin token
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"GC endpoint should work with admin token: {response.text}"
    
    # Test POST /memory/monitoring/start with admin token
    response = test_client.post(
        "/api/v1/memory/monitoring/start",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Start monitoring should work with admin token: {response.text}"
    
    # Test POST /memory/monitoring/stop with admin token
    response = test_client.post(
        "/api/v1/memory/monitoring/stop",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Stop monitoring should work with admin token: {response.text}"
    
    # Test admin endpoint with read token (should fail)
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 403, f"GC endpoint should fail with read token: {response.text}"
    
    # Test endpoint without auth (should fail)
    response = test_client.get("/api/v1/memory/stats")
    assert response.status_code == 401, f"Stats endpoint should fail without auth: {response.text}"
    
    # Test with API key
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"X-API-Key": "test-admin-key"}
    )
    assert response.status_code == 200, f"Stats endpoint should work with API key: {response.text}"
    
    # Test admin endpoint with API key
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"X-API-Key": "test-admin-key"}
    )
    assert response.status_code == 200, f"GC endpoint should work with API key: {response.text}"
    
    # Test with invalid API key (should fail)
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401, f"Stats endpoint should fail with invalid API key: {response.text}"
        
        # Test POST /memory/gc with read token (should fail)
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 403, f"GC endpoint should fail with read token: {response.text}"
    
    # Test POST /memory/gc with admin token (should succeed)
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Force GC should work with admin token: {response.text}"
    
    # Test POST /memory/monitoring/stop with read token (should fail)
    response = test_client.post(
        "/api/v1/memory/monitoring/stop",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 403, f"Stop monitoring should fail with read token: {response.text}"
    
    # Test POST /memory/monitoring/stop with admin token (should succeed)
    response = test_client.post(
        "/api/v1/memory/monitoring/stop",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Stop monitoring should work with admin token: {response.text}"
    
    # Test GET /memory/monitoring/status with read token
    response = test_client.get(
        "/api/v1/memory/monitoring/status",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 200, f"Status endpoint should work with read token: {response.text}"
    
    # Test GET /memory/monitoring/status with admin token
    response = test_client.get(
        "/api/v1/memory/monitoring/status",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Status endpoint should work with admin token: {response.text}"
    
    # Test POST /memory/monitoring/start with read token (should fail)
    response = test_client.post(
        "/api/v1/memory/monitoring/start",
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert response.status_code == 403, f"Start monitoring should fail with read token: {response.text}"
    
    # Test POST /memory/monitoring/start with admin token (should succeed)
    response = test_client.post(
        "/api/v1/memory/monitoring/start",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Start monitoring should work with admin token: {response.text}"
    
    print("\n✓ All authentication tests passed!")


@pytest.mark.parametrize("auth_enabled", ["true", "false"])
def test_memory_endpoints_no_auth(test_client, auth_enabled):
    """Test memory endpoints with authentication disabled."""
    print(f"Testing memory endpoints with auth={auth_enabled}...")
    
    # Set environment to disable auth
    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        # Reload modules
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)

@pytest.mark.parametrize("rate_limiting", ["enabled", "disabled"])
def test_rate_limiting_headers(test_client, rate_limiting, test_env):
    """Test rate limiting headers presence."""
    print(f"Testing rate limiting headers with rate limiting {rate_limiting}...")
    
    # Set up environment for testing
    test_env = {
        "MEMORY_API_ENABLE_RATE_LIMITING": rate_limiting,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        # Reload modules to pick up environment
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        # Create test client with patched environment
        client = TestClient(create_app())
        
        # Test rate limiting headers
        response = client.get("/api/v1/memory/stats")
        if rate_limiting == "enabled":
            assert "X-RateLimit-Limit" in response.headers, "Rate limiting headers should be present"
            assert "X-RateLimit-Remaining" in response.headers, "Rate limit remaining should be present"
        else:
            assert "X-RateLimit-Limit" not in response.headers, "Rate limiting headers should be absent"
            assert "X-RateLimit-Remaining" not in response.headers, "Rate limit remaining should be absent"
        
        print("\n✓ Rate limiting tests passed!")
