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

from fastapi import Request

from api.auth import UserRole, create_jwt_token, verify_api_key, verify_jwt_token
from api.rate_limit import RateLimiter, TokenBucket, get_client_ip


@pytest.fixture
def mock_api_key(monkeypatch):
    """Pytest fixture that sets up test API key and reloads auth module."""
    test_key = "test-api-key-12345"
    monkeypatch.setenv("MEMORY_API_KEY", test_key)

    # Reload the auth module to pick up new environment variable
    import api.auth
    importlib.reload(api.auth)

    yield test_key

    # Reload auth module to pick up restored environment
    importlib.reload(api.auth)


def test_jwt_authentication():
    """Test JWT token creation and verification."""
    print("Testing JWT authentication...")

    # Create token
    token = create_jwt_token("test_user", UserRole.READ_ONLY)
    assert token is not None, "Token should be created"
    assert isinstance(token, str), "Token should be a string"

    # Verify token
    payload = verify_jwt_token(token)
    assert payload["user_id"] == "test_user", "User ID should match"
    assert payload["role"] == UserRole.READ_ONLY, "Role should match"

    # Test admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    admin_payload = verify_jwt_token(admin_token)
    assert admin_payload["role"] == UserRole.ADMIN, "Admin role should match"

    print("✓ JWT authentication test passed")


def test_api_key_authentication(mock_api_key):
    """Test API key authentication."""
    print("Testing API key authentication...")

    # Import verify_api_key from the reloaded auth module

    # Test valid key
    assert verify_api_key(mock_api_key) is True, "Valid API key should pass"

    # Test invalid key
    assert verify_api_key("invalid-key") is False, "Invalid API key should fail"

    print("✓ API key authentication test passed")


def test_rate_limiting():
    """Test rate limiting functionality."""
    print("Testing rate limiting...")

    # Test token bucket
    bucket = TokenBucket(max_tokens=5, refill_rate=1.0)

    # Should allow initial requests
    for i in range(5):
        assert bucket.consume() is True, f"Request {i+1} should be allowed"

    # Should deny when bucket is empty
    assert bucket.consume() is False, "Request should be denied when bucket empty"

    # Test time until available
    retry_after = bucket.time_until_available(1.0)
    assert retry_after > 0, "Should have positive retry time"

    # Test rate limiter
    limiter = RateLimiter()

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


def test_client_ip_extraction():
    """Test client IP extraction from request."""
    print("Testing client IP extraction...")

    # Mock request with X-Forwarded-For header
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(b"x-forwarded-for", b"192.168.1.100, 10.0.0.1")],
        "client": ("127.0.0.1", 8000),
    }
    request = Request(scope)

    ip = get_client_ip(request)
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

    ip = get_client_ip(request)
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

    ip = get_client_ip(request)
    assert ip == "192.168.1.30", "Should fallback to client.host"

    print("✓ Client IP extraction test passed")


def test_jwt_tokens_with_auth_enabled():
    """Test JWT token creation and verification with auth enabled."""
    print("Testing JWT tokens with auth enabled...")

    # Set up environment for testing
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }

    with patch.dict(os.environ, test_env):
        # Reload the auth module to pick up new environment variables
        import api.auth
        importlib.reload(api.auth)

        # Import after reloading module
        from api.auth import create_jwt_token, verify_jwt_token

        # Test JWT token creation
        read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)

        assert read_token is not None, "Read token should be created"
        assert admin_token is not None, "Admin token should be created"

        # Verify tokens

        read_payload = verify_jwt_token(read_token)
        admin_payload = verify_jwt_token(admin_token)

        assert read_payload["role"] == UserRole.READ_ONLY, "Read token should have read role"
        assert admin_payload["role"] == UserRole.ADMIN, "Admin token should have admin role"

    print("✓ JWT tokens with auth enabled test passed")


def test_authentication_disabled():
    """Test behavior when authentication is disabled."""
    print("Testing authentication disabled...")

    # Set environment to disable auth
    with patch.dict(os.environ, {"MEMORY_API_ENABLE_AUTH": "false"}):
        # Reload the module to pick up new environment variable
        import api.auth
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
        assert user["role"] == UserRole.ADMIN, "Should have admin role when auth disabled"

    # Restore auth module to original state
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

    with patch.dict(os.environ, test_env):
        # Reload the module to pick up new environment variable
        import api.rate_limit
        importlib.reload(api.rate_limit)

        from api.rate_limit import RATE_LIMITS, RATE_LIMITS_PER_SECOND

        assert RATE_LIMITS["read"] == 120, "Read rate limit should be 120"
        assert RATE_LIMITS["write"] == 20, "Write rate limit should be 20"
        assert RATE_LIMITS["admin"] == 10, "Admin rate limit should be 10"

        assert RATE_LIMITS_PER_SECOND["read"] == pytest.approx(2.0), "Read rate should be 2.0/sec"
        assert RATE_LIMITS_PER_SECOND["write"] == pytest.approx(20/60), "Write rate should be 0.33/sec"
        assert RATE_LIMITS_PER_SECOND["admin"] == pytest.approx(10/60), "Admin rate should be 0.17/sec"

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
