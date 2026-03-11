#!/usr/bin/env python3
"""Modal Labs deployment script for the Dolphin OCR Translation project.

This script handles:
1. Deploying the Dolphin OCR microservice to Modal
2. Setting up the main translation application
3. Configuring environment variables and secrets
"""

import os
import sys

# Default Modal endpoint URL - users should set MODAL_ENDPOINT_BASE env var
DEFAULT_MODAL_ENDPOINT: str = (
    "https://modal-labs--dolphin-ocr-service-dolphin-ocr-endpoint.modal.run"
)

# Optional (non-fatal) environment variables recognized by deployment.
# DOLPHIN_ENDPOINT can be provided here for convenience during validation,
# but it is still validated as required in validate_environment_variables.
OPTIONAL_ENV_VARS: list[str] = [
    "HF_TOKEN",  # HuggingFace token for model downloads
    "PDF_DPI",
    "MAX_CONCURRENT_REQUESTS",
    "MAX_REQUESTS_PER_SECOND",
    "TRANSLATION_BATCH_SIZE",
    "TRANSLATION_MAX_RETRIES",
    "TRANSLATION_REQUEST_TIMEOUT",
    "GRADIO_SHARE",
    "GRADIO_SCHEMA_PATCH",
]


def validate_environment_variables() -> (
    tuple[list[str], list[str], list[str], list[str]]
):
    """Validate environment variables and return validation results.

    Returns:
        tuple: (missing_required, empty_required, missing_optional, empty_optional)
               where each element is a list of variable names
    """
    required_vars: list[str] = [
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "LINGO_API_KEY",
    ]
    optional_vars: list[str] = [v for v in OPTIONAL_ENV_VARS if v not in required_vars]

    missing_required: list[str] = []
    empty_required: list[str] = []
    missing_optional: list[str] = []
    empty_optional: list[str] = []

    # Validate required variables
    for var in required_vars:
        value: str | None = os.getenv(var)
        if value is None:
            missing_required.append(var)
        elif not value.strip():
            empty_required.append(var)

    # Validate optional variables
    for var in optional_vars:
        value = os.getenv(var)
        if value is None:
            missing_optional.append(var)
        elif not value.strip():
            empty_optional.append(var)

    return missing_required, empty_required, missing_optional, empty_optional


def report_environment_validation(
    missing_required: list[str],
    empty_required: list[str],
    missing_optional: list[str],
    empty_optional: list[str],
) -> bool:
    """Report environment variable validation results to the user.

    Args:
        missing_required: List of missing required variables
        empty_required: List of empty required variables
        missing_optional: List of missing optional variables
        empty_optional: List of empty optional variables

    Returns:
        bool: True if all required variables are valid, False otherwise
    """
    # Report required variable issues
    invalid_required: list[str] = missing_required + empty_required
    if invalid_required:
        print("❌ Invalid required environment variables:")
        for var in missing_required:
            print(f"   - {var} (not set)")
        for var in empty_required:
            print(f"   - {var} (empty value)")
        print("\nPlease set these variables in your .env file or environment.")
        return False

    print("✅ All required environment variables are set")

    # Report optional variable status
    all_optional: list[str] = missing_optional + empty_optional
    for var in all_optional:
        if var in missing_optional:
            print(f"⚠️  Optional variable {var} is not set")
        else:
            print(f"⚠️  Optional variable {var} is set but empty")

    # Report successfully set optional variables
    for var in OPTIONAL_ENV_VARS:
        if var not in all_optional:
            value = os.getenv(var)
            if value and value.strip():
                print(f"✅ Optional variable {var} is set")

    return True


def check_environment_variables() -> bool:
    """Check that all required environment variables are set and valid.

    Returns:
        bool: True if all required variables are valid, False otherwise
    """
    (
        missing_required,
        empty_required,
        missing_optional,
        empty_optional,
    ) = validate_environment_variables()
    return report_environment_validation(
        missing_required, empty_required, missing_optional, empty_optional
    )


def build_secret_command(env_data: dict[str, str | None]) -> str:
    """Build a quoted Modal secret creation command from provided env data."""
    secret_cmd: str = "modal secret create translation-api"
    for key in env_data:
        placeholder: str = "'<your-" + key.lower().replace("_", "-") + ">'"
        secret_cmd += f" {key}={placeholder}"
    return secret_cmd


def prepare_modal_secrets() -> str:
    """Prepare Modal secret creation commands for the application.

    Returns:
        str: The constructed secret creation command with quoted placeholders.
    """
    print("🔐 Creating Modal secrets...")

    # Create translation API secret
    translation_secret_data: dict[str, str | None] = {
        "LINGO_API_KEY": os.getenv("LINGO_API_KEY"),
    }

    # Add HuggingFace token if available
    if os.getenv("HF_TOKEN"):
        translation_secret_data["HF_TOKEN"] = os.getenv("HF_TOKEN")

    # Create the secret using Modal CLI (this would need to be run separately)
    print("📝 Translation API secret data prepared")
    print("   Run this command to create the secret:")
    secret_cmd: str = build_secret_command(translation_secret_data)
    print(f"   {secret_cmd}")
    print(
        "   Note: quote your values or export them as env vars to avoid "
        "shell interpretation issues."
    )
    return secret_cmd


def deploy_dolphin_service() -> bool:
    """Deploy the Dolphin OCR service via Modal SDK or CLI.

    Attempts SDK deployment first; falls back to the `modal` CLI.
    Returns True on success, False on failure.
    """
    print("🚀 Deploying Dolphin OCR service...")

    module_path: str = "services/dolphin_modal_service.py"

    # Try Modal SDK
    try:
        import modal  # type: ignore

        deploy_fn = getattr(modal, "deploy", None)
        if callable(deploy_fn):
            deploy_fn(module_path)
            print("✅ Modal deploy completed via SDK")
            return True
    except Exception as err:
        print(f"ℹ️  Modal SDK deploy unavailable or failed: {err}")

    # Fallback to Modal CLI
    try:
        import shutil
        import subprocess

        modal_bin: str | None = shutil.which("modal")
        if not modal_bin:
            print("❌ 'modal' CLI not found. Install Modal CLI or use the SDK.")
            return False

        result: subprocess.CompletedProcess[str] = subprocess.run(
            [modal_bin, "deploy", module_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.stdout:
            print("CLI Output:", result.stdout)
        if result.stderr:
            print("CLI Errors:", result.stderr, file=sys.stderr)
        print("✅ Modal CLI deploy completed")
        return True
    except subprocess.CalledProcessError as err:
        print("❌ Modal CLI deploy failed", file=sys.stderr)
        if err.stdout:
            print(err.stdout, file=sys.stderr)
        if err.stderr:
            print(err.stderr, file=sys.stderr)
        return False
    except subprocess.TimeoutExpired as err:
        print(
            f"❌ Modal CLI deploy timed out after {err.timeout} seconds", file=sys.stderr
        )
        if getattr(err, "output", None):
            print("CLI Output:", err.output, file=sys.stderr)
        if err.stderr:
            print("CLI Errors:", err.stderr, file=sys.stderr)
        return False
    except Exception as err:
        print(f"❌ Deployment error: {err}", file=sys.stderr)
        return False


def deploy_main_application() -> bool:
    """Deploy the main translation application."""
    print("🚀 Deploying main translation application...")

    # This would be implemented when we create the main Modal app
    print("📝 Main application deployment not yet implemented")
    print("   This will include the Gradio UI and translation pipeline")

    return True


def main() -> None:
    """Main deployment function."""
    print("🌊 Modal Labs Deployment for Dolphin OCR Translation")
    print("=" * 60)

    # Step 1: Check environment variables
    if not check_environment_variables():
        sys.exit(1)

    # Step 2: Create Modal secrets
    secret_cmd: str = prepare_modal_secrets()

    # Step 3: Deploy Dolphin service
    if not deploy_dolphin_service():
        sys.exit(1)

    # Step 3.5: Check DOLPHIN_ENDPOINT after deployment
    # On first-time setup, DOLPHIN_ENDPOINT doesn't exist until after deploying the Dolphin service
    if not os.getenv("DOLPHIN_ENDPOINT"):
        print("\n⚠️  DOLPHIN_ENDPOINT is not set")
        print(
            "   This is expected on first-time setup since the endpoint doesn't exist"
        )
        print("   until after deploying the Dolphin service.")
        print(
            "\n   After deployment completes, set DOLPHIN_ENDPOINT to the service URL:"
        )
        endpoint_url: str = (
            os.getenv("DOLPHIN_MODAL_ENDPOINT")
            or os.getenv("MODAL_ENDPOINT_BASE", DEFAULT_MODAL_ENDPOINT)
        )
        print(f"   export DOLPHIN_ENDPOINT={endpoint_url}")
        print("\n   Then run the test script to verify the deployment:")
        print("   python -m scripts.test_modal_deployment")

    # Step 4: Deploy main application
    if not deploy_main_application():
        sys.exit(1)

    print("\n✅ Deployment preparation complete!")
    print("\nNext steps:")
    print("1. Create the Modal secret:")
    print(f"   {secret_cmd}")
    if os.getenv("HF_TOKEN"):
        print("   (HF_TOKEN will be included automatically)")

    print("\n2. Deploy the Dolphin OCR service:")
    print("   modal deploy services/dolphin_modal_service.py")

    # Only show DOLPHIN_ENDPOINT setup if it wasn't already shown above
    if os.getenv("DOLPHIN_ENDPOINT"):
        print(f"\n3. Current DOLPHIN_ENDPOINT: {os.getenv('DOLPHIN_ENDPOINT')}")
        print("   (If this differs from actual deployment URL, update accordingly)")

    print("\n4. Test the deployment:")
    print("   python -m scripts.test_modal_deployment")


if __name__ == "__main__":
    main()
