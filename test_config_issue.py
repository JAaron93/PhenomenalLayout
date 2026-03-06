#!/usr/bin/env python3
"""Test to verify the config issue hypothesis."""

import os
import sys
from unittest.mock import patch

print("=== Initial test ===")
test_env1 = {
    'MEMORY_API_ENABLE_AUTH': 'true',
    'MEMORY_API_JWT_SECRET': 'test-secret',
    'MEMORY_API_KEY': 'test-key'
}
with patch.dict('os.environ', test_env1):
    sys.modules.pop('api.auth', None)
    from api.auth import _default_config
    print(f"Env: MEMORY_API_ENABLE_AUTH={os.getenv('MEMORY_API_ENABLE_AUTH')}")
    print(f"Config: enable_auth={_default_config.enable_auth}")
    assert _default_config.enable_auth == True, "Expected enable_auth=True"

print("\n=== Changing environment ===")
test_env2 = {
    'MEMORY_API_ENABLE_AUTH': 'false',
    'MEMORY_API_JWT_SECRET': 'test-secret',
    'MEMORY_API_KEY': 'test-key'
}
with patch.dict('os.environ', test_env2):
    sys.modules.pop('api.auth', None)
    from api.auth import _default_config as config2
    print(f"Env: MEMORY_API_ENABLE_AUTH={os.getenv('MEMORY_API_ENABLE_AUTH')}")
    print(f"Config: enable_auth={config2.enable_auth}")
    assert config2.enable_auth == False, "Expected enable_auth=False"

print("\n✓ Configuration is correctly updating!")
