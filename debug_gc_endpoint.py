#!/usr/bin/env python3
"""Debug GC endpoint issue."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from app import create_app

def test_gc_endpoint():
    """Debug GC endpoint issue."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        client = TestClient(create_app())
        
        # Create admin token with dynamic timestamps
        import jwt
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        iat = int(now.timestamp())
        exp = int((now + timedelta(days=1)).timestamp())
        
        admin_token = jwt.encode(
            {
                "user_id": "admin_user",
                "role": "admin",
                "exp": exp,
                "iat": iat,
                "type": "access"
            },
            "test-secret-key",
            algorithm="HS256"
        )
        # Test GC endpoint
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"GC Response status: {response.status_code}")
        print(f"GC Response body: {response.text}")

if __name__ == "__main__":
    test_gc_endpoint()
