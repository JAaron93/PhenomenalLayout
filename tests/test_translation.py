import asyncio
import os
import time

import dotenv

from core.translation_handler import (
    get_translation_status,
    process_file_upload,
    start_translation,
    state,
)


async def run_test():
    """Run translation test with a sample PDF."""
    dotenv.load_dotenv()
    # Path relative to this script
    pdf_path = os.environ.get(
        "TEST_PDF_PATH", os.path.join(os.path.dirname(__file__), "sample.pdf")
    )
    if not os.path.exists(pdf_path):
        print(
            f"Test PDF not found at {pdf_path}. Set TEST_PDF_PATH environment variable."
        )
        return

    print(f"Testing translation with {pdf_path}")

    # 1. Upload and process file
    success = False
    try:
        result = await process_file_upload(pdf_path)
        _preview = result.get("preview", "")
        status = result.get("status", "")
        detected_lang = result.get("detected_language", "")
        preproc_info = result.get("preprocessing_info", "")
        _proc_details = result.get("processing_details", "")
        success = result.get("success", False)
    except Exception:
        import traceback

        traceback.print_exc()
        status = "❌ Exception occurred"
        success = False

    print("\n--- Upload Status ---")
    print(status)
    if not success:
        print("Upload failed. Exiting.")
        return

    print(f"Detected language: {detected_lang}")
    print("Preprocessing info:", preproc_info)

    # 2. Start translation to Spanish
    print("\n--- Starting Translation ---")
    start_status, start_upload_status, is_ready = await start_translation(
        target_language="Spanish", max_pages=0, philosophy_mode=False
    )
    print(
        "Start result:",
        start_status,
        "| Upload status:",
        start_upload_status,
        "| Ready:",
        is_ready,
    )

    if not is_ready:
        print(f"\n❌ Translation failed to start!")
        print(f"Status: {start_status}")
        print(f"Upload Status: {start_upload_status}")
        return

    # 3. Monitor translation
    print("\n--- Monitoring Progress ---")
    timeout_seconds = 300  # 5-minute timeout
    start_time = time.monotonic()
    while True:
        elapsed = time.monotonic() - start_time
        if elapsed >= timeout_seconds:
            print(f"\n⚠️ Translation timed out after {timeout_seconds} seconds")
            break

        curr_status, progress, is_done = get_translation_status()
        print(f"Status: {curr_status} | Progress: {progress}%")

        if is_done:
            print("\n✅ Translation completed successfully!")
            print(f"Output saved to: {state.output_file}")
            break

        if state.translation_status == "error":
            print(f"\n❌ Translation failed: {state.error_message}")
            break

        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run_test())
