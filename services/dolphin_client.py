"""Async client for the Dolphin PDF layout micro-service.

This client supports both local microservice and Modal Labs deployment.
The official Modal deployment is hosted by the 'modal-labs' organization.
Personal deployments (e.g., for billing or forked development) can be
configured via the DOLPHIN_MODAL_ENDPOINT environment variable.

The service exposes an endpoint that accepts a multipart upload of a PDF file
and returns JSON describing the page layouts. This helper wraps the HTTP call
so the rest of the codebase doesn't need to know the wire format.
"""

from __future__ import annotations

import logging
import math
import os
import pathlib
from typing import Any

import httpx

logger: logging.Logger = logging.getLogger(__name__)

# Canonical set of allowed block types for validation (immutable)
ALLOWED_BLOCK_TYPES = frozenset(
    {
        "text",  # Regular text content
        "title",  # Document titles and headings
        "header",  # Page headers
        "footer",  # Page footers
        "image",  # Image content
        "table",  # Tabular data
        "figure",  # Figures and diagrams
        "caption",  # Figure/table captions
        "list",  # List items
        "paragraph",  # Paragraph blocks
    }
)

# Default endpoints - Modal Labs takes priority
# Fallback is the official modal-labs namespace; override via environment variables for personal use.
DEFAULT_MODAL_ENDPOINT: str = (
    "https://modal-labs--dolphin-ocr-service-dolphin-ocr-endpoint.modal.run"
)
DEFAULT_LOCAL_ENDPOINT: str = "http://localhost:8501/layout"
DEFAULT_TIMEOUT: int = 300  # seconds (increased for Modal processing)


def validate_dolphin_layout_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the response structure and bbox coordinates from Dolphin service.

    This function validates that bboxes have valid coordinates, allowing zero
    extents for single characters or dots that may appear in OCR results.

    Args:
        data: The response data from the Dolphin service

    Returns:
        The validated data (same object, for chaining)

    Raises:
        ValueError: If the response structure or bbox coordinates are invalid
    """
    # Basic validation - check if response has the expected structure
    if not isinstance(data, dict) or "pages" not in data:
        raise ValueError(
            "Invalid response format from Dolphin service: missing 'pages' key"
        )

    if not isinstance(data["pages"], list):
        raise ValueError(
            "Invalid response format from Dolphin service: 'pages' is not a list"
        )

    # Validate each page in the response
    for i, page in enumerate(data["pages"]):
        if not isinstance(page, dict):
            raise ValueError(f"Page {i} is not a dictionary")

        # Check for required page-level fields (updated for Modal format)
        required_fields: list[str] = ["page_number", "width", "height", "text_blocks"]
        missing = [f for f in required_fields if f not in page]
        if missing:
            raise ValueError(
                f"Page {i} is missing required fields: {', '.join(missing)}"
            )

        # Validate text_blocks array (Modal format uses text_blocks)
        if not isinstance(page["text_blocks"], list):
            raise ValueError(f"Page {i} 'text_blocks' is not a list")

        # Validate each text block in the page
        for j, block in enumerate(page["text_blocks"]):
            if not isinstance(block, dict):
                raise ValueError(f"Text block {j} in page {i} is not a dictionary")

            # Check for required text block fields (Modal format)
            block_required: list[str] = ["text", "bbox", "confidence", "block_type"]
            missing = [f for f in block_required if f not in block]
            if missing:
                raise ValueError(
                    f"Text block {j} in page {i} is missing required fields: "
                    f"{', '.join(missing)}"
                )

            # Semantic validation: confidence must be numeric and between 0 and 1
            confidence = block.get("confidence")
            if not isinstance(confidence, (int, float)):
                raise ValueError(
                    f"Page {i}, block {j}: confidence must be numeric, got "
                    f"{type(confidence).__name__} with value {confidence}"
                )
            if not (0.0 <= confidence <= 1.0):
                raise ValueError(
                    f"Page {i}, block {j}: confidence must be between 0 and 1, "
                    f"got {confidence}"
                )

            # Semantic validation: block_type must be in allowed set
            block_type = block.get("block_type")
            if block_type not in ALLOWED_BLOCK_TYPES:
                raise ValueError(
                    f"Page {i}, block {j}: invalid block_type '{block_type}', "
                    f"must be one of: {', '.join(sorted(ALLOWED_BLOCK_TYPES))}"
                )

            # Validate bbox format and bounds
            bbox_coords: list[int | float] = block.get("bbox", [])
            if not (
                isinstance(bbox_coords, list)
                and len(bbox_coords) == 4
                and all(isinstance(coord, (int, float)) for coord in bbox_coords)
            ):
                raise ValueError(
                    f"Page {i}, block {j}: invalid bbox format. "
                    f"Expected [x0, y0, x1, y1], got {bbox_coords}"
                )

            x0, y0, x1, y1 = bbox_coords

            # Validate bbox extents are valid (zero extents allowed for single chars/dots)
            if x1 < x0 or y1 < y0:
                raise ValueError(
                    f"Page {i}, block {j}: invalid bbox extents: {bbox_coords}"
                )

            # Validate bbox coordinates are within page bounds when available
            page_width = page.get("width")
            page_height = page.get("height")

            if page_width is not None and page_height is not None:
                # Ensure page dimensions are numeric, finite, and positive
                if not isinstance(page_width, (int, float)) or not isinstance(
                    page_height, (int, float)
                ):
                    raise ValueError(
                        f"Page {i}: width/height must be numeric, got "
                        f"{type(page_width).__name__}/{type(page_height).__name__}"
                    )
                if not (math.isfinite(page_width) and math.isfinite(page_height)):
                    raise ValueError(
                        f"Page {i}: width/height must be finite, got {page_width}/{page_height}"
                    )
                if page_width <= 0 or page_height <= 0:
                    raise ValueError(
                        f"Page {i}: width/height must be positive, got {page_width}/{page_height}"
                    )
                if not (0 <= x0 <= page_width and 0 <= x1 <= page_width):
                    raise ValueError(
                        f"Page {i}, block {j}: bbox x-coordinates {x0}, {x1} "
                        f"outside page width {page_width}: {bbox_coords}"
                    )
                if not (0 <= y0 <= page_height and 0 <= y1 <= page_height):
                    raise ValueError(
                        f"Page {i}, block {j}: bbox y-coordinates {y0}, {y1} "
                        f"outside page height {page_height}: {bbox_coords}"
                    )
            else:
                # If page dimensions not available, just ensure non-negative
                if x0 < 0 or y0 < 0 or x1 < 0 or y1 < 0:
                    raise ValueError(
                        f"Page {i}, block {j}: negative bbox coordinates: "
                        f"{bbox_coords}"
                    )

    return data


async def get_layout(pdf_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Send *pdf_path* to the Dolphin service and return the JSON payload.

    Parameters
    ----------
    pdf_path: str | PathLike
        Absolute path to the PDF (single or multi-page) to analyse.

    Returns:
    -------
    dict
        Whatever JSON structure the Dolphin service responds with.  The caller
        is responsible for interpreting the schema.
    """
    # Determine which endpoint to use based on configuration
    # Check for DOLPHIN_ENDPOINT_TYPE env var first (modal or local)
    endpoint_type = os.getenv("DOLPHIN_ENDPOINT_TYPE", "modal").lower()
    
    if endpoint_type == "local":
        # Use local endpoint with custom URL if provided
        endpoint = os.getenv("DOLPHIN_LOCAL_ENDPOINT", DEFAULT_LOCAL_ENDPOINT)
    else:
        # Use Modal endpoint (default)
        # Prioritize specific DOLPHIN_MODAL_ENDPOINT, then fallback to DOLPHIN_ENDPOINT or the default
        endpoint = (
            os.getenv("DOLPHIN_MODAL_ENDPOINT") 
            or os.getenv("DOLPHIN_ENDPOINT") 
            or DEFAULT_MODAL_ENDPOINT
        )
    
    pdf_path = pathlib.Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Get timeout from environment variable or use default
    try:
        timeout_seconds: int = int(
            os.getenv("DOLPHIN_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT))
        )
    except ValueError:
        logger.warning(
            f"Invalid DOLPHIN_TIMEOUT_SECONDS value, using default: {DEFAULT_TIMEOUT}"
        )
        timeout_seconds = DEFAULT_TIMEOUT
    else:
        if timeout_seconds <= 0:
            logger.warning(
                f"Non-positive DOLPHIN_TIMEOUT_SECONDS={timeout_seconds}, using default: {DEFAULT_TIMEOUT}"
            )
            timeout_seconds = DEFAULT_TIMEOUT

    # Use streaming upload to avoid loading big PDFs fully into memory.
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        with pdf_path.open("rb") as fp:
            files: dict[str, Any] = {"file": (pdf_path.name, fp, "application/pdf")}
            try:
                response: httpx.Response = await client.post(endpoint, files=files)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error(
                    "Dolphin request to %s failed: %s: %s",
                    endpoint,
                    type(exc).__name__,
                    exc,
                )
                raise

    try:
        data: dict[str, Any] = response.json()
    except ValueError as e:
        raise ValueError(f"Invalid JSON response from Dolphin service: {e}") from e

    # Validate the response using the dedicated validation function
    validate_dolphin_layout_response(data)
    return data
