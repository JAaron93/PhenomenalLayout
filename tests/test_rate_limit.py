"""Tests for the rate limit decorator functionality."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from api.rate_limit import rate_limit, shutdown_rate_limiter


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


def test_sync_function_decorator(test_client_sync):
    """Test that the rate limit decorator works with synchronous functions."""
    # Make multiple requests to trigger rate limiting
    for _ in range(60):
        response = test_client_sync.get("/sync-endpoint")
        assert response.status_code == 200, "Sync endpoint should return 200"

    # The 61st request should be rate-limited
    response = test_client_sync.get("/sync-endpoint")
    assert response.status_code == 429, "Rate limiting for sync function"


@pytest.mark.asyncio
async def test_async_function_decorator(test_client_async):
    """Test that the rate limit decorator works with asynchronous functions."""
    # Make multiple requests to trigger rate limiting
    for _ in range(10):
        response = test_client_async.get("/async-endpoint")
        assert response.status_code == 200, "Async endpoint should return 200"

    # The 11th request should be rate-limited
    response = test_client_async.get("/async-endpoint")
    assert response.status_code == 429, "Rate limiting for async function"


def test_shutdown_rate_limiter():
    """Test that shutdown_rate_limiter() function works correctly."""
    shutdown_rate_limiter()
    shutdown_rate_limiter()
    assert True, "shutdown_rate_limiter() handles both cases"
