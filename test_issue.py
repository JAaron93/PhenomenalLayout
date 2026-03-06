#!/usr/bin/env python3
"""Test script to reproduce the issue with authentication disabled."""

import os
from unittest.mock import patch
from fastapi.testclient import TestClient

import sys

def test_authentication_disabled():
    """Test that endpoints work without authentication when MEMORY_API_ENABLE_AUTH is 'false'."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }

    # Clear and reload modules to test with the new environment
    for module in list(sys.modules.keys()):
        if module.startswith("api.") or module == "app":
            del sys.modules[module]

    with patch.dict("os.environ", test_env):
        # Import modules after environment is patched
        from app import create_app
        client = TestClient(create_app())

        # Test endpoints without authentication
        print("Testing without authentication...")
        
        # Test read endpoints
        read_endpoints = [
            ("/api/v1/memory/stats", "GET"),
            ("/api/v1/memory/monitoring/status", "GET"),
        ]
        
        for url, method in read_endpoints:
            response = client.get(url)
            print(f"\n{method} {url}")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            assert response.status_code == 200, f"Expected 200 for {url}, got {response.status_code}"
        
        # Test admin endpoints
        admin_endpoints = [
            ("/api/v1/memory/gc", "POST"),
            ("/api/v1/memory/monitoring/start", "POST"),
            ("/api/v1/memory/monitoring/stop", "POST"),
        ]
        
        for url, method in admin_endpoints:
            if method == "POST":
                response = client.post(url)
            else:
                response = client.get(url)
                
            print(f"\n{method} {url}")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            assert response.status_code == 200, f"Expected 200 for {url}, got {response.status_code}"
        
        print("\n✓ All tests passed!")
        return True

if __name__ == "__main__":
    try:
        test_authentication_disabled()
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
