#!/usr/bin/env python3
"""Debug test to verify environment and authentication."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, '.')

from api.auth import UserRole, create_jwt_token
from app import create_app


def main():
    """Main function to test environment and authentication."""
    print("=== ENVIRONMENT DEBUG ===")
    print(f"MEMORY_API_ENABLE_AUTH: {os.getenv('MEMORY_API_ENABLE_AUTH')}")
    jwt_secret = os.getenv('MEMORY_API_JWT_SECRET')
    print(f"MEMORY_API_JWT_SECRET: {'[SET]' if jwt_secret else '[NOT SET]'}")
    api_key = os.getenv('MEMORY_API_KEY')
    print(f"MEMORY_API_KEY: {'[SET]' if api_key else '[NOT SET]'}")

    # Create app and client
    app = create_app()
    client = TestClient(app)
    admin_token = create_jwt_token("admin_user", UserRole.ADMIN)
    print(f"Admin token generated: {admin_token[:20]}... (truncated)")

    # Test GC endpoint
    try:
        auth_headers = {'Authorization': f'Bearer {admin_token}'}
        response = client.post('/api/v1/memory/gc', headers=auth_headers)
        print(f"GC Response - Status: {response.status_code}")
        print(f"GC Response - Body: {response.text}")

        if response.status_code != 200:
            print(
                "ERROR: GC endpoint returned non-200 status: "
                f"{response.status_code}"
            )

    except Exception as e:
        print(
            f"ERROR: Failed to call GC endpoint: {type(e).__name__}: {e}"
        )
        print("Endpoint: POST /api/v1/memory/gc")
        print(
            f"Headers: {{'Authorization': 'Bearer {admin_token[:20]}...'}}"
        )

    # Test status endpoint
    try:
        response = client.get('/api/v1/memory/monitoring/status')
        print(f"Status Response - Status: {response.status_code}")
        print(f"Status Response - Body: {response.text}")

        if response.status_code != 200:
            print(
                f"ERROR: Status endpoint returned non-200 status: "
                f"{response.status_code}"
            )

    except Exception as e:
        print(
            f"ERROR: Failed to call Status endpoint: {type(e).__name__}: {e}"
        )
        print("Endpoint: GET /api/v1/memory/monitoring/status")


if __name__ == "__main__":
    main()
