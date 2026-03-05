#!/usr/bin/env python3
"""Test get_current_user function directly."""

from unittest.mock import patch
import pytest
from fastapi import HTTPException
import asyncio

def test_current_user():
    """Test get_current_user function directly."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key", 
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        # Force reload of auth module
        import importlib
        import api.auth
        
        importlib.reload(api.auth)
        
        # Rebind functions from reloaded module
        create_jwt_token = api.auth.create_jwt_token
        get_current_user = api.auth.get_current_user
        UserRole = api.auth.UserRole
        
        # Create admin token
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
        
        # Test get_current_user directly
        class MockRequest:
            def __init__(self, headers):
                self.headers = headers
        
        request = MockRequest(headers={"Authorization": f"Bearer {admin_token}"})
        
        with pytest.raises(HTTPException) as exc_info:
            # Passes None for credentials, skipping FastAPI's dependency injection which naturally expects a 401
            asyncio.run(get_current_user(request, None, None))
            
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"

if __name__ == "__main__":
    test_current_user()
