"""Utilities for OCR processing and parsing."""

from typing import Any

from dolphin_ocr.layout import BoundingBox, FontInfo
from services.layout_aware_translation_service import LayoutContext, TextBlock

def parse_ocr_result(result: dict[str, Any]) -> list[list[TextBlock]]:
    """Convert OCR JSON into per-page TextBlocks.

    The expected shape in the result is flexible. We look for:
    result["pages"][i]["text_blocks"] where each block has:
      - text: str
      - bbox: [x, y, w, h]
      - font_info: {family, size, weight, style, color}
      - confidence: float (optional)
    Missing fields fall back to reasonable defaults.
    """
    pages_out: list[list[TextBlock]] = []
    pages = result.get("pages", []) if isinstance(result, dict) else []
    for page in pages:
        page_blocks: list[TextBlock] = []
        blocks = page.get("text_blocks", []) if isinstance(page, dict) else []
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            text = str(blk.get("text", ""))
            bbox = blk.get("bbox", [0.0, 0.0, 100.0, 20.0])
            font = blk.get("font_info", {})
            color_raw = font.get("color", (0, 0, 0))
            if isinstance(color_raw, (list, tuple)) and len(color_raw) >= 3:
                color = tuple(color_raw[:3])
            else:
                color = (0, 0, 0)
            try:
                font_info = FontInfo(
                    family=str(font.get("family", "Helvetica")),
                    size=float(font.get("size", 12.0)),
                    weight=str(font.get("weight", "normal")),
                    style=str(font.get("style", "normal")),
                    color=(int(color[0]), int(color[1]), int(color[2])),
                )
            except (TypeError, ValueError):
                font_info = FontInfo(
                    family="Helvetica",
                    size=12.0,
                    weight="normal",
                    style="normal",
                    color=(0, 0, 0),
                )
            # Validate and sanitize bbox values
            try:
                bbox_values = [
                    float(bbox[i]) if i < len(bbox) else 0.0 for i in range(4)
                ]
                if bbox_values[2] <= 0:
                    bbox_values[2] = 100.0
                if bbox_values[3] <= 0:
                    bbox_values[3] = 20.0
            try:
                ocr_conf = float(blk["confidence"]) if "confidence" in blk else None
            except (TypeError, ValueError):
                ocr_conf = None

            layout_ctx = LayoutContext(
                bbox=BoundingBox(
                    bbox_values[0],
                    bbox_values[1],
                    bbox_values[2],
                    bbox_values[3],
                ),
                font=font_info,
                ocr_confidence=ocr_conf,
            )
            layout_ctx = LayoutContext(
                bbox=BoundingBox(
                    bbox_values[0],
                    bbox_values[1],
                    bbox_values[2],
                    bbox_values[3],
                ),
                font=font_info,
                ocr_confidence=(
                    float(blk["confidence"]) if "confidence" in blk else None
                ),
            )
            page_blocks.append(TextBlock(text=text, layout=layout_ctx))
        pages_out.append(page_blocks)
    return pages_out
