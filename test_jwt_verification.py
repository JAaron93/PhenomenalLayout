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
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
        print(f"Admin token: {admin_token}")
        
        # Test verification directly
        try:
            payload = verify_jwt_token(admin_token)
            print(f"JWT verification result: {payload}")
        except Exception as e:
            print(f"JWT verification error: {e}")

if __name__ == "__main__":
    test_jwt_verification()
