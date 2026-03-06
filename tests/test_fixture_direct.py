#!/usr/bin/env python3
"""Directly test the reload_app_with_env fixture."""

import sys


def test_fixture_module_reloading(reload_app_with_env):
    """Test that the fixture properly reloads modules."""

    # Save original sys.modules state to restore after test
    original_modules = sys.modules.copy()

    try:
        # First test with auth enabled
        print("Test 1: Auth enabled")
        test_env1 = {
            'MEMORY_API_ENABLE_AUTH': 'true',
            'MEMORY_API_JWT_SECRET': 'test-secret',
            'MEMORY_API_KEY': 'test-key'
        }

        client1 = reload_app_with_env(test_env1)

        # Get the imported module
        auth_module1 = sys.modules['api.auth']
        print(f"Module id: {id(auth_module1)}")
        config1 = auth_module1._default_config
        print(f"Config enable_auth: {config1.enable_auth}")

        # Test endpoint
        response1 = client1.get('/api/v1/memory/stats')
        print(f"Endpoint response: {response1.status_code} {response1.text}")

        assert response1.status_code == 401, \
            "Expected 401 when auth is enabled"

        # Now test with auth disabled
        print("\nTest 2: Auth disabled")
        test_env2 = {
            'MEMORY_API_ENABLE_AUTH': 'false',
            'MEMORY_API_JWT_SECRET': 'test-secret',
            'MEMORY_API_KEY': 'test-key'
        }

        client2 = reload_app_with_env(test_env2)

        # Check if module is different
        auth_module2 = sys.modules['api.auth']
        print(f"Module id: {id(auth_module2)}")
        config2 = auth_module2._default_config
        print(f"Config enable_auth: {config2.enable_auth}")

        # Test endpoint
        response2 = client2.get('/api/v1/memory/stats')
        print(f"Endpoint response: {response2.status_code} {response2.text}")

        assert response2.status_code == 200, \
            "Expected 200 when auth is disabled"

        print("\n✓ Fixture module reloading tested successfully!")
    finally:
        # Restore sys.modules to original state to prevent affecting other
        # tests
        sys.modules.clear()
        sys.modules.update(original_modules)


if __name__ == "__main__":
    try:
        test_fixture_module_reloading()
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)
