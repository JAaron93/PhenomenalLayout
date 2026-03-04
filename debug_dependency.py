#!/usr/bin/env python3
"""Debug dependency injection issue."""

from unittest.mock import patch
import jwt
from fastapi.testclient import TestClient
from app import create_app
from api.auth import get_current_user_dependency

def test_dependency():
    """Debug dependency injection issue."""
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict('os.environ', test_env):
        import importlib
        import api.auth
        importlib.reload(api.auth)
        
        client = TestClient(create_app())
        
        # Create admin token
        import time
        
        now = int(time.time())
        admin_token = jwt.encode(
            {
                "user_id": "admin_user",
                "role": "admin",
                "exp": now + 86400,  # 24 hours from now
                "iat": now,
                "type": "access"
            },
            "test-secret-key",
            algorithm="HS256"
        )
        
        print(f"Admin token: {admin_token}")

        # Test auth endpoints using TestClient
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Test protected endpoint without auth (should fail)
        response = client.get("/memory/stats")
        print(
            f"GET /memory/stats without auth: {response.status_code} "
            f"- {response.json()}"
        )

        # Test protected endpoint with auth (should succeed)
        response = client.get("/memory/stats", headers=headers)
        print(
            f"GET /memory/stats with auth: {response.status_code} "
            f"- {response.json()}"
        )

        # Test admin endpoint with auth (should succeed)
        response = client.post("/memory/monitoring/start", headers=headers)
        print(
            "POST /memory/monitoring/start with auth: "
            f"{response.status_code} - {response.json()}"
        )

        # Test dependency directly
        from unittest.mock import MagicMock
        
        # Create a mock request
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {admin_token}"}
        # Configure other commonly accessed Request attributes to prevent AttributeError
        request.app = MagicMock()
        request.state = MagicMock()
        request.url = "http://test"
        
        try:
            import asyncio
            import inspect

            user = get_current_user_dependency(request)
            if inspect.iscoroutine(user):
                try:
                    user = asyncio.run(user)
                except RuntimeError:
                    # Fallback for when an event loop is already running
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is already running, we can't use
                        # run_until_complete
                        # In a debug script, we might just need to wait for it
                        # or use nest_asyncio
                        try:
                            import nest_asyncio
                            nest_asyncio.apply()
                            user = loop.run_until_complete(user)
                        except ImportError:
                            print(
                                "Warning: nest_asyncio not installed, "
                                "cannot run coroutine in running loop"
                            )
                            # Fallback: schedule it and hope for the best, though this is async
                            user = asyncio.ensure_future(user)
                    else:
                        user = loop.run_until_complete(user)
                
            print(f"User from dependency: {user}")
        except Exception as e:
            print(f"Dependency error: {e}")


if __name__ == "__main__":
    test_dependency()
