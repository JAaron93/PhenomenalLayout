#!/usr/bin/env python3
"""Test get_current_user function directly."""

import sys
from unittest.mock import patch
import importlib
import pytest
from fastapi import HTTPException


@pytest.fixture
def auth_module():
    """Fixture that provides auth module components with patched environment.

    This fixture imports and reloads api.auth with a patched environment,
    yields the necessary imports, and then reloads again to restore
    original state.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }

    # Store original module if it exists
    original_module = sys.modules.get('api.auth')

    with patch.dict('os.environ', test_env):
        # Import and reload auth module to pick up patched environment
        import api.auth

        importlib.reload(api.auth)

        # Yield the needed components from the reloaded module
        yield (
            api.auth.create_jwt_token,
            api.auth.get_current_user,
            api.auth.UserRole
        )

    # Restore original module state if it was previously loaded
    if original_module is not None:
        sys.modules['api.auth'] = original_module
    else:
        # Remove so next import loads with actual environment
        sys.modules.pop('api.auth', None)


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_credentials_none(auth_module):
    """Test get_current_user function directly."""
    create_jwt_token, get_current_user, UserRole = auth_module

    # Test get_current_user directly with no credentials
    class MockRequest:
        def __init__(self, headers=None):
            self.headers = headers or {}

    request = MockRequest()

    with pytest.raises(HTTPException) as exc_info:
        # Passes None for credentials to exercise the early 401 path
        await get_current_user(request, None, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
