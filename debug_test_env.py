#!/usr/bin/env python3
"""Debug test to verify environment and authentication."""

import os
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app import create_app
from api.auth import create_jwt_token, UserRole

def main():
    print("=== ENVIRONMENT DEBUG ===")
    print(f"MEMORY_API_ENABLE_AUTH: {os.getenv('MEMORY_API_ENABLE_AUTH')}")
    print(f"MEMORY_API_JWT_SECRET: {os.getenv('MEMORY_API_JWT_SECRET')}")
    print(f"MEMORY_API_KEY: {os.getenv('MEMORY_API_KEY')}")
    
    # Create app and client
    app = create_app()
    client = TestClient(app)
    
    # Create admin token
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token: {admin_token}")
    
    # Test GC endpoint
    response = client.post('/api/v1/memory/gc', headers={'Authorization': f'Bearer {admin_token}'})
    print(f"GC Response - Status: {response.status_code}")
    print(f"GC Response - Body: {response.text}")
    
    # Test status endpoint
    response = client.get('/api/v1/memory/monitoring/status')
    print(f"Status Response - Status: {response.status_code}")
    print(f"Status Response - Body: {response.text}")

if __name__ == "__main__":
    main()
