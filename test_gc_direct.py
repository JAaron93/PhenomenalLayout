#!/usr/bin/env python3
"""Direct test of GC endpoint."""

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, AuthConfig

def test_gc_direct():
    """Test GC endpoint directly."""
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
    
    # Test GC endpoint
    response = client.post(
        "/api/v1/memory/gc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    # Add more specific assertions based on expected response structure
    # e.g., assert "collected" in response.json()
    
    # Also test monitoring status to make sure it works
    response2 = client.get(
        "/api/v1/memory/monitoring/status",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response2.status_code == 200, f"Expected 200, got {response2.status_code}: {response2.text}"

if __name__ == "__main__":
    test_gc_direct()
