#!/usr/bin/env python3
"""Debug test to isolate authentication issue."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole

def test_auth_debug():
    """Debug authentication issue."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        client = TestClient(create_app())
        
        # Create tokens
        read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
        
        print(f"Read token: {read_token}")
        print(f"Admin token: {admin_token}")
        
        # Test 1: GET /memory/stats with read token
        print("\n=== Test 1: GET /memory/stats with read token ===")
        response1 = client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        print(f"Response 1 status: {response1.status_code}")
        print(f"Response 1 body: {response1.text}")
        
        # Test 2: GET /memory/stats with admin token
        print("\n=== Test 2: GET /memory/stats with admin token ===")
        response2 = client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Response 2 status: {response2.status_code}")
        print(f"Response 2 body: {response2.text}")
        
        # Test 3: GET /memory/monitoring/status with read token
        print("\n=== Test 3: GET /memory/monitoring/status with read token ===")
        response3 = client.get(
            "/api/v1/memory/monitoring/status",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        print(f"Response 3 status: {response3.status_code}")
        print(f"Response 3 body: {response3.text}")

if __name__ == "__main__":
    test_auth_debug()
