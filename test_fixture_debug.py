#!/usr/bin/env python3
"""Debug test to verify fixture behavior."""

import pytest

def test_fixture_debug(test_client):
    """Test that fixture is working correctly."""
    print(f"Test client type: {type(test_client)}")
    print(f"Test client value: {test_client}")
    
    # Make a simple request
    response = test_client.get("/api/v1/memory/stats")
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
