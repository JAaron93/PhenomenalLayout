#!/usr/bin/env python3
"""Test that replicates pytest setup."""

import os
import sys
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

def test_pytest_behavior():
    """Test that replicates how pytest runs the test."""
    test_env = {
        'MEMORY_API_ENABLE_AUTH': 'false',
        'MEMORY_API_JWT_SECRET': 'test-secret',
        'MEMORY_API_KEY': 'test-key'
    }
    
    with patch.dict('os.environ', test_env):
        # Clean up
        for module in list(sys.modules.keys()):
            if module.startswith('api.') or module == 'app':
                del sys.modules[module]
        
        # Import fresh
        from app import create_app
        client = TestClient(create_app())
        
        import api.auth
        print(f"=== Module info ===")
        print(f"Module: api.auth")
        print(f"  id: {id(api.auth)}")
        print(f"  enable_auth: {api.auth._default_config.enable_auth}")
        print(f"  ANONYMOUS_USER: {api.auth.ANONYMOUS_USER}")
        
        # Test endpoint
        print(f"\n=== Testing endpoint ===")
        response = client.get('/api/v1/memory/stats')
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-xvs"])
