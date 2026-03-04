#!/usr/bin/env python3
"""Debug authentication issue."""

from unittest.mock import patch


def test_auth_debug():
    """Debug authentication issue."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict("os.environ", test_env):
        import importlib
        import api.auth
        importlib.reload(api.auth)

        # Rebind names from reloaded module to reflect patched environment
        create_jwt_token = api.auth.create_jwt_token
        verify_jwt_token = api.auth.verify_jwt_token
        UserRole = api.auth.UserRole

        # Create tokens
        read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)

        print(f"Read token: {read_token}")
        print(f"Admin token: {admin_token}")

        # Test token verification
        try:
            payload = verify_jwt_token(read_token)
            print(f"Read token valid: {payload}")
        except Exception as e:
            print(f"Read token error: {e}")

        try:
            payload = verify_jwt_token(admin_token)
            print(f"Admin token valid: {payload}")
        except Exception as e:
            print(f"Admin token error: {e}")

if __name__ == "__main__":
    test_auth_debug()
