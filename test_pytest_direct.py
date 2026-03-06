#!/usr/bin/env python3
"""Test that replicates pytest setup."""

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
        # Capture specific modules to restore after test
        saved = {
            'api': sys.modules.pop('api', None),
            'api.auth': sys.modules.pop('api.auth', None),
            'api.routes': sys.modules.pop('api.routes', None),
            'api.memory_routes': sys.modules.pop('api.memory_routes', None),
            'app': sys.modules.pop('app', None)
        }

        try:
            # Import fresh
            from app import create_app
            client = TestClient(create_app())
            
            import api.auth
            print("=== Module info ===")
            print("Module: api.auth")
            print(f"  id: {id(api.auth)}")
            print(f"  enable_auth: {api.auth.is_auth_enabled()}")
            print(f"  ANONYMOUS_USER: {api.auth.ANONYMOUS_USER}")
            
            # Test endpoint
            print("\n=== Testing endpoint ===")
            response = client.get('/api/v1/memory/stats')
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text}")
            
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}"
            )
        finally:
            # Restore saved modules (only those that were actually present)
            sys.modules.update(
                {k: v for k, v in saved.items() if v is not None}
            )


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-xvs"])
