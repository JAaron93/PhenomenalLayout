#!/usr/bin/env python3
"""Debug dependency injection issue."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import get_current_user_dependency

def test_dependency():
    """Debug dependency injection issue."""
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
        
        # Create admin token
        import jwt
        admin_token = jwt.encode(
            {
                "user_id": "admin_user",
                "role": "admin",
                "exp": 1772596372,
                "iat": 1772509972,
                "type": "access"
            },
            "test-secret-key",
            algorithm="HS256"
        )
        
        print(f"Admin token: {admin_token}")
        
        # Test dependency directly
        from fastapi import Request
        
        # Create a mock request
        class MockRequest:
            def __init__(self, headers):
                self.headers = headers
        
        request = MockRequest(headers={"Authorization": f"Bearer {admin_token}"})
        
        try:
            user = get_current_user_dependency(request)
            print(f"User from dependency: {user}")
        except Exception as e:
            print(f"Dependency error: {e}")

if __name__ == "__main__":
    test_dependency()
