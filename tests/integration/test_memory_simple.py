#!/usr/bin/env python3
"""Simple test to verify fixture is working."""

import logging
import sys
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)


@pytest.fixture
def test_client():
    """Pytest fixture providing a test client with test environment."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }

    # Save the original module states before patching
    original_auth = sys.modules.get('api.auth')
    original_app = sys.modules.get('app')

    with patch.dict('os.environ', test_env):
        import importlib
        import api.auth
        from app import create_app
        importlib.reload(api.auth)

        client = TestClient(create_app())
        logger.debug("Created test client for testing")
        yield client

    # Restore the original module states after the test
    if original_auth is not None:
        sys.modules['api.auth'] = original_auth
    else:
        # Module wasn't originally loaded, remove it from sys.modules
        sys.modules.pop('api.auth', None)

    if original_app is not None:
        sys.modules['app'] = original_app
    else:
        # Module wasn't originally loaded, remove it from sys.modules
        sys.modules.pop('app', None)


def test_simple_endpoint(test_client):
    """Test simple endpoint to verify auth is working."""
    import api.auth

    logger.debug("Testing simple endpoint with auth enabled")

    # Create admin token using reloaded module
    admin_token = api.auth.create_jwt_token(
        "admin_user", api.auth.UserRole.ADMIN
    )
    logger.debug("Created admin token for testing")

    # Test GET /memory/stats with admin token
    response = test_client.get(
        "/api/v1/memory/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    logger.debug("Received response with status: %d", response.status_code)
    assert response.status_code == 200
