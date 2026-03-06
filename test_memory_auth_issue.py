#!/usr/bin/env python3
"""Directly test the memory endpoints without using the problematic fixture."""

import os
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient

def test_endpoints_with_auth_disabled():
    """Test endpoints with authentication disabled."""
    test_env = {
        'MEMORY_API_ENABLE_AUTH': 'false',
        'MEMORY_API_JWT_SECRET': 'test-secret',
        'MEMORY_API_KEY': 'test-key'
    }
    
    print("=== Test 1: Direct import with auth disabled ===")
    
    with patch.dict('os.environ', test_env):
        # Remove all relevant modules from sys.modules to ensure fresh import
        for module in list(sys.modules.keys()):
            if module.startswith('api.') or module == 'app':
                del sys.modules[module]
        
        # Import fresh modules with the patched environment
        from app import create_app
        client = TestClient(create_app())
        
        print(f"os.getenv('MEMORY_API_ENABLE_AUTH') = '{os.getenv('MEMORY_API_ENABLE_AUTH')}'")
        print(f"sys.modules['api.auth']._default_config.enable_auth = {sys.modules['api.auth']._default_config.enable_auth}")
        
        # Test the endpoint
        response = client.get('/api/v1/memory/stats')
        print(f"\nGET /api/v1/memory/stats response: {response.status_code}")
        print(f"Response body: {response.text}")
        
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        
def test_endpoints_with_auth_enabled():
    """Test endpoints with authentication enabled."""
    test_env = {
        'MEMORY_API_ENABLE_AUTH': 'true',
        'MEMORY_API_JWT_SECRET': 'test-secret',
        'MEMORY_API_KEY': 'test-key'
    }
    
    print("\n=== Test 2: Direct import with auth enabled ===")
    
    with patch.dict('os.environ', test_env):
        # Remove all relevant modules from sys.modules to ensure fresh import
        for module in list(sys.modules.keys()):
            if module.startswith('api.') or module == 'app':
                del sys.modules[module]
        
        # Import fresh modules with the patched environment
        from app import create_app
        client = TestClient(create_app())
        
        print(f"os.getenv('MEMORY_API_ENABLE_AUTH') = '{os.getenv('MEMORY_API_ENABLE_AUTH')}'")
        print(f"sys.modules['api.auth']._default_config.enable_auth = {sys.modules['api.auth']._default_config.enable_auth}")
        
        # Test the endpoint - should require authentication
        response = client.get('/api/v1/memory/stats')
        print(f"\nGET /api/v1/memory/stats response: {response.status_code}")
        print(f"Response body: {response.text}")
        
        assert response.status_code == 401, f"Expected status code 401, got {response.status_code}"

if __name__ == "__main__":
    try:
        test_endpoints_with_auth_disabled()
        test_endpoints_with_auth_enabled()
        print("\n✅ All tests passed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
