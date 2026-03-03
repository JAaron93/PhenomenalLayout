#!/usr/bin/env python3
"""Debug optional dependency."""

import asyncio
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_current_user_optional_dependency

async def test_optional_dependency():
    """Test the optional dependency function."""
    print("=== TESTING OPTIONAL DEPENDENCY ===")
    
    # Create read token
    read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
    print(f"Read token: {read_token}")
    
    # Create a mock request with Authorization header
    class MockRequest:
        def __init__(self, headers):
            self.headers = headers
    
    request = MockRequest({"Authorization": f"Bearer {read_token}"})
    
    try:
        # Test the optional dependency function
        user = await get_current_user_optional_dependency(request)
        print(f"✅ get_current_user_optional_dependency result: {user}")
        return user
    except Exception as e:
        print(f"❌ get_current_user_optional_dependency failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("=== OPTIONAL DEPENDENCY DEBUG ===")
    
    # Test 1: Direct async call
    user = asyncio.run(test_optional_dependency())
    
    # Test 2: Through FastAPI client
    print("\n--- Test 2: Through FastAPI client ---")
    app = create_app()
    client = TestClient(app)
    
    read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
    response = client.get('/api/v1/memory/stats', headers={'Authorization': f'Bearer {read_token}'})
    print(f"Stats Response - Status: {response.status_code}")
    print(f"Stats Response - Body: {response.text}")

if __name__ == "__main__":
    main()
