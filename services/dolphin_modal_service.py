"""Modal Labs deployment service for ByteDance Dolphin OCR.

This service replaces the HuggingFace Spaces API approach with a direct
Modal deployment of the Dolphin OCR model for better performance and control.
"""

import logging
from typing import Annotated, Any

import modal
from fastapi import File, UploadFile

try:
    from dolphin_ocr.logging_config import get_logger, setup_logging

    setup_logging()
    logger = get_logger("modal_service")
except Exception:  # Fallback to local logger if package not available
    logger = logging.getLogger("dolphin_ocr.modal_service")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Modal App Configuration
app = modal.App("dolphin-ocr-service")

# Model and cache configuration
MODEL_CACHE_PATH = "/models"
DOLPHIN_MODEL_ID = "ByteDance/Dolphin"  # Adjust based on actual model ID
PDF2IMAGE_DPI = 300

# Define the container image with all dependencies
dolphin_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "poppler-utils",  # For pdf2image
        "libgl1-mesa-glx",  # For OpenCV
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender-dev",
        "libgomp1",
        "wget",
        "curl",
    )
    .pip_install(
        "torch>=2.0.0",
        "torchvision",
        "transformers>=4.30.0",
        "accelerate",
        "pdf2image>=1.17.0",
        "pillow>=9.0.0",
        "numpy>=1.21.0",
        "opencv-python-headless",
        "huggingface_hub>=0.16.0",
        "hf-transfer>=0.1.0",
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.23.0",
        "python-multipart>=0.0.6",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HUB_CACHE": MODEL_CACHE_PATH,
            "TRANSFORMERS_CACHE": MODEL_CACHE_PATH,
            "TORCH_HOME": MODEL_CACHE_PATH,
        }
    )
)

# Create a persistent volume for model storage
model_volume = modal.Volume.from_name("dolphin-ocr-models", create_if_missing=True)


@app.function(
    image=dolphin_image,
    gpu="T4",  # Start with T4, can upgrade to A10G or L40S if needed
    volumes={MODEL_CACHE_PATH: model_volume},
    timeout=300,
    memory=8192,  # 8GB RAM
    scaledown_window=300,  # 5 minutes
)
def download_model():
    """Download and cache the Dolphin OCR model."""
    from huggingface_hub import snapshot_download

    logger.info("Downloading Dolphin OCR model...")

    # Download the model to the persistent volume
    try:
        model_path = snapshot_download(
            repo_id=DOLPHIN_MODEL_ID,
            cache_dir=MODEL_CACHE_PATH,
            local_dir_use_symlinks=False,
        )
    except Exception as e:
        logger.exception("Failed to download model: %s", e)
        raise

    logger.info(f"Model downloaded to: {model_path}")
    return model_path


@app.cls(
    image=dolphin_image,
    gpu="T4",  # Adjust based on performance needs
    volumes={MODEL_CACHE_PATH: model_volume},
    timeout=600,  # 10 minutes for processing
    memory=8192,
    scaledown_window=600,  # 10 minutes
)
class DolphinOCRProcessor:
    """Cached Dolphin OCR processor that loads model once and reuses it."""

    # Use modal.enter() instead of __init__ for Modal 1.0+ compatibility
    @modal.enter()
    def initialize_model(self):
        """Initialize the processor and load the model once."""
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor

        logger.info("Initializing Dolphin OCR processor...")
        logger.info(
            "Loading Dolphin OCR model and processor (one-time initialization)..."
        )

        # Load the model and processor once during initialization
        # Use the path returned by snapshot_download or a consistent location
        # Use the actual model ID for loading
        self.processor = AutoProcessor.from_pretrained(
            DOLPHIN_MODEL_ID, cache_dir=MODEL_CACHE_PATH
        )
        self.model = AutoModelForVision2Seq.from_pretrained(
            DOLPHIN_MODEL_ID,
            cache_dir=MODEL_CACHE_PATH,
            torch_dtype=torch.float16,
            device_map="auto",
        )

        # Set model to evaluation mode
        self.model.eval()

        logger.info(
            "✅ Dolphin OCR model and processor loaded successfully! Device: %s",
            self.model.device,
        )

    @modal.method()
    def process_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """Process a PDF with Dolphin OCR using cached model and processor.

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            Dictionary containing OCR results with layout information
        """
        import torch
        from pdf2image import convert_from_bytes

        logger.info("Processing PDF with cached Dolphin OCR model...")

        # Convert PDF to images
        try:
            images = convert_from_bytes(
                pdf_bytes,
                dpi=PDF2IMAGE_DPI,
                fmt="RGB",
                thread_count=2,
            )
        except Exception as e:
            logger.exception("Failed to convert PDF")
            raise ValueError(f"PDF conversion failed: {e!s}") from e

        logger.debug("Processing %d pages...", len(images))

        results = []

        for page_num, image in enumerate(images):
            logger.debug("Processing page %d/%d", page_num + 1, len(images))

            # Process the image with Dolphin using cached model and processor
            inputs = self.processor(images=image, return_tensors="pt").to(
                self.model.device
            )

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=2048,
                    do_sample=False,
                    temperature=0.0,
                )

            # Decode the output
            generated_text = self.processor.batch_decode(
                outputs, skip_special_tokens=True
            )[0]

            # Parse the Dolphin output into structured blocks with bbox/confidence
            blocks = parse_dolphin_output(generated_text, image.width, image.height)

            page_result = {
                "page_number": page_num + 1,
                "width": image.width,
                "height": image.height,
                "text_blocks": blocks,
                "raw_output": generated_text,
            }

            results.append(page_result)

        return {
            "pages": results,
            "total_pages": len(results),
            "processing_metadata": {
                "processor": "dolphin_ocr_modal_cached",
                "model_id": DOLPHIN_MODEL_ID,
                "dpi": PDF2IMAGE_DPI,
            },
        }


# Create a global instance for backward compatibility
dolphin_processor = DolphinOCRProcessor()


@app.function(
    image=dolphin_image,
    gpu="T4",
    volumes={MODEL_CACHE_PATH: model_volume},
    timeout=600,
    memory=8192,
    scaledown_window=600,  # 10 minutes
)
def process_pdf_with_dolphin(pdf_bytes: bytes) -> dict[str, Any]:
    """Process a PDF with Dolphin OCR using cached model (backward compatibility wrapper).

    This function maintains backward compatibility while using the cached processor.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Dictionary containing OCR results with layout information
    """
    return dolphin_processor.process_pdf.remote(pdf_bytes)


def parse_dolphin_output(
    raw_output: str, page_width: int, page_height: int
) -> list[dict[str, Any]]:
    """Parse Dolphin OCR output into structured text blocks.

    The parser is defensive and supports multiple shapes:
    - Direct JSON list of blocks or dict with a "blocks" key
    - JSON embedded within text (first JSON payload is extracted)
    - Line-based records containing bbox/conf/text fields
    - Fallback: non-empty lines as blocks spanning the full page

    Returns a list of dicts with keys: text, bbox [x1,y1,x2,y2], confidence, block_type.
    """
    import json as _json
    import logging as _logging
    import re as _re

    def _clip_bbox(b: list[float]) -> list[float]:
        x1, y1, x2, y2 = b
        x1 = max(0.0, min(float(x1), float(page_width)))
        y1 = max(0.0, min(float(y1), float(page_height)))
        x2 = max(0.0, min(float(x2), float(page_width)))
        y2 = max(0.0, min(float(y2), float(page_height)))
        return [x1, y1, x2, y2]

    def _norm_block(obj: dict[str, Any]) -> dict[str, Any]:
        text = str(obj.get("text", "")).strip()
        bbox = obj.get("bbox") or obj.get("box") or obj.get("bounds")
        if isinstance(bbox, dict):
            # Support {x1:.., y1:.., x2:.., y2:..}
            bbox = [
                bbox.get("x1", 0),
                bbox.get("y1", 0),
                bbox.get("x2", page_width),
                bbox.get("y2", page_height),
            ]
        if not (isinstance(bbox, list | tuple) and len(bbox) == 4):
            # Default to full page span if missing
            bbox = [0, 0, page_width, page_height]
        conf = obj.get("confidence") or obj.get("conf") or obj.get("score")
        try:
            confidence = float(conf) if conf is not None else 1.0
        except Exception:
            confidence = 1.0
        block_type = obj.get("block_type") or obj.get("type") or "text"
        return {
            "text": text,
            "bbox": _clip_bbox([*bbox]),
            "confidence": confidence,
            "block_type": str(block_type),
        }

    # 1) Try direct JSON parse first
    try:
        parsed = _json.loads(raw_output)
        if (
            isinstance(parsed, dict)
            and "blocks" in parsed
            and isinstance(parsed["blocks"], list)
        ):
            return [_norm_block(b) for b in parsed["blocks"] if isinstance(b, dict)]
        if isinstance(parsed, list):
            return [_norm_block(b) for b in parsed if isinstance(b, dict)]
    except Exception:
        pass

    # 2) Try to extract JSON payload embedded in text
    try:
        m = _re.search(r"(\{.*?\}|\[.*?\])", raw_output, flags=_re.DOTALL)
        if m:
            payload = m.group(1)
            parsed = _json.loads(payload)
            if (
                isinstance(parsed, dict)
                and "blocks" in parsed
                and isinstance(parsed["blocks"], list)
            ):
                return [_norm_block(b) for b in parsed["blocks"] if isinstance(b, dict)]
            if isinstance(parsed, list):
                return [_norm_block(b) for b in parsed if isinstance(b, dict)]
    except Exception:
        pass

    # 3) Parse line-based format: bbox=[x1,y1,x2,y2] conf=0.95 text="..." type=...
    blocks: list[dict[str, Any]] = []
    line_pattern = _re.compile(
        r"bbox\s*[:=]\s*[\[\(]?\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*[\]\)]?"  # bbox
        r".*?(?:conf(?:idence)?|score)\s*[:=]\s*([0-9.]+)"  # confidence
        r".*?text\s*[:=]\s*\"?(.*?)\"?(?:\s|$)",  # text
        flags=_re.IGNORECASE,
    )
    for line in raw_output.splitlines():
        m = line_pattern.search(line)
        if not m:
            continue
        x1, y1, x2, y2, conf, text = m.groups()
        try:
            bbox = _clip_bbox([float(x1), float(y1), float(x2), float(y2)])
            confidence = float(conf)
        except Exception:
            bbox = [0, 0, page_width, page_height]
            confidence = 1.0
        blocks.append(
            {
                "text": text.strip(),
                "bbox": bbox,
                "confidence": confidence,
                "block_type": "text",
            }
        )

    if blocks:
        return blocks

    # 4) Fallbacks: split on blank lines for paragraphs, use full-page bbox
    _logging.warning("Falling back to simple Dolphin output parsing")
    paras = [p.strip() for p in raw_output.splitlines() if p.strip()]
    if not paras:
        return []
    full_bbox = [0, 0, page_width, page_height]
    return [
        {"text": p, "bbox": full_bbox, "confidence": 1.0, "block_type": "text"}
        for p in paras
    ]


@app.function(
    image=dolphin_image,
    timeout=630,  # Slightly longer than processing function timeout
)
@modal.fastapi_endpoint(method="POST", docs=True)
async def dolphin_ocr_endpoint(
    pdf_file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """HTTP endpoint for Dolphin OCR processing.

    Compatible with the existing dolphin_client.py interface.
    """
    # Validate file size (example: 50MB limit)
    max_file_size = 50 * 1024 * 1024

    # Read the file content
    pdf_content = await pdf_file.read()

    if len(pdf_content) > max_file_size:
        return {
            "error": "File too large. Maximum size is 50MB.",
            "status": "failed",
        }

    try:
        # Process the PDF using cached processor for better performance
        # Properly invoke the Modal function
        result = process_pdf_with_dolphin.remote(pdf_content)
        return result
    except ValueError as e:
        return {
            "error": f"Invalid input: {e!s}",
            "status": "failed",
        }
    except Exception:
        logger.exception("Unexpected error in OCR endpoint")
        return {
            "error": "Internal server error during OCR processing",
            "status": "failed",
        }


@app.function()
def setup_dolphin_service():
    """Initialize the Dolphin service by downloading the model."""
    logger.info("Setting up Dolphin OCR service...")
    model_path = download_model.remote()
    logger.info("Dolphin service ready! Model at: %s", model_path)
    return model_path


if __name__ == "__main__":
    # For local testing
    with app.run():
        setup_dolphin_service.remote()
