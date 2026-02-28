#!/usr/bin/env python3
"""Integration test for memory API endpoints with authentication."""

import os
import sys
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

# Add the project root to Python path
sys.path.insert(0, '/Users/pretermodernist/PhenomenalLayout')

from app import app
from api.auth import create_jwt_token, UserRole


def test_memory_endpoints_with_auth():
    """Test memory endpoints with authentication."""
    print("Testing memory endpoints with authentication...")
    
    # Set up environment for testing
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict(os.environ, test_env):
        # Reload modules to pick up environment
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        # Create test client
        client = TestClient(app)
        
        # Create tokens
        read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
        admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
        
        # Test GET /memory/stats with read token
        response = client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        assert response.status_code == 200, f"Stats endpoint should work with read token: {response.text}"
        
        # Test GET /memory/stats with admin token
        response = client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Stats endpoint should work with admin token: {response.text}"
        
        # Test GET /memory/monitoring/status with read token
        response = client.get(
            "/api/v1/memory/monitoring/status",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        assert response.status_code == 200, f"Status endpoint should work with read token: {response.text}"
        
        # Test POST /memory/gc with admin token
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"GC endpoint should work with admin token: {response.text}"
        
        # Test POST /memory/monitoring/start with admin token
        response = client.post(
            "/api/v1/memory/monitoring/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Start monitoring should work with admin token: {response.text}"
        
        # Test POST /memory/monitoring/stop with admin token
        response = client.post(
            "/api/v1/memory/monitoring/stop",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Stop monitoring should work with admin token: {response.text}"
        
        # Test admin endpoint with read token (should fail)
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        assert response.status_code == 403, f"GC endpoint should fail with read token: {response.text}"
        
        # Test endpoint without auth (should fail)
        response = client.get("/api/v1/memory/stats")
        assert response.status_code == 401, f"Stats endpoint should fail without auth: {response.text}"
        
        # Test with API key
        response = client.get(
            "/api/v1/memory/stats",
            headers={"X-API-Key": "test-admin-key"}
        )
        assert response.status_code == 200, f"Stats endpoint should work with API key: {response.text}"
        
        # Test admin endpoint with API key
        response = client.post(
            "/api/v1/memory/gc",
            headers={"X-API-Key": "test-admin-key"}
        )
        assert response.status_code == 200, f"GC endpoint should work with API key: {response.text}"
        
        # Test with invalid API key (should fail)
        response = client.get(
            "/api/v1/memory/stats",
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401, f"Stats endpoint should fail with invalid API key: {response.text}"
    
    print("✓ Memory endpoints with authentication test passed")


def test_memory_endpoints_no_auth():
    """Test memory endpoints with authentication disabled."""
    print("Testing memory endpoints with authentication disabled...")
    
    # Set environment to disable auth
    with patch.dict(os.environ, {"MEMORY_API_ENABLE_AUTH": "false"}):
        # Reload modules
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        # Create test client
        client = TestClient(app)
        
        # Test endpoints without auth (should work)
        response = client.get("/api/v1/memory/stats")
        assert response.status_code == 200, f"Stats endpoint should work without auth: {response.text}"
        
        response = client.post("/api/v1/memory/gc")
        assert response.status_code == 200, f"GC endpoint should work without auth: {response.text}"
        
        response = client.get("/api/v1/memory/monitoring/status")
        assert response.status_code == 200, f"Status endpoint should work without auth: {response.text}"
    
    print("✓ Memory endpoints without authentication test passed")


def test_rate_limiting_headers():
    """Test rate limiting headers are present."""
    print("Testing rate limiting headers...")
    
    # Set up environment
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    }
    
    with patch.dict(os.environ, test_env):
        # Reload modules
        import importlib
        import api.auth
        import api.memory_routes
        importlib.reload(api.auth)
        importlib.reload(api.memory_routes)
        
        # Create test client
        client = TestClient(app)
        
        # Create token
        read_token = create_jwt_token("read_user", UserRole.READ_ONLY)
        
        # Test rate limit headers
        response = client.get(
            "/api/v1/memory/stats",
            headers={"Authorization": f"Bearer {read_token}"}
        )
        assert response.status_code == 200
        
        # Check for rate limit headers
        assert "X-RateLimit-Limit" in response.headers, "Should have rate limit headers"
        assert "X-RateLimit-Remaining" in response.headers, "Should have remaining header"
        assert "X-RateLimit-Reset" in response.headers, "Should have reset header"
        
        print(f"  Rate limit headers: {dict(response.headers)}")
    
    print("✓ Rate limiting headers test passed")


if __name__ == "__main__":
    print("Testing Memory API Integration...")
    print("=" * 50)
    
    try:
        test_memory_endpoints_with_auth()
        test_memory_endpoints_no_auth()
        test_rate_limiting_headers()
        
        print("=" * 50)
        print("✅ All integration tests passed!")
        print("\nIntegration verified:")
        print("- JWT authentication works for all endpoints")
        print("- API key authentication works for all endpoints")
        print("- Role-based access control enforced")
        print("- Authentication can be disabled for development")
        print("- Rate limiting headers are present")
        print("- All endpoints return proper responses")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
