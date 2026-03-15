import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath("."))

from core.translation_handler import process_file_upload, start_translation, get_translation_status, state
import dotenv

async def run_test():
    dotenv.load_dotenv()
    pdf_path = "/Users/pretermodernist/PhenomenalLayout/sample.pdf"
    
    print(f"Testing translation with {pdf_path}")
    
    try:
        preview, status, detected_lang, preproc_info, proc_details = await process_file_upload(pdf_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        status = "❌ Exception occurred"
    
    print("\n--- Upload Status ---")
    print(status)
    if not status.startswith("✅"):
        print("Upload failed. Exiting.")
        return
        
    print(f"Detected language: {detected_lang}")
    print("Preprocessing info:", preproc_info)
    
    # 2. Start translation to Spanish
    print("\n--- Starting Translation ---")
    start_status, start_upload_status, is_ready = await start_translation("Spanish", 0, False)
    print("Start result:", start_status)
    
    # 3. Monitor translation
    print("\n--- Monitoring Progress ---")
    while True:
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
