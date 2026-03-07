import logging
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytest_plugins: tuple[str, ...] = ("pytest_asyncio",)

logger = logging.getLogger(__name__)

# Modules to reload in dependency order (base → dependent)
# Order matters: auth → rate_limit → memory_routes → app
# Exclude third-party modules that can't be reloaded (like numpy)
_RELOAD_MODULE_NAMES = [
    "api.auth",
    "api.rate_limit",
    "api.memory_routes",
    "app",
]

# Modules to exclude from sys.modules operations
_EXCLUDE_MODULES = {"numpy", "gradio"}


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
        "SECRET_KEY", "test-secret-key-for-testing-only!"
    )
    # Set memory API security environment variables
    os.environ.setdefault("MEMORY_API_ENABLE_AUTH", "true")
    os.environ.setdefault("MEMORY_API_JWT_SECRET", "test-secret-key")
    os.environ.setdefault("MEMORY_API_KEY", "test-admin-key")
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
        import sys

        for name in _RELOAD_MODULE_NAMES:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                __import__(name)

        app_module = sys.modules["app"]
        client = TestClient(app_module.create_app())
        yield client

        # Teardown: reload modules to restore state after patch context exits
        for name in _RELOAD_MODULE_NAMES:
            if name in sys.modules:
                try:
                    importlib.reload(sys.modules[name])
                except Exception:
                    logger.debug("Failed to reload %s during teardown", name, exc_info=True)


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


@pytest.fixture
def reload_app_with_env():
    """Fixture to reload modules with patched environment and cleanup after.

    Isolates environment changes by patching os.environ, reloading affected
    modules in dependency order, and restoring original modules after test.
    Yields a factory function that returns a fresh TestClient.
    """
    import sys

    # Save original module objects before any reloads
    original_modules = {}
    for name in _RELOAD_MODULE_NAMES:
        if name in sys.modules:
            original_modules[name] = sys.modules[name]

    # Track active patches and created test clients
    active_patches = []
    created_clients = []

    def _factory(test_env: dict) -> TestClient:
        """Create TestClient with patched environment and fresh module imports."""
        from unittest.mock import patch

        # Create a long-lived patch that stays active
        patch_obj = patch.dict("os.environ", test_env)
        patch_obj.start()
        active_patches.append(patch_obj)

        # Remove modules from sys.modules to ensure fresh imports
        # Exclude problematic modules that can't be reloaded
        for name in _RELOAD_MODULE_NAMES:
            if name in sys.modules and not any(excluded in name for excluded in _EXCLUDE_MODULES):
                del sys.modules[name]

        # Import fresh modules
        for name in _RELOAD_MODULE_NAMES:
            __import__(name)

        app_module = sys.modules["app"]
        client = TestClient(app_module.create_app())
        created_clients.append(client)
        return client

    try:
        yield _factory
    finally:
        # Close all created test clients
        for client in created_clients:
            client.close()
        # Stop all active patches
        for patch_obj in active_patches:
            patch_obj.stop()
        # Restore original modules to prevent state leakage between tests
        for name in original_modules:
            sys.modules[name] = original_modules[name]
