#!/usr/bin/env python3
"""Simple test to verify fixture is working."""

import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole

@pytest.fixture
def test_client():
    """Pytest fixture providing a test client with test environment."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        import importlib
        import api.auth
        importlib.reload(api.auth)
        
        client = TestClient(create_app())
        print(f"Created test client: {type(client)}")
        print(f"ENABLE_AUTH in fixture: {os.getenv('MEMORY_API_ENABLE_AUTH')}")
        return client

def test_simple_endpoint(test_client):
    """Test simple endpoint to verify auth is working."""
    print(f"ENABLE_AUTH in test: {os.getenv('MEMORY_API_ENABLE_AUTH')}")
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token: {admin_token}")
    
    # Test GET /memory/stats with admin token
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    assert response.status_code == 200
