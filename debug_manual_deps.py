#!/usr/bin/env python3
"""Debug manual dependency injection."""

import asyncio
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_current_user, get_bearer_scheme
from fastapi import Request

async def test_manual_injection():
    """Test manual dependency injection like FastAPI would do."""
    print("=== TESTING MANUAL DEPENDENCY INJECTION ===")
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token (truncated): {admin_token[:20]}...")
    
    # Create a mock request with Authorization header
    class MockRequest:
        def __init__(self, headers):
            self.headers = headers
    
    request = MockRequest({"Authorization": f"Bearer {admin_token}"})
    
    # Manually inject dependencies like FastAPI would
    bearer_scheme = get_bearer_scheme()
    print(f"Bearer scheme: {bearer_scheme}")
    
    # Extract credentials like FastAPI would
    credentials = None
    if bearer_scheme:
        try:
            credentials = await bearer_scheme(request)
            print(f"Extracted credentials: {credentials}")
        except Exception as e:
            print(f"Failed to extract credentials: {e}")
    
    try:
        # Call get_current_user with manually injected dependencies
        user = await get_current_user(request, None, credentials)
        print(f"✅ get_current_user result: {user}")
        return user
    except Exception as e:
        print(f"❌ get_current_user failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("=== MANUAL DEPENDENCY DEBUG ===")
    
    # Test 1: Manual dependency injection
    user = asyncio.run(test_manual_injection())
    
    # Test 2: Through FastAPI client
    print("\n--- Test 2: Through FastAPI client ---")
    app = create_app()
    client = TestClient(app)
    
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    response = client.post('/api/v1/memory/gc', headers={'Authorization': f'Bearer {admin_token}'})
    print(f"GC Response - Status: {response.status_code}")
    print(f"GC Response - Body: {response.text}")

if __name__ == "__main__":
    main()
