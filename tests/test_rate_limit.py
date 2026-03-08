"""Tests for the rate limit decorator functionality."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from api.rate_limit import (
    rate_limit,
    shutdown_rate_limiter,
    get_rate_limiter,
    RATE_LIMITS,
)


@pytest.fixture
def test_app_sync():
    """Create a test FastAPI application with synchronous rate-limited endpoint."""
    app = FastAPI()

    @app.get("/sync-endpoint")
    @rate_limit("read")
    def sync_endpoint(request: Request):
        return {"message": "Success"}

    return app


@pytest.fixture
def test_app_async():
    """Create a test FastAPI application with asynchronous rate-limited endpoint."""
    app = FastAPI()

    @app.get("/async-endpoint")
    @rate_limit("write")
    async def async_endpoint(request: Request):
        return {"message": "Success"}

    return app


@pytest.fixture
def test_client_sync(test_app_sync):
    """Create a test client for the synchronous endpoint app."""
    return TestClient(test_app_sync)


@pytest.fixture
def test_client_async(test_app_async):
    """Create a test client for the asynchronous endpoint app."""
    return TestClient(test_app_async)


@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before and after each test."""
    # Reset before test
    shutdown_rate_limiter()
    # Reinitialize for the test
    get_rate_limiter()
    yield
    # Reset after test
    shutdown_rate_limiter()


def test_sync_function_decorator(test_client_sync, reset_rate_limiter):
    """Test that the rate limit decorator works with synchronous functions."""
    # Get the expected limit from configuration
    read_limit = RATE_LIMITS["read"]
    # Make multiple requests to trigger rate limiting
    for _ in range(read_limit):
        response = test_client_sync.get("/sync-endpoint")
        assert response.status_code == 200, "Sync endpoint should return 200"

    # The request after the limit should be rate-limited
    response = test_client_sync.get("/sync-endpoint")
    assert response.status_code == 429, "Rate limiting for sync function"


def test_async_function_decorator(test_client_async):
    """Test that the rate limit decorator works with asynchronous functions."""
    # Make multiple requests to trigger rate limiting
    for _ in range(10):
        response = test_client_async.get("/async-endpoint")
        assert response.status_code == 200, "Async endpoint should return 200"

    # The 11th request should be rate-limited
    response = test_client_async.get("/async-endpoint")
    assert response.status_code == 429, "Rate limiting for async function"


def test_shutdown_rate_limiter(reset_rate_limiter):
    """Test that shutdown_rate_limiter() function works correctly."""
    # Initialize rate limiter first by calling get_rate_limiter()
    limiter = get_rate_limiter()
    assert limiter is not None, "Rate limiter should be initialized"

    # Shutdown the rate limiter
    shutdown_rate_limiter()

    # After shutdown, get_rate_limiter() should return a new instance
    # (not the same object) - verifies old limiter was properly shut down
    new_limiter = get_rate_limiter()
    assert new_limiter is not None, (
        "Rate limiter should be re-initialized after shutdown"
    )
    assert new_limiter is not limiter, (
        "After shutdown, get_rate_limiter should return a new instance"
    )

    # Call shutdown again to verify idempotency (should not raise)
    shutdown_rate_limiter()

    # Verify calling get_rate_limiter after second shutdown works
    final_limiter = get_rate_limiter()
    assert final_limiter is not None, (
        "Rate limiter should work after multiple shutdowns"
    )
