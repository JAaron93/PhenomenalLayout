#!/usr/bin/env python3
"""Debug GC endpoint issue."""

import os
import sys
import subprocess


def run_test_in_subprocess():
    """Run the test in a clean subprocess with test environment."""
    test_env = os.environ.copy()
    test_env.update({
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key"
    })

    # Run the actual test function in a subprocess with timeout
    try:
        result = subprocess.run(
            [sys.executable, __file__, "--run-test"],
            env=test_env,
            capture_output=True,
            text=True,
            timeout=30
        )
    except subprocess.TimeoutExpired as e:
        print(
            "ERROR: Test subprocess timed out after 30 seconds",
            file=sys.stderr
        )
        if e.stdout:
            print("STDOUT before timeout:", e.stdout)
        if e.stderr:
            print("STDERR before timeout:", e.stderr, file=sys.stderr)
        return 1

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)

    return result.returncode


def test_gc_endpoint():
    """Debug GC endpoint issue in clean environment."""
    import jwt
    import traceback
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app import create_app

    client = TestClient(create_app())

    # Create admin token with dynamic timestamps
    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    exp = int((now + timedelta(days=1)).timestamp())

    admin_token = jwt.encode(
        {
            "user_id": "admin_user",
            "role": "admin",
            "exp": exp,
            "iat": iat,
            "type": "access"
        },
        "test-secret-key",
        algorithm="HS256"
    )

    # Test GC endpoint
    try:
        response = client.post(
            "/api/v1/memory/gc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        print(f"GC Response status: {response.status_code}")
        print(f"GC Response body: {response.text}")
    except Exception as e:
        print(
            f"Exception occurred during HTTP call: "
            f"{type(e).__name__}: {e}"
        )
        print("Stack trace:")
        traceback.print_exc()
        # Try to print response details if response object exists
        try:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        except NameError:
            print(
                "No response object available "
                "(request failed before receiving response)"
            )
        # Exit with non-zero status to propagate failure
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run-test":
        # Running in subprocess with clean environment
        test_gc_endpoint()
    else:
        # Main entry point - spawn subprocess
        sys.exit(run_test_in_subprocess())
