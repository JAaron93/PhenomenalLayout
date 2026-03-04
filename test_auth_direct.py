#!/usr/bin/env python3
"""Test auth dependencies directly."""

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, AuthConfig

def test_auth_direct():
    """Test auth dependencies directly."""
    test_config = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key", 
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    # Create app with test configuration
    client = TestClient(create_app(test_config))
    
    # Create auth config for token generation
    auth_config = AuthConfig(test_config)
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN, auth_config)
    
    # Test the actual endpoint instead of dependency directly
    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    # Add additional assertions based on expected response structure
    # e.g., assert "success" in response.json() or similar

if __name__ == "__main__":
    test_auth_direct()
