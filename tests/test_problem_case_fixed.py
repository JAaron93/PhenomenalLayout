#!/usr/bin/env python3
"""Test focusing on the problematic test case with proper fixture usage."""

import pytest


@pytest.mark.parametrize("auth_enabled,expected_status", [
    ("false", 200),
    ("true", 401),
])
def test_problematic_case_fixed(
    reload_app_with_env, auth_enabled, expected_status
):
    """Test the problematic scenario with proper fixture usage.
    
    When auth is disabled (auth_enabled="false"), unauthenticated 
    requests should succeed.
    When auth is enabled (auth_enabled="true"), unauthenticated 
    requests should be rejected with 401.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }
    
    client = reload_app_with_env(test_env)
    
    # Check auth state via public API
    import api.auth
    if auth_enabled == "false":
        assert not api.auth.is_auth_enabled(), "Auth should be disabled"
        assert api.auth.ANONYMOUS_USER is not None
    else:
        assert api.auth.is_auth_enabled(), "Auth should be enabled"
    
    # Test endpoint
    response = client.get('/api/v1/memory/stats')
    
    assert response.status_code == expected_status, (
        f"Expected status {expected_status} but got {response.status_code}. "
        f"Response body: {response.text}"
    )
