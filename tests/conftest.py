import os

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

pytest_plugins: tuple[str, ...] = ("pytest_asyncio",)


@pytest.fixture(autouse=True)
def dolphin_env_defaults(monkeypatch):
    """Provide sane default env vars for Dolphin config during tests."""
    monkeypatch.setenv("HF_TOKEN", os.getenv("HF_TOKEN", "mock_hf_token_for_tests"))
    monkeypatch.setenv(
        "DOLPHIN_MODAL_ENDPOINT",
        os.getenv(
            "DOLPHIN_MODAL_ENDPOINT",
            "https://mock-dolphin-endpoint.test.local",
        ),
    )
    yield


@pytest.fixture
def lingo_translator(monkeypatch):
    """Provide a LingoTranslator instance with a test API key for any test module/class."""
    # Set the environment variable using monkeypatch (automatically restored after test)
    monkeypatch.setenv("LINGO_API_KEY", "test_api_key")

    # Import LingoTranslator after setting the environment variable
    from services.translation_service import LingoTranslator

    return LingoTranslator()


def pytest_configure(config: pytest.Config) -> None:
    """Set required environment variables for tests early in startup.

    This runs before test collection, ensuring modules that read environment
    variables at import time (e.g., `config.settings.Settings`) see the values.
    """
    # Set DEBUG=True for tests to enable auto-generated SECRET_KEY
    os.environ.setdefault("DEBUG", "true")
    # Provide a deterministic SECRET_KEY for tests to ensure consistency across workers
    os.environ.setdefault(
        "SECRET_KEY", "test-secret-key-deterministic-for-testing-only-32chars"
    )
    # When focusing, quiet output at runtime without relying on pre-parsed
    # addopts
    if os.getenv("FOCUSED"):
        config.option.quiet = max(getattr(config.option, "quiet", 0), 1)


@pytest.fixture(scope="module")
def test_client():
    """Pytest fixture providing a test client with test environment.
    
    Uses module scope to prevent cached state leakage across tests that
    could occur when reloading modules with function-scoped fixtures.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100"
    }

    with patch.dict('os.environ', test_env):
        # Reload modules to pick up environment
        import importlib
        import api.auth
        import api.memory_routes
        import api.rate_limit
        import app as app_module
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        importlib.reload(api.rate_limit)
        importlib.reload(app_module)

        # Create test client with patched environment
        client = TestClient(app_module.create_app())
        yield client


@pytest.fixture
def read_token(test_client):
    """Pytest fixture providing a read-only token."""
    import api.auth
    return api.auth.create_jwt_token("read_user", api.auth.UserRole.READ_ONLY)


@pytest.fixture
def admin_token(test_client):
    """Pytest fixture providing an admin token."""
    import api.auth
    return api.auth.create_jwt_token("admin_user", api.auth.UserRole.ADMIN)
