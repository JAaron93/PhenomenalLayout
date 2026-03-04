#!/usr/bin/env python3
"""Direct test of GC endpoint."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole

def test_gc_direct():
    """Test GC endpoint directly."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key", 
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        # Force reload of all relevant modules
        import importlib
        import api.auth
        import api.memory_routes  
        import app
        
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        importlib.reload(app)
        
        client = TestClient(create_app())
        
        # Create admin token
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
        print(f"Admin token: {admin_token}")
        
        # Test GC endpoint
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"GC Response status: {response.status_code}")
        print(f"GC Response body: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Add more specific assertions based on expected response structure
        # e.g., assert "collected" in response.json()
        
        # Also test monitoring status to make sure it works
        response2 = client.get(
            "/api/v1/memory/monitoring/status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"Status Response status: {response2.status_code}")
        print(f"Status Response body: {response2.text}")
        
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}: {response2.text}"

if __name__ == "__main__":
    test_gc_direct()
