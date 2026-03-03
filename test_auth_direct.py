#!/usr/bin/env python3
"""Test auth dependencies directly."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_admin_user

def test_auth_direct():
    """Test auth dependencies directly."""
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
        
        # Test the actual endpoint instead of dependency directly
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"GC endpoint test - Status: {response.status_code}")
        print(f"GC endpoint test - Body: {response.text}")

if __name__ == "__main__":
    test_auth_direct()
