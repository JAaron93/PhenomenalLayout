#!/usr/bin/env python3
"""Test focusing on the problematic test case with proper fixture usage."""

def test_problematic_case_fixed(reload_app_with_env):
    """Test the problematic scenario from the failing test with proper fixture usage."""
    auth_enabled = "false"
    print(f"Testing with auth_enabled={auth_enabled}")
    
    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }
    
    client = reload_app_with_env(test_env)
    
    # Check imported modules
    import api.auth
    print(f"\napi.auth module id: {id(api.auth)}")
    print(f"_default_config: {id(api.auth._default_config)}")
    print(f"enable_auth: {api.auth._default_config.enable_auth}")
    print(f"ANONYMOUS_USER: {api.auth.ANONYMOUS_USER}")
    
    # Test endpoint
    print(f"\nCalling /api/v1/memory/stats")
    response = client.get('/api/v1/memory/stats')
    
    print(f"Response status: {response.status_code}")
    print(f"Response text: {response.text}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
