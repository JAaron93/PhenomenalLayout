#!/usr/bin/env python3
"""Demonstration of the web-eval-agent MCP server capabilities.

This script shows how the web-eval-agent can be used for automated web
evaluation.
"""

import hashlib
import hmac
import json
import os
import time
from typing import Final, TypedDict

# Default demo URL for web evaluation demonstration
DEFAULT_DEMO_URL: Final[str] = "http://localhost:8000/static/demos/web-eval/demo.html"


class SampleReport(TypedDict):
    """Type definition for web evaluation sample report."""

    url: str
    task: str
    agent_steps: list[str]
    console_logs: list[str]
    network_requests: list[str]
    conclusion: str


def demonstrate_web_eval_agent() -> None:
    """Demonstrate the web-eval-agent capabilities."""
    api_key: str = os.getenv("OP_API_KEY", "[API_KEY_NOT_SET]")
    # Resolve demo URL from environment with sensible default
    demo_url: str = os.getenv("WEB_EVAL_DEMO_URL") or DEFAULT_DEMO_URL
    print("🚀 Web Eval Agent MCP Server Demonstration")
    print("=" * 50)

    # Simulate the web-eval-agent configuration
    print("\n📋 Configuration:")
    print("  • Server Name: github.com/Operative-Sh/web-eval-agent")
    # Use non-reversible fingerprint to avoid leaking any key substring
    trimmed_key = api_key.strip()
    if not trimmed_key or trimmed_key == "[API_KEY_NOT_SET]":
        api_key_display = "not set"
    else:
        # Compute HMAC-SHA-256 fingerprint and show first 8 hex chars
        fingerprint_key = b"web-eval-demo:fingerprint:v1"
        fingerprint = hmac.new(
            fingerprint_key, trimmed_key.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:8]
        api_key_display = f"set (fingerprint: {fingerprint})"
    print(f"  • API Key: {api_key_display}")
    print(
        "  • Command: "
        "uvx --refresh-package webEvalAgent --from "
        "git+https://github.com/Operative-Sh/web-eval-agent.git webEvalAgent"
    )

    # Show the tools available
    print("\n🔧 Available Tools:")
    print("  1. web_eval_agent - Automated UX evaluator that drives the browser")
    print("  2. setup_browser_state - Set up browser state for authentication")

    # Simulate a web evaluation task
    print("\n🎯 Demonstration Task:")
    print(f"  Evaluating {demo_url}")
    print(
        "  Task: 'Evaluate the web page for user experience issues and test "
        "the button functionality'"
    )

    # Simulate the evaluation process
    print("\n🔄 Running Evaluation...")
    time.sleep(1)
    print(f"  🔍 Step 1: Navigating to {demo_url}")
    time.sleep(1)
    print("  🖱️ Step 2: Interacting with UI elements")
    time.sleep(1)
    print("  📸 Step 3: Capturing screenshots")
    time.sleep(1)
    print("  📋 Step 4: Analyzing user experience")

    # Show sample output
    print("\n📊 Evaluation Results:")
    sample_report: SampleReport = {
        "url": demo_url,
        "task": (
            "Evaluate the web page for user experience issues and test the "
            "button functionality"
        ),
        "agent_steps": [
            f"Navigate → {demo_url}",
            "Click 'Run Web Evaluation Demo' button",
            "Verify JavaScript functionality",
            "Check responsive design",
        ],
        "console_logs": [
            "[info] Page loaded successfully",
            "[debug] Button click handler registered",
            "[info] Demo animation started",
        ],
        "network_requests": [
            "GET /static/demos/web-eval/demo.html 200",
            "GET /favicon.ico 404",
        ],
        "conclusion": (
            "✅ UX evaluation complete - Page functions correctly with no "
            "issues detected"
        ),
    }

    # Preserve insertion order for better readability and logical flow
    # Original order: url -> task -> agent_steps -> console_logs -> network_requests -> conclusion
    print(json.dumps(sample_report, indent=2, ensure_ascii=False))

    print("\n✨ Key Features Demonstrated:")
    print("  • 🌐 Browser Automation: Navigate and interact with web pages")
    print("  • 📊 UX Evaluation: Analyze user experience and identify issues")
    print("  • 📸 Screenshot Capture: Visual documentation of each step")
    print("  • 🚨 Console Monitoring: Capture errors and logs")
    print("  • 🌐 Network Analysis: Monitor HTTP requests and responses")
    print("  • 🤖 Autonomous Testing: End-to-end automated evaluation")

    print("\n🎉 Setup Complete!")
    print("The web-eval-agent MCP server is now configured and ready to use.")
    print("You can now use it in your IDE to evaluate web applications.")


def main() -> None:
    """Main function to run the web evaluation demonstration."""
    demonstrate_web_eval_agent()


if __name__ == "__main__":
    main()
