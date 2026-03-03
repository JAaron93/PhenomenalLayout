#!/usr/bin/env python3
"""Debug FastAPI dependency injection."""

import asyncio
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_current_user_dependency
from fastapi import Request

async def test_dependency_directly():
    """Test the dependency function directly with proper async/await."""
    print("=== TESTING DEPENDENCY DIRECTLY ===")
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token: {admin_token}")
    
    # Create a mock request with Authorization header
    class MockRequest:
        def __init__(self, headers):
            self.headers = headers
    
    request = MockRequest({"Authorization": f"Bearer {admin_token}"})
    
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
    print("=== FASTAPI DEPENDENCY DEBUG ===")
    
    # Test 1: Direct async call
    user = asyncio.run(test_dependency_directly())
    
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
