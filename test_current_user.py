#!/usr/bin/env python3
"""Test get_current_user function directly."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_current_user

def test_current_user():
    """Test get_current_user function directly."""
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
        
        # Test get_current_user directly
        from fastapi import Request
        
        class MockRequest:
            def __init__(self, headers):
                self.headers = headers
        
        request = MockRequest(headers={"Authorization": f"Bearer {admin_token}"})
        
        import pytest
        from fastapi import HTTPException
        import asyncio
        
        with pytest.raises(HTTPException) as exc_info:
            # Passes None for credentials, skipping FastAPI's dependency injection which naturally expects a 401
            asyncio.run(get_current_user(request, None, None))
            
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"

if __name__ == "__main__":
    test_current_user()
