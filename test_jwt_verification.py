#!/usr/bin/env python3
"""Test JWT token verification directly."""

from unittest.mock import patch
from api.auth import create_jwt_token, verify_jwt_token, UserRole

def test_jwt_verification():
    """Test JWT token verification directly."""
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
        
        # Create admin token
        user_id = "admin_user"
        role = api.auth.UserRole.ADMIN
        admin_token = api.auth.create_jwt_token(user_id, role)
        
        # Test verification directly
        payload = api.auth.verify_jwt_token(admin_token)
        
        # Proper assertions
        assert payload["user_id"] == user_id
        assert payload["role"] == role
        assert "exp" in payload
        assert "iat" in payload
        assert payload["type"] == "access"
        
        print("✓ JWT verification test passed with proper assertions")

if __name__ == "__main__":
    test_jwt_verification()
