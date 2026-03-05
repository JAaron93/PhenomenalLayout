#!/usr/bin/env python3
"""Test JWT token verification directly."""

import importlib
import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def auth_setup():
    """Fixture that sets up auth module with patched environment.
    
    This fixture:
    1. Patches os.environ with required environment variables
    2. Reloads api.auth to pick up the patched environment
    3. Yields the module and necessary functions/classes
    4. Reloads api.auth again in teardown to restore original state
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    # Save the original module if it exists
    original_module = sys.modules.get('api.auth')
    
    with patch.dict('os.environ', test_env):
        # Reload to pick up patched environment
        import api.auth
        importlib.reload(api.auth)
        
        # Yield the module and its exports for tests
        yield {
            'module': api.auth,
            'create_jwt_token': api.auth.create_jwt_token,
            'verify_jwt_token': api.auth.verify_jwt_token,
            'UserRole': api.auth.UserRole
        }
        
        # Teardown: reload to restore original state
        importlib.reload(api.auth)
    
    # Restore the original module in sys.modules if it existed
    if original_module is not None:
        sys.modules['api.auth'] = original_module
    elif 'api.auth' in sys.modules:
        # Remove if it didn't exist before
        del sys.modules['api.auth']


def test_jwt_verification(auth_setup):
    """Test JWT token verification directly."""
    # Get the functions/classes from the fixture
    create_jwt_token = auth_setup['create_jwt_token']
    verify_jwt_token = auth_setup['verify_jwt_token']
    UserRole = auth_setup['UserRole']
    
    # Create admin token
    user_id = "admin_user"
    role = UserRole.ADMIN
    admin_token = create_jwt_token(user_id, role)
    
    # Test verification directly
    payload = verify_jwt_token(admin_token)
    
    # Proper assertions
    assert payload["user_id"] == user_id
    assert payload["role"] == role
    assert "exp" in payload
    assert "iat" in payload
    assert payload["type"] == "access"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
