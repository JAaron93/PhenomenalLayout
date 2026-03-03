#!/usr/bin/env python3
"""Quick test to verify endpoint paths are correct."""

import os
import sys
from unittest.mock import patch

# Add current directory to path
sys.path.insert(0, '.')

# Set up test environment
test_env = {
    "MEMORY_API_ENABLE_AUTH": "true",
    "MEMORY_API_JWT_SECRET": "test-secret-key",
    "MEMORY_API_KEY": "test-admin-key",
    "MEMORY_API_READ_RATE_LIMIT": "100",
    "MEMORY_API_WRITE_RATE_LIMIT": "100", 
    "MEMORY_API_ADMIN_RATE_LIMIT": "100"
}

with patch.dict('os.environ', test_env):
    # Import after setting environment
    from fastapi.testclient import TestClient
    from app import create_app
    from api.auth import create_jwt_token, UserRole
    
    # Create test client
    client = TestClient(create_app())
    
    # Create tokens
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
    
    # Test endpoints
    endpoints = [
        ('/api/v1/memory/gc', 'POST', admin_token, 200),
        ('/api/v1/memory/gc', 'POST', read_token, 403),
        ('/api/v1/memory/monitoring/stop', 'POST', admin_token, 200),
        ('/api/v1/memory/monitoring/stop', 'POST', read_token, 403),
        ('/api/v1/memory/monitoring/status', 'GET', admin_token, 200),
        ('/api/v1/memory/monitoring/status', 'GET', read_token, 200),
        ('/api/v1/memory/monitoring/start', 'POST', admin_token, 200),
        ('/api/v1/memory/monitoring/start', 'POST', read_token, 403),
    ]
    
    print("Testing endpoint paths and authentication:")
    print("=" * 60)
    
    all_passed = True
    for endpoint, method, token, expected_status in endpoints:
        headers = {"Authorization": f"Bearer {token}"}
        
        if method == 'POST':
            response = client.post(endpoint, headers=headers)
        else:
            response = client.get(endpoint, headers=headers)
        
        status_ok = response.status_code == expected_status
        status_text = "✓" if status_ok else "✗"
        
        print(f"{status_text} {method} {endpoint} with {token[:10]}... token")
        print(f"   Expected: {expected_status}, Got: {response.status_code}")
        
        if not status_ok:
            print(f"   Response: {response.text[:100]}...")
            all_passed = False
        print()
    
    print("=" * 60)
    if all_passed:
        print("✓ All endpoint tests passed!")
    else:
        print("✗ Some tests failed")
    
    sys.exit(0 if all_passed else 1)
