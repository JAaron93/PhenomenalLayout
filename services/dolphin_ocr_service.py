"""Shim for DolphinOCRService to fix import errors after its removal.

This file provides a dummy DolphinOCRService class to allow the codebase to 
collect and run tests that still depend on the import, even though the 
actual service implementation has moved to dolphin_modal_service.py.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

class DolphinOCRService:
    """Dummy OCR service to maintain backward compatibility for imports."""
    
    def __init__(self, *args, **kwargs):
        logger.warning("DolphinOCRService is deprecated. Use DolphinOCRProcessor from dolphin_modal_service.py instead.")
        pass

    def process_document_images(self, images: list[bytes]) -> dict[str, Any]:
        """Dummy implementation of image processing."""
        return {"pages": [], "total_pages": 0}

    async def process_document_images_async(self, images: list[bytes]) -> dict[str, Any]:
        """Dummy async implementation of image processing."""
        return {"pages": [], "total_pages": 0}
