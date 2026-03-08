#!/usr/bin/env python3
"""Tests for auth config environment handling."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def clear_api_modules():
    """Ensure api auth modules are re-imported fresh for each test."""
    sys.modules.pop("api", None)
    sys.modules.pop("api.auth", None)
    yield
    sys.modules.pop("api", None)
    sys.modules.pop("api.auth", None)


def test_enable_auth_true_when_env_is_true(clear_api_modules):
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret",
        "MEMORY_API_KEY": "test-key",
    }

    with patch.dict(os.environ, test_env):
        from api.auth import _default_config

        assert _default_config.enable_auth is True


def test_enable_auth_false_when_env_is_false(clear_api_modules):
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "false",
        "MEMORY_API_JWT_SECRET": "test-secret",
        "MEMORY_API_KEY": "test-key",
    }

    with patch.dict(os.environ, test_env, clear=True):
        from api.auth import _default_config

        assert _default_config.enable_auth is False
