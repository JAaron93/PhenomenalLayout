#!/usr/bin/env python3
"""
Basic usage example for the Dolphin OCR Modal service.

Shows how to use the service with optional security features.
"""

import asyncio
import json
import os
from pathlib import Path

import httpx


async def main():
    """Basic usage example."""

    # Service configuration
    service_url = os.getenv("DOLPHIN_SERVICE_URL")
    # Optional, only if authentication is enabled
    api_key = os.getenv("ADMIN_API_KEY")

    # Validate service URL is configured
    sentinel_url = "https://REPLACE_ME_DOLPHIN_SERVICE_URL"
    if not service_url or service_url == sentinel_url:
        print("❌ Error: DOLPHIN_SERVICE_URL environment variable is required")
        print(
            "   Please set DOLPHIN_SERVICE_URL to your actual "
            "Dolphin OCR service URL"
        )
        print(
            "   Example: export DOLPHIN_SERVICE_URL='"
            "https://your-actual-modal-domain.com'"
        )
        return

    client = httpx.AsyncClient(timeout=30.0)

    try:
        # 1. Health check
        print("🔍 Checking service health...")
        response = await client.get(f"{service_url}/health")
        if response.status_code == 200:
            print("✅ Service is healthy")
        else:
            print(f"❌ Service unhealthy: {response.status_code}")
            return

        # 2. Get service info
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        print("📋 Getting service information...")
        response = await client.get(f"{service_url}/", headers=headers)
        if response.status_code == 200:
            info = response.json()
            print(f"   Service: {info['name']}")
            print(f"   Max file size: {info['limits']['max_file_size_mb']}MB")
            print(f"   Rate limit: {info.get('rate_limit', 'Not specified')}")
        elif response.status_code == 401:
            print("   ⚠️  Authentication required (set ADMIN_API_KEY)")

        # 3. Upload and process a PDF
        test_pdf = Path("test_document.pdf")
        if test_pdf.exists():
            print(f"📄 Processing PDF: {test_pdf}")

            with open(test_pdf, "rb") as f:
                files = {"pdf_file": (test_pdf.name, f, "application/pdf")}

                response = await client.post(
                    f"{service_url}/", files=files, headers=headers
                )

            if response.status_code == 200:
                result = response.json()
                pages = result.get("pages", [])
                print(f"   ✅ Successfully processed {len(pages)} pages")

                # Save results
                output_file = Path(f"result_{test_pdf.stem}.json")
                with open(output_file, "w") as f:
                    json.dump(result, f, indent=2)
                print(f"   💾 Results saved to: {output_file}")

            elif response.status_code == 401:
                print("   ❌ Authentication failed")
            elif response.status_code == 429:
                print("   ❌ Rate limit exceeded - please wait")
            else:
                print(f"   ❌ Processing failed: {response.status_code}")
                try:
                    error = response.json()
                    print(f"      Error: {error.get('error', 'Unknown')}")
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"      Unable to parse error response as JSON: {e}")
                except Exception as e:
                    print(f"      Unexpected error parsing response: {e}")
                    raise
        else:
            print(f"   ℹ️  No test PDF found at {test_pdf}")
            print("   Create a test PDF file to see OCR processing")

    finally:
        await client.aclose()


if __name__ == "__main__":
    print("🚀 Basic Dolphin OCR Usage Example")
    print("==================================")
    asyncio.run(main())
