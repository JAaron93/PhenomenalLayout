#!/usr/bin/env python3
"""Debug test to inspect what's happening inside endpoints."""

import os
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient

def test_endpoint_debugging():
    """Debug test to see what's happening inside the endpoint handler."""
    test_env = {
        'MEMORY_API_ENABLE_AUTH': 'false',
        'MEMORY_API_JWT_SECRET': 'test-secret',
        'MEMORY_API_KEY': 'test-key'
    }
    
    with patch.dict('os.environ', test_env):
        # Remove modules to ensure fresh import
        for module in list(sys.modules.keys()):
            if module.startswith('api.') or module == 'app':
                del sys.modules[module]
        
        from app import create_app
        client = TestClient(create_app())
        
        # Import the auth module after app creation
        import api.auth
        print(f"DEBUG: api.auth module id: {id(api.auth)}")
        print(f"DEBUG: api.auth._default_config: {id(api.auth._default_config)}")
        print(f"DEBUG: api.auth._default_config.enable_auth: {api.auth._default_config.enable_auth}")
        print(f"DEBUG: api.auth.ANONYMOUS_USER: {api.auth.ANONYMOUS_USER}")
        
        # Try to access the endpoint
        print("\n=== Making API request ===")
        try:
            response = client.get('/api/v1/memory/stats')
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response text: {response.text}")
            
            # Check what's in sys.modules after request
            print(f"\nDEBUG: After request - api.auth module id: {id(sys.modules['api.auth'])}")
            print(f"DEBUG: After request - enable_auth: {sys.modules['api.auth']._default_config.enable_auth}")
            
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            print(traceback.format_exc())

if __name__ == "__main__":
    test_endpoint_debugging()
