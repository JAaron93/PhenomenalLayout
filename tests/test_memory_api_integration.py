#!/usr/bin/env python3
"""Integration test for memory API endpoints with authentication."""

import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, verify_jwt_token, UserRole

# Module-level constant for test admin API key
TEST_ADMIN_API_KEY = "test-admin-key"


def _assert_success_response(resp, method: str, url: str) -> dict:
    """Assert response is successful and return parsed body.

    Validates:
    - status_code == 200
    - Response body is a dict
    - 'success' field exists and is a bool
    - 'success' field is True

    Args:
        resp: The response object from TestClient
        method: HTTP method for error messages
        url: Endpoint URL for error messages

    Returns:
        Parsed JSON body as dict for additional assertions
    """
    assert resp.status_code == 200, (
        f"{method} {url} should succeed: "
        f"status={resp.status_code}, body={resp.text}"
    )
    body = resp.json()
    assert isinstance(body, dict), (
        f"{method} {url} response should be a dict: {type(body)}"
    )
    assert "success" in body, (
        f"{method} {url} response missing 'success' field: {body}"
    )
    assert isinstance(body["success"], bool), (
        f"{method} {url} 'success' should be bool: {type(body['success'])}"
    )
    assert body["success"] is True, (
        f"{method} {url} response should indicate success: {body}"
    )
    return body


@pytest.fixture
def reload_app_with_env():
    """Fixture to reload modules with patched environment and cleanup after.

    Isolates environment changes by patching os.environ, reloading affected
    modules in dependency order, and restoring original modules after test.
    Yields a factory function that returns a fresh TestClient.
    """
    import importlib
    import sys

    # Modules to reload in dependency order (base → dependent)
    # Order matters: auth → rate_limit → memory_routes → app
    MODULE_NAMES = [
        "api.auth",
        "api.rate_limit",
        "api.memory_routes",
        "app",
    ]

    # Save original module objects before any reloads
    original_modules = {}
    for name in MODULE_NAMES:
        if name in sys.modules:
            original_modules[name] = sys.modules[name]

    def _factory(test_env: dict) -> TestClient:
        """Create TestClient with patched environment and reloaded modules."""
        with patch.dict("os.environ", test_env):
            # Reload modules in dependency order
            for name in MODULE_NAMES:
                if name not in sys.modules:
                    raise RuntimeError(f"Module {name} not loaded; cannot reload")
                importlib.reload(sys.modules[name])

            app_module = sys.modules["app"]
            return TestClient(app_module.create_app())

    try:
        yield _factory
    finally:
        # Restore original modules to prevent state leakage between tests
        for name in original_modules:
            sys.modules[name] = original_modules[name]


def test_memory_endpoints_with_auth(test_client, read_token, admin_token):
    """Test memory endpoints with authentication."""
    print(f"Testing memory endpoints with authentication...", flush=True)
    print(f"Using test_client: {type(test_client)}", flush=True)
    print(f"ENABLE_AUTH env: {os.getenv('MEMORY_API_ENABLE_AUTH')}", flush=True)
    
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
        headers={"X-API-Key": TEST_ADMIN_API_KEY}
    )
    assert response.status_code == 200, f"Stats endpoint should work with API key: {response.text}"

    # Test admin endpoint with API key
    response = test_client.post(
        "/api/v1/memory/gc",
        headers={"X-API-Key": TEST_ADMIN_API_KEY}
    )
    assert response.status_code == 200, f"GC endpoint should work with API key: {response.text}"
    
    # Test with invalid API key (should fail)
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401, f"Stats endpoint should fail with invalid API key: {response.text}"
    
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

    print("\n✓ All authentication tests passed!")


@pytest.mark.parametrize("auth_enabled", ["true", "false"])
def test_memory_endpoints_no_auth(reload_app_with_env, auth_enabled):
    """Test memory endpoints behave correctly with and without authentication.

    When auth is disabled (``auth_enabled="false"``), unauthenticated requests
    should succeed because the auth dependencies return an anonymous admin user.
    When auth is enabled (``auth_enabled="true"``), unauthenticated requests
    should be rejected with 401.
    """
    print(f"Testing memory endpoints with auth={auth_enabled}...")

    # Set environment for the desired auth mode
    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": TEST_ADMIN_API_KEY,
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }

    client = reload_app_with_env(test_env)

    # -- Read endpoints (use get_current_user_optional_dependency) --
    read_endpoints = [
        ("GET", "/api/v1/memory/stats"),
        ("GET", "/api/v1/memory/monitoring/status"),
    ]
    # -- Admin endpoints (use get_admin_user) --
    admin_endpoints = [
        ("POST", "/api/v1/memory/gc"),
        ("POST", "/api/v1/memory/monitoring/start"),
        ("POST", "/api/v1/memory/monitoring/stop"),
    ]

    if auth_enabled == "false":
        # Auth disabled – all endpoints should succeed without credentials
        # Expected response schema: {"success": bool, "data": dict, "message": str}
        for method, url in read_endpoints:
            resp = client.request(method, url)
            _assert_success_response(resp, method, url)

        for method, url in admin_endpoints:
            resp = client.request(method, url)
            _assert_success_response(resp, method, url)

    else:
        # Auth enabled – requests without credentials should be rejected
        for method, url in read_endpoints + admin_endpoints:
            resp = client.request(method, url)
            assert resp.status_code == 401, (
                f"{method} {url} should return 401 with auth enabled and "
                f"no credentials: status={resp.status_code}, body={resp.text}"
            )

    print(f"\n✓ Auth {'disabled' if auth_enabled == 'false' else 'enabled'} tests passed!")


@pytest.mark.parametrize("rate_limiting", ["true", "false"])
def test_rate_limiting_headers(rate_limiting):
    """Test rate limiting headers presence."""
    print(f"Testing rate limiting headers with rate limiting {rate_limiting}...")
    
    # Set up environment for testing
    test_env = {
        "MEMORY_API_ENABLE_RATE_LIMITING": rate_limiting,
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": TEST_ADMIN_API_KEY
    }

    client = reload_app_with_env(test_env)

    # Test rate limiting headers
    response = client.get("/api/v1/memory/stats")
    if rate_limiting == "true":
        assert "X-RateLimit-Limit" in response.headers, "Rate limiting headers should be present"
        assert "X-RateLimit-Remaining" in response.headers, "Rate limit remaining should be present"
    else:
        assert "X-RateLimit-Limit" not in response.headers, "Rate limiting headers should be absent"
        assert "X-RateLimit-Remaining" not in response.headers, "Rate limit remaining should be absent"

    print("\n✓ Rate limiting tests passed!")
