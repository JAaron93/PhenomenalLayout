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
            "MEMORY_API_ENABLE_AUTH": "true",
            "MEMORY_API_JWT_SECRET": "test-secret",
            "MEMORY_API_KEY": "test-key",
        }

        client1 = reload_app_with_env(test_env1)

        # Get the imported module
        auth_module1 = sys.modules.get("api.auth")
        assert auth_module1 is not None, "api.auth module not found in sys.modules"
        print(f"Module id: {id(auth_module1)}")
        assert hasattr(auth_module1, "_default_config"), (
            "api.auth module missing _default_config attribute"
        )
        config1 = auth_module1._default_config
        print(f"Config enable_auth: {config1.enable_auth}")

        # Test endpoint
        response1 = client1.get("/api/v1/memory/stats")
        print(f"Endpoint response: {response1.status_code} {response1.text}")

        assert response1.status_code == 401, "Expected 401 when auth is enabled"

        # Now test with auth disabled
        print("\nTest 2: Auth disabled")
        test_env2 = {
            "MEMORY_API_ENABLE_AUTH": "false",
            "MEMORY_API_JWT_SECRET": "test-secret",
            "MEMORY_API_KEY": "test-key",
        }

        client2 = reload_app_with_env(test_env2)

        # Check if module is different
        auth_module2 = sys.modules.get("api.auth")
        assert auth_module2 is not None, "api.auth module not found in sys.modules"
        print(f"Module id: {id(auth_module2)}")
        assert hasattr(auth_module2, "_default_config"), (
            "api.auth module missing _default_config attribute"
        )
        config2 = auth_module2._default_config
        print(f"Config enable_auth: {config2.enable_auth}")

        # Test endpoint
        response2 = client2.get("/api/v1/memory/stats")
        print(f"Endpoint response: {response2.status_code} {response2.text}")

        assert response2.status_code == 200, "Expected 200 when auth is disabled"

        print("\n✓ Fixture module reloading tested successfully!")
    finally:
        # Restore sys.modules to original state: remove only modules added
        # during test and restore any mutated originals.
        # numpy and gradio are intentionally excluded because they carry
        # C-extension/global runtime state and cannot be safely reloaded
        # in-process.
        excluded_top_level = {"numpy", "gradio"}

        added = set(sys.modules) - set(original_modules)
        for name in added:
            if any(
                name == pkg or name.startswith(f"{pkg}.") for pkg in excluded_top_level
            ):
                continue
            sys.modules.pop(name, None)
        for name in original_modules:
            if any(
                name == pkg or name.startswith(f"{pkg}.") for pkg in excluded_top_level
            ):
                continue
            sys.modules[name] = original_modules[name]
