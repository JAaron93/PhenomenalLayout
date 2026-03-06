#!/usr/bin/env python3
"""Test focusing on the problematic test case."""

import logging

import pytest

from tests.test_memory_api_integration import reload_app_with_env

# Get logger for test
logger = logging.getLogger(__name__)


def test_problematic_case():
    """Test the problematic scenario from the failing test."""
    auth_enabled = "false"
    logger.debug("Testing with auth_enabled=%s", auth_enabled)
    
    test_env = {
        "MEMORY_API_ENABLE_AUTH": auth_enabled,
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }
    
    client = reload_app_with_env(test_env)
    
    # Check imported modules
    import api.auth
    # Verify auth is disabled via public API
    assert not api.auth.is_auth_enabled(), \
        "Auth should be disabled with MEMORY_API_ENABLE_AUTH=false"
    # Assert ANONYMOUS_USER is accessible (public symbol)
    assert api.auth.ANONYMOUS_USER is not None
    
    # Test endpoint
    logger.debug("Calling /api/v1/memory/stats")
    response = client.get('/api/v1/memory/stats')
    
    logger.debug("Response status: %s", response.status_code)
    logger.debug("Response text: %s", response.text)
    
    assert response.status_code == 200, \
        f"Expected 200, got {response.status_code}"


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-xvs"])
