#!/usr/bin/env python3
"""Debug authentication flow step by step."""

import os
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole, get_current_user, get_current_user_dependency
from fastapi import Request
from unittest.mock import Mock

def main():
    print("=== AUTH FLOW DEBUG ===")
    
    # Create app and client
    app = create_app()
    client = TestClient(app)
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token: {admin_token}")
    
    # Test 1: Direct dependency function
    print("\n--- Test 1: Direct dependency function ---")
    try:
        # Create a mock request with Authorization header
        request = Mock(spec=Request)
        request.headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test the dependency function directly
        user = get_current_user_dependency(request)
        print(f"✅ get_current_user_dependency result: {user}")
    except Exception as e:
        print(f"❌ get_current_user_dependency failed: {e}")
    
    # Test 2: GC endpoint with debug
    print("\n--- Test 2: GC endpoint ---")
    response = client.post('/api/v1/memory/gc', headers={'Authorization': f'Bearer {admin_token}'})
    print(f"GC Response - Status: {response.status_code}")
    print(f"GC Response - Body: {response.text}")
    
    # Test 3: Status endpoint (working)
    print("\n--- Test 3: Status endpoint ---")
    response = client.get('/api/v1/memory/monitoring/status')
    print(f"Status Response - Status: {response.status_code}")
    print(f"Status Response - Body: {response.text}")

if __name__ == "__main__":
    main()
