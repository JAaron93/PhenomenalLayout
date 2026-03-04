#!/usr/bin/env python3
"""Debug FastAPI dependency injection."""

import asyncio
import sys

sys.path.insert(0, ".")

from fastapi import Request
from fastapi.testclient import TestClient

from api.auth import UserRole, create_jwt_token, get_current_user_dependency
from app import create_app


async def test_dependency_directly():
    """Test the dependency function directly with proper async/await."""
    print("=== TESTING DEPENDENCY DIRECTLY ===")

    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token: {admin_token}")

    # Create a real FastAPI request object with a proper ASGI scope
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "method": "GET",
        "path": "/",
        "scheme": "http",
        "http_version": "1.1",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"authorization", f"Bearer {admin_token}".encode())],
        "state": {},
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    request = Request(scope=scope)

    try:
        # Test the dependency function directly with await
        user = await get_current_user_dependency(request)
        print(f"✅ get_current_user_dependency result: {user}")
        return user
    except Exception as e:
        print(f"❌ get_current_user_dependency failed: {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Run debug tests."""
    print("=== FASTAPI DEPENDENCY DEBUG ===")

    # Test 1: Direct async call
    asyncio.run(test_dependency_directly())

    # Test 2: Through FastAPI client
    print("\n--- Test 2: Through FastAPI client ---")
    app = create_app()
    client = TestClient(app)

    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    response = client.post(
        "/api/v1/memory/gc", headers={"Authorization": f"Bearer {admin_token}"}
    )
    print(f"GC Response - Status: {response.status_code}")
    print(f"GC Response - Body: {response.text}")


if __name__ == "__main__":
    main()
