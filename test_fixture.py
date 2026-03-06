#!/usr/bin/env python3
"""Test to see what's happening with reload_app_with_env fixture."""

import os
import pytest
from unittest.mock import patch

def test_reload_fixture(reload_app_with_env):
    """Test what reload_app_with_env actually does."""
    test_env = {
        'MEMORY_API_ENABLE_AUTH': 'false',
        'MEMORY_API_JWT_SECRET': 'test-secret-key',
        'MEMORY_API_KEY': 'test-admin-key',
        'MEMORY_API_READ_RATE_LIMIT': '100',
        'MEMORY_API_WRITE_RATE_LIMIT': '100',
        'MEMORY_API_ADMIN_RATE_LIMIT': '100',
    }

    # Check current environment before calling fixture
    print('Before fixture call:')
    print(f'MEMORY_API_ENABLE_AUTH: {os.getenv("MEMORY_API_ENABLE_AUTH")}')
    print('-' * 50)
    
    client = reload_app_with_env(test_env)
    
    # Check environment variables are set inside the fixture
    print('After fixture call, testing endpoint:')
    response = client.get('/api/v1/memory/stats')
    print(f'Status: {response.status_code}')
    print(f'Response: {response.text}')
    assert response.status_code == 200

    print('-' * 50)
    print('Environment variables after fixture:')
    print(f'MEMORY_API_ENABLE_AUTH: {os.getenv("MEMORY_API_ENABLE_AUTH")}')
