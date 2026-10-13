#!/usr/bin/env python3
"""Test script to verify memory API authentication and rate limiting."""

import asyncio
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the project root to Python path
project_root = Path(__file__).resolve().parents[1] if '__file__' in globals() else Path('.').resolve()
sys.path.insert(0, str(project_root))

from fastapi import Request  # noqa: E402

import api.auth  # noqa: E402
import api.rate_limit  # noqa: E402


@pytest.fixture
def auth_module():
    """Fixture that provides auth module components with patched environment.

    This fixture imports and reloads api.auth with a patched environment,
    yields the necessary imports, and then restores original module state
    or removes the module so subsequent imports load with actual environment.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }

    with patch.dict('os.environ', test_env):
        # Import and reload auth module to pick up patched environment
        import api.auth
        import api.rate_limit
        sys.modules[api.auth.__name__] = api.auth
        sys.modules[api.rate_limit.__name__] = api.rate_limit

        importlib.reload(api.auth)
        importlib.reload(api.rate_limit)

        # Yield the needed components from the reloaded module
        yield (
            api.auth.UserRole,
            api.auth.create_jwt_token,
            api.auth.verify_api_key,
            api.auth.verify_jwt_token,
            api.auth.get_current_user,
            api.rate_limit.RateLimiter,
            api.rate_limit.TokenBucket,
            api.rate_limit.get_client_ip
        )

    # Reload after the patch context exits: importlib.reload mutates the
    # module in place, so restoring sys.modules entries is a no-op — the
    # reloaded state (including any env-derived constants) would leak to
    # every later test in this worker. Re-executing against the
    # session-default environment restores the constants tests expect.
    importlib.reload(api.auth)
    importlib.reload(api.rate_limit)


@pytest.fixture
def mock_api_key(monkeypatch):
    """Pytest fixture that sets up test API key and reloads auth module."""
    original_key = os.getenv("MEMORY_API_KEY")
    test_key = "test-api-key-12345"
    monkeypatch.setenv("MEMORY_API_KEY", test_key)

    # Reload auth module to pick up new environment variable
    import api.auth
    sys.modules[api.auth.__name__] = api.auth
    importlib.reload(api.auth)

    yield test_key

    # Reload with the pre-test key value restored: monkeypatch has not
    # undone its setenv yet at fixture teardown, so an unqualified reload
    # here would bake the test key into the module for later tests.
    if original_key is None:
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MEMORY_API_KEY", original_key)
    importlib.reload(api.auth)


@pytest.mark.usefixtures("auth_module")
def test_jwt_authentication():
    """Test JWT token creation and verification."""
    print("Testing JWT authentication...")
    user_role = api.auth.UserRole
    create_jwt_token = api.auth.create_jwt_token
    verify_jwt_token = api.auth.verify_jwt_token

    # Create token
    token = create_jwt_token("test_user", user_role.READ_ONLY)
    assert token is not None, "Token should be created"
    assert isinstance(token, str), "Token should be a string"

    # Verify token
    payload = verify_jwt_token(token)
    assert payload["user_id"] == "test_user", "User ID should match"
    assert payload["role"] == user_role.READ_ONLY, "Role should match"

    # Test admin token
    admin_token = create_jwt_token("admin_user", user_role.ADMIN)
    admin_payload = verify_jwt_token(admin_token)
    assert admin_payload["role"] == user_role.ADMIN, "Admin role should match"

    print("✓ JWT authentication test passed")


@pytest.mark.usefixtures("auth_module")
def test_api_key_authentication(mock_api_key):
    """Test API key authentication."""
    print("Testing API key authentication...")
    verify_api_key = api.auth.verify_api_key

    # Test valid key
    assert verify_api_key(mock_api_key) is True, "Valid API key should pass"

    # Test invalid key
    assert verify_api_key("invalid-key") is False, "Invalid API key should fail"

    print("✓ API key authentication test passed")


@pytest.mark.usefixtures("auth_module")
def test_rate_limiting():
    """Test rate limiting functionality."""
    print("Testing rate limiting...")
    token_bucket_cls = api.rate_limit.TokenBucket
    rate_limiter_cls = api.rate_limit.RateLimiter

    # Test token bucket
    bucket = token_bucket_cls(max_tokens=5, refill_rate=1.0)

    # Should allow initial requests
    for i in range(5):
        assert bucket.consume() is True, f"Request {i+1} should be allowed"

    # Should deny when bucket is empty
    assert bucket.consume() is False, "Request should be denied when bucket empty"

    # Test time until available
    retry_after = bucket.time_until_available(1.0)
    assert retry_after > 0, "Should have positive retry time"

    # Test rate limiter
    limiter = rate_limiter_cls()

    # Should allow first request
    allowed, retry_after = limiter.is_allowed("test_client", 5, 1.0)
    assert allowed is True, "First request should be allowed"
    assert retry_after == pytest.approx(0.0), "Retry after should be 0 for allowed request"

    # Should allow multiple requests up to limit
    for i in range(4):
        allowed, retry_after = limiter.is_allowed("test_client", 5, 1.0)
        assert allowed is True, f"Request {i+2} should be allowed"

    # Should deny when limit reached
    allowed, retry_after = limiter.is_allowed("test_client", 5, 1.0)
    assert allowed is False, "Request should be denied when limit reached"
    assert retry_after > 0, "Should have positive retry time"

    print("✓ Rate limiting test passed")


@pytest.mark.usefixtures("auth_module")
def test_client_ip_extraction():
    """Test client IP extraction from request."""
    print("Testing client IP extraction...")

    try:
        # All scenarios run under one trusted-proxy reload: the X-Forwarded-For
        # and X-Real-IP cases both require TRUST_FORWARDER_HEADERS=true, and the
        # fallback case uses a client outside the trusted-proxy list.
        with patch.dict(os.environ, {"TRUST_FORWARDER_HEADERS": "true"}):
            sys.modules["api.rate_limit"] = api.rate_limit
            importlib.reload(api.rate_limit)

            # Mock request with X-Forwarded-For header
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [(b"x-forwarded-for", b"192.168.1.100, 10.0.0.1")],
                "client": ("127.0.0.1", 8000),
            }
            request = Request(scope)

            ip = api.rate_limit.get_client_ip(request)
            assert ip == "192.168.1.100", "Should extract IP from X-Forwarded-For"

            # Mock request with X-Real-IP header
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [(b"x-real-ip", b"192.168.1.200")],
                "client": ("127.0.0.1", 8000),
            }
            request = Request(scope)

            ip = api.rate_limit.get_client_ip(request)
            assert ip == "192.168.1.200", "Should extract IP from X-Real-IP"

            # Mock request with no headers (fallback to client.host)
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [],
                "client": ("192.168.1.30", 8000),
            }
            request = Request(scope)

            ip = api.rate_limit.get_client_ip(request)
            assert ip == "192.168.1.30", "Should fallback to client.host"
    finally:
        # Restore default constants even when an assertion fails: the reload
        # above baked TRUST_FORWARDER_HEADERS=true into the module; later
        # tests expect the default (false) forwarded-header behavior.
        importlib.reload(api.rate_limit)

    print("✓ Client IP extraction test passed")


@pytest.mark.usefixtures("auth_module")
def test_jwt_tokens_with_auth_enabled():
    """Test JWT token creation and verification with auth enabled."""
    print("Testing JWT tokens with auth enabled...")
    user_role = api.auth.UserRole
    create_jwt_token = api.auth.create_jwt_token
    verify_jwt_token = api.auth.verify_jwt_token

    # Test JWT token creation
    read_token = create_jwt_token("read_user", user_role.READ_ONLY)
    admin_token = create_jwt_token("admin_user", user_role.ADMIN)

    assert read_token is not None, "Read token should be created"
    assert admin_token is not None, "Admin token should be created"

    # Verify tokens

    read_payload = verify_jwt_token(read_token)
    admin_payload = verify_jwt_token(admin_token)

    assert read_payload["role"] == user_role.READ_ONLY, "Read token should have read role"
    assert admin_payload["role"] == user_role.ADMIN, "Admin token should have admin role"

    print("✓ JWT tokens with auth enabled test passed")


def test_authentication_disabled():
    """Test behavior when authentication is disabled."""
    print("Testing authentication disabled...")

    # Set environment to disable auth, but also provide required secret to avoid error on reload
    with patch.dict(os.environ, {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }):
        # Reload the module to pick up new environment variable
        import api.auth
        sys.modules[api.auth.__name__] = api.auth
        importlib.reload(api.auth)

        # Mock request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "client": ("127.0.0.1", 8000),
        }
        request = Request(scope)

        # Should return anonymous user with admin role when auth disabled
        user = asyncio.run(api.auth.get_current_user(request, None, None))
        assert user["user_id"] == "anonymous", "Should return anonymous user"
        assert user["role"] == api.auth.UserRole.ADMIN, "Should have admin role when auth disabled"

    # Restore auth module to original state with proper environment variables
    with patch.dict(os.environ, {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }):
        sys.modules[api.auth.__name__] = api.auth
        importlib.reload(api.auth)

    print("✓ Authentication disabled test passed")


def test_rate_limit_configuration():
    """Test rate limit configuration from environment."""
    print("Testing rate limit configuration...")

    # Set custom rate limits
    test_env = {
        "MEMORY_API_READ_RATE_LIMIT": "120",
        "MEMORY_API_WRITE_RATE_LIMIT": "20",
        "MEMORY_API_ADMIN_RATE_LIMIT": "10"
    }

    try:
        with patch.dict(os.environ, test_env):
            # Reload the module to pick up new environment variable
            import api.rate_limit
            sys.modules[api.rate_limit.__name__] = api.rate_limit
            importlib.reload(api.rate_limit)

            from api.rate_limit import RATE_LIMITS, RATE_LIMITS_PER_SECOND

            assert RATE_LIMITS["read"] == 120, "Read rate limit should be 120"
            assert RATE_LIMITS["write"] == 20, "Write rate limit should be 20"
            assert RATE_LIMITS["admin"] == 10, "Admin rate limit should be 10"

            assert RATE_LIMITS_PER_SECOND["read"] == pytest.approx(2.0), "Read rate should be 2.0/sec"
            assert RATE_LIMITS_PER_SECOND["write"] == pytest.approx(20/60), "Write rate should be 0.33/sec"
            assert RATE_LIMITS_PER_SECOND["admin"] == pytest.approx(10/60), "Admin rate should be 0.17/sec"
    finally:
        # Restore default rate limits even when an assertion fails: the
        # reload above baked the test values (120/20/10) into the module
        # constants, and later tests — including the test_rate_limit.py
        # decorator tests — assert the 60/10/5 defaults. Runs outside the
        # env patch so the constants re-execute with default configuration.
        importlib.reload(api.rate_limit)

    print("✓ Rate limit configuration test passed")


if __name__ == "__main__":
    print("Testing Memory API Security Implementation...")
    print("=" * 50)

    try:
        test_jwt_authentication()

        # Test API key authentication with mock fixture
        # Manually set up the fixture environment for standalone test
        test_key = "test-api-key-12345"
        os.environ["MEMORY_API_KEY"] = test_key

        # Reload auth module to pick up environment variable
        import api.auth
        importlib.reload(api.auth)

        # Run the test logic directly
        print("Testing API key authentication...")
        assert api.auth.verify_api_key(test_key) is True, "Valid API key should pass"
        assert api.auth.verify_api_key("invalid-key") is False, "Invalid API key should fail"
        print("✓ API key authentication test passed")

        # Clean up environment
        os.environ.pop("MEMORY_API_KEY", None)
        importlib.reload(api.auth)

        test_rate_limiting()
        test_client_ip_extraction()
        test_jwt_tokens_with_auth_enabled()
        test_authentication_disabled()
        test_rate_limit_configuration()

        print("=" * 50)
        print("✅ All security tests passed!")
        print("\nSecurity features implemented:")
        print("- JWT authentication with role-based access")
        print("- API key authentication for admin operations")
        print("- Rate limiting with token bucket algorithm")
        print("- IP-based tracking and client IP extraction")
        print("- Configurable authentication (enable/disable)")
        print("- Environment-based configuration")
        print("- Proper error handling and logging")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
