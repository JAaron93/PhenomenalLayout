from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class ExtractTextResult:
    """Result of text extraction per page and summary metadata."""

    text_per_page: list[str]
    warnings: list[str]
    warning_counts: dict[str, int]
    used_ocr_pages: list[int]
    extractor_summary: str


class PDFQualityValidator:
    """Helpers for PDF quality validation and lightweight comparison.

    Implements hybrid text extraction with direct (pypdf/pdfminer) methods
    and OCR fallback, streaming in batches to avoid OOM. Also provides
    simple text accuracy and layout-hash length similarity checks.
    """

    # Environment-driven defaults
    DEFAULT_MAX_PAGES = int(os.getenv("PDF_QUALITY_MAX_PAGES", "200"))
    DEFAULT_OVERALL_TIMEOUT_S = float(
        os.getenv("PDF_QUALITY_OVERALL_TIMEOUT_SECONDS", "60")
    )
    DEFAULT_OCR_TIMEOUT_S = float(os.getenv("PDF_QUALITY_OCR_TIMEOUT_SECONDS", "5"))
    DEFAULT_PDFMINER_CHUNK = int(os.getenv("PDF_QUALITY_PDFMINER_CHUNK_SIZE", "16"))
    DEFAULT_OCR_BATCH_PAGES = int(os.getenv("PDF_QUALITY_OCR_BATCH_PAGES", "8"))
    DEFAULT_PDF_DPI = int(os.getenv("PDF_DPI", "300"))
    DEFAULT_TESS_LANG = os.getenv("TESSERACT_LANG", "eng")
    DEFAULT_POPPLER_PATH = os.getenv("POPPLER_PATH")

    @staticmethod
    def _truncate(text: str, limit: int = 200) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 12] + " … (truncated)"

    @staticmethod
    def _aggregate_warnings(warnings: Iterable[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for w in warnings:
            counts[w] = counts.get(w, 0) + 1
        return counts

    def _elapsed_exceeded(self, start_ts: float, overall_timeout_s: float) -> bool:
        return time.time() - start_ts >= overall_timeout_s

    # ---------------------------- Extraction ----------------------------
    def extract_text_hybrid(
        self,
        pdf_path: str,
        *,
        max_pages: int | None = None,
        lang: str | None = None,
        overall_timeout_seconds: float | None = None,
        pdfminer_chunk_size: int | None = None,
        ocr_batch_pages: int | None = None,
        dpi: int | None = None,
        poppler_path: str | None = None,
    ) -> ExtractTextResult:
        """Extract text using pypdf/pdfminer with OCR fallback per page.

        - Uses pypdf first for speed and to capture born-digital text.
        - Fallback to pdfminer.six for empty pages to improve coverage.
        - Fallback to OCR (pytesseract) per-page, in image batches via
          pdf2image.convert_from_path to reduce reopening overhead.
        - Caps pages and time to avoid OOM/long runtimes.

        Returns text per page, warnings with aggregated counts, list of
        OCR-used page indices (1-based), and a short extractor summary.
        """
        # Resolve effective configuration
        effective_max_pages = max_pages or self.DEFAULT_MAX_PAGES
        overall_timeout = (
            overall_timeout_seconds
            if overall_timeout_seconds is not None
            else self.DEFAULT_OVERALL_TIMEOUT_S
        )
        pdfminer_chunk = pdfminer_chunk_size or self.DEFAULT_PDFMINER_CHUNK
        ocr_batch = ocr_batch_pages or self.DEFAULT_OCR_BATCH_PAGES
        target_dpi = dpi or self.DEFAULT_PDF_DPI
        tess_lang = (lang or self.DEFAULT_TESS_LANG) or "eng"
        poppler_path = (
            poppler_path if poppler_path is not None else self.DEFAULT_POPPLER_PATH
        )

        # Normalize/clamp configuration values to safe minimums
        if max_pages is not None and max_pages < 1:
            effective_max_pages = 1
        if dpi is not None and dpi < 72:
            target_dpi = 72

        warnings_out: list[str] = []
        ocr_pages: list[int] = []
        start_ts = time.time()

        # 1) Determine number of pages via pypdf if possible
        total_pages = 0
        pypdf_reader = None
        try:
            pypdf = importlib.import_module("pypdf")
            pypdf_reader = pypdf.PdfReader(pdf_path)
            total_pages = len(pypdf_reader.pages)
        except (ImportError, OSError, ValueError) as e:
            warnings_out.append(f"pypdf open failed: {type(e).__name__}")

        if total_pages <= 0:
            # Try pdfminer to estimate pages by iterating pages quickly
            try:
                pdfminer_pdfpage = importlib.import_module("pdfminer.pdfpage")
                pdfminer_pdfparser = importlib.import_module("pdfminer.pdfparser")
                pdfminer_pdfdocument = importlib.import_module("pdfminer.pdfdocument")

                with open(pdf_path, "rb") as fh:
                    parser = pdfminer_pdfparser.PDFParser(fh)
                    doc = pdfminer_pdfdocument.PDFDocument(parser)
                    total_pages = sum(
                        1 for _ in pdfminer_pdfpage.PDFPage.create_pages(doc)
                    )
            except (ImportError, OSError, ValueError) as e:
                warnings_out.append(
                    "pdfminer page count failed: " f"{type(e).__name__}"
                )

        if total_pages <= 0:
            # Give up early with clear message
            msg = "Unable to determine page count; cannot extract text"
            warnings_out.append(msg)
            return ExtractTextResult(
                text_per_page=[],
                warnings=warnings_out,
                warning_counts=self._aggregate_warnings(warnings_out),
                used_ocr_pages=[],
                extractor_summary="none",
            )

        capped_pages = min(total_pages, effective_max_pages)
        # Extractor decision traces (counts)
        used_pypdf = 0
        used_pdfminer = 0

        # 2) Try pypdf direct extraction for all pages (bounded)
        pypdf_text: list[str | None] = [None] * capped_pages
        if pypdf_reader is not None:
            for idx in range(capped_pages):
                if self._elapsed_exceeded(start_ts, overall_timeout):
                    warnings_out.append("overall timeout reached during pypdf phase")
                    break
                try:
                    page = pypdf_reader.pages[idx]
                    # Prefer layout mode if available
                    try:
                        text = page.extract_text(
                            extraction_mode="layout",
                        )
                    except (ValueError, RuntimeError, TypeError):
                        text = page.extract_text()
                    if text:
                        pypdf_text[idx] = text
                        used_pypdf += 1
                except (ValueError, RuntimeError, TypeError) as e:
                    warnings_out.append(
                        "pypdf extract page " f"{idx+1} failed: {type(e).__name__}"
                    )

        # 3) Fill gaps with pdfminer in page chunks using iterator slicing
        text_per_page: list[str] = [""] * capped_pages
        # Copy what we have
        for i in range(capped_pages):
            if pypdf_text[i]:
                text_per_page[i] = pypdf_text[i] or ""

        remaining_indices = [i for i in range(capped_pages) if not text_per_page[i]]
        if remaining_indices:
            try:
                pdfminer_high = importlib.import_module("pdfminer.high_level")

                for chunk in self._iter_page_index_chunks(
                    remaining_indices,
                    pdfminer_chunk,
                ):
                    if self._elapsed_exceeded(start_ts, overall_timeout):
                        warnings_out.append(
                            "overall timeout reached during pdfminer phase"
                        )
                        break
                    # pdfminer expects 1-based page numbers
                    page_numbers = [i + 1 for i in chunk]
                    try:
                        mined = pdfminer_high.extract_text(
                            pdf_path,
                            page_numbers=page_numbers,
                        )
                    except TypeError:
                        # Older pdfminer may require tuple
                        mined = pdfminer_high.extract_text(
                            pdf_path,
                            page_numbers=tuple(page_numbers),
                        )
                    # Split text per page by form feed if present
                    parts = mined.split("\x0c") if mined else []
                    for local_idx, page_i in enumerate(chunk):
                        page_text = parts[local_idx] if local_idx < len(parts) else ""
                        if page_text:
                            text_per_page[page_i] = page_text
                            used_pdfminer += 1
            except (ImportError, OSError, ValueError) as e:
                warnings_out.append(f"pdfminer extract failed: {type(e).__name__}")

        # 4) OCR fallback per page in streaming batches via pdf2image
        still_missing = [
            i for i, t in enumerate(text_per_page) if not (t and t.strip())
        ]
        if still_missing:
            try:
                pdf2image = importlib.import_module("pdf2image")
                pytesseract = importlib.import_module("pytesseract")

                def ocr_image(img) -> str:
                    try:
                        # Derive per-image timeout from remaining budget
                        remaining = max(
                            0.1,
                            overall_timeout - (time.time() - start_ts),
                        )
                        try:
                            return pytesseract.image_to_string(
                                img,
                                lang=tess_lang,
                                timeout=remaining,
                            )
                        except TypeError:
                            try:
                                return pytesseract.image_to_string(
                                    img,
                                    tess_lang,
                                    timeout=remaining,
                                )
                            except TypeError:
                                try:
                                    return pytesseract.image_to_string(
                                        img,
                                        lang=tess_lang,
                                    )
                                except TypeError:
                                    try:
                                        return pytesseract.image_to_string(
                                            img,
                                            tess_lang,
                                            remaining,
                                        )
                                    except TypeError:
                                        return pytesseract.image_to_string(
                                            img,
                                            tess_lang,
                                        )
                    except (RuntimeError, ValueError):
                        # Some tesseract wrappers raise ValueError on timeouts
                        return ""
                    except OSError:
                        # Tesseract missing or not executable
                        return ""

                for page_range in self._iter_pages_for_indices(
                    still_missing,
                    ocr_batch,
                ):
                    if self._elapsed_exceeded(start_ts, overall_timeout):
                        warnings_out.append("overall timeout reached during OCR phase")
                        break
                    # Convert to 1-based; last is exclusive already
                    first = page_range.start + 1
                    last = page_range.stop
                    try:
                        try:
                            images = pdf2image.convert_from_path(
                                pdf_path,
                                dpi=target_dpi,
                                first_page=first,
                                last_page=last,
                                poppler_path=poppler_path,
                            )
                        except TypeError:
                            try:
                                images = pdf2image.convert_from_path(
                                    pdf_path,
                                    dpi=target_dpi,
                                    first_page=first,
                                    last_page=last,
                                )
                            except TypeError:
                                try:
                                    images = pdf2image.convert_from_path(
                                        pdf_path,
                                        target_dpi,
                                        first_page=first,
                                        last_page=last,
                                    )
                                except TypeError:
                                    # Some wrappers expose first/last as positional-only args.
                                    try:
                                        images = pdf2image.convert_from_path(
                                            pdf_path,
                                            target_dpi,
                                            first,
                                            last,
                                            poppler_path,
                                        )
                                    except TypeError:
                                        images = pdf2image.convert_from_path(
                                            pdf_path,
                                            target_dpi,
                                            first,
                                            last,
                                        )
                    except (OSError, ValueError, RuntimeError) as e:
                        # Handle poppler absence gracefully
                        et = type(e).__name__
                        if et in {
                            "PDFInfoNotInstalledError",
                            "PDFPageCountError",
                        }:
                            warnings_out.append(
                                "pdf2image unavailable or poppler " f"missing: {et}"
                            )
                            break
                        warnings_out.append(f"pdf2image failure: {et}")
                        break
                    except TypeError as e:
                        # Older pdf2image might not accept some kwargs
                        warnings_out.append(f"pdf2image type error: {type(e).__name__}")
                        break

                    # Map images back to page indices
                    batch_indices = list(range(first - 1, last))
                    for img, page_i in zip(images, batch_indices, strict=False):
                        if page_i < 0 or page_i >= capped_pages:
                            continue
                        if text_per_page[page_i]:
                            continue
                        text = ocr_image(img) or ""
                        if text.strip():
                            text_per_page[page_i] = text
                            ocr_pages.append(page_i + 1)
                        else:
                            warnings_out.append(
                                "OCR produced empty text on page " f"{page_i+1}"
                            )
            except (ImportError, OSError, ValueError) as e:
                warnings_out.append(f"OCR fallback not available: {type(e).__name__}")
            except subprocess.CalledProcessError as e:
                # Tesseract may bubble this up from underlying calls
                warnings_out.append(f"OCR process failed: {type(e).__name__}")

        # Final aggregation and summary
        extractor_summary = (
            f"pypdf:{used_pypdf} pdfminer:{used_pdfminer} ocr:{len(ocr_pages)}"
        )
        # Aggregate counts BEFORE truncation, then truncate for presentation
        warning_counts = self._aggregate_warnings(warnings_out)
        warnings_truncated = [self._truncate(w, 200) for w in warnings_out]
        return ExtractTextResult(
            text_per_page=text_per_page,
            warnings=warnings_truncated,
            warning_counts=warning_counts,
            used_ocr_pages=sorted(set(ocr_pages)),
            extractor_summary=extractor_summary,
        )

    def _iter_page_index_chunks(
        self, indices: Sequence[int], chunk_size: int
    ) -> Iterator[list[int]]:
        i = 0
        n = len(indices)
        while i < n:
            yield list(indices[i : i + chunk_size])
            i += chunk_size

    def _iter_pages_for_indices(
        self, indices: Sequence[int], batch: int
    ) -> Iterator[range]:
        if not indices:
            return
        # Merge contiguous indices; then chunk ranges to at most `batch` pages
        groups: list[list[int]] = []
        current: list[int] = [indices[0]]
        for i in indices[1:]:
            if i == current[-1] + 1:
                current.append(i)
            else:
                groups.append(current)
                current = [i]
        groups.append(current)

        for g in groups:
            start = g[0]
            end = g[-1]
            size = end - start + 1
            if size <= batch:
                yield range(start, end + 1)
            else:
                # split into batches
                sub_start = start
                while sub_start <= end:
                    sub_end = min(end, sub_start + batch - 1)
                    yield range(sub_start, sub_end + 1)
                    sub_start = sub_end + 1

    # ------------------------- Accuracy & Hashes -------------------------
    @staticmethod
    def compute_text_accuracy(
        original_text: str,
        translated_text: str,
        *,
        min_ratio: float = 0.4,
        max_ratio: float = 2.5,
    ) -> dict[str, float | bool]:
        """Simple length-based reasonableness check.

        Returns dict with ratio (translated/original, with 1.0 = equal length)
        and `ok` boolean if ratio within [min_ratio, max_ratio].
        """
        orig_len = max(1, len(original_text.strip()))
        trans_len = len(translated_text.strip())
        ratio = trans_len / orig_len
        ratio = float(ratio)
        ok = (ratio >= float(min_ratio)) and (ratio <= float(max_ratio))
        return {"ratio": ratio, "ok": ok}

    def compare_layout_hashes(
        self,
        original_pdf: str,
        reconstructed_pdf: str,
        *,
        page_normalize: bool = False,
        pages_a: int | None = None,
        pages_b: int | None = None,
        max_length_ratio: float | None = None,
    ) -> dict[str, float | int | str | bool | None]:
        """Length-based layout similarity with optional normalization.

        By default, the score uses raw signature lengths:
            1 - |len(a) - len(b)| / max(len(a), len(b))
        which is in [0, 1].

        Options:
        - page_normalize: when True, compare per-page average lengths
          (len/pages). Use provided pages_a/pages_b or derive from PDFs.
        - max_length_ratio: if set, clamp the larger effective length to
          at most (smaller * max_length_ratio) before computing the score.
        """

        def signature(pdf_path: str) -> str:
            # Avoid OCR here for performance; rely on direct extraction only
            text = self._extract_text_direct_only(pdf_path)
            s = " ".join(" ".join(line.split()) for line in text.splitlines())
            return s

        a_sig = signature(original_pdf)
        b_sig = signature(reconstructed_pdf)

        la = len(a_sig)
        lb = len(b_sig)

        used_pages_a = pages_a
        used_pages_b = pages_b

        if page_normalize:
            # Derive page counts if not provided
            def _count_pages(pdf_path: str) -> int:
                try:
                    pypdf = importlib.import_module("pypdf")
                    return len(pypdf.PdfReader(pdf_path).pages)
                except (ImportError, OSError, ValueError):
                    try:
                        pdfminer_pdfpage = importlib.import_module("pdfminer.pdfpage")
                        pdfminer_pdfparser = importlib.import_module(
                            "pdfminer.pdfparser"
                        )
                        pdfminer_pdfdocument = importlib.import_module(
                            "pdfminer.pdfdocument"
                        )
                        with open(pdf_path, "rb") as fh:
                            parser = pdfminer_pdfparser.PDFParser(fh)
                            doc = pdfminer_pdfdocument.PDFDocument(parser)
                            return sum(
                                1 for _ in pdfminer_pdfpage.PDFPage.create_pages(doc)
                            )
                    except (ImportError, OSError, ValueError):
                        return 0

            if used_pages_a is None:
                used_pages_a = _count_pages(original_pdf)
            if used_pages_b is None:
                used_pages_b = _count_pages(reconstructed_pdf)

            pa = max(1, int(used_pages_a or 0))
            pb = max(1, int(used_pages_b or 0))
            la_eff = la / float(pa)
            lb_eff = lb / float(pb)
        else:
            la_eff = float(la)
            lb_eff = float(lb)

        # Apply optional clamping for extreme differences
        if max_length_ratio is not None and max_length_ratio > 0:
            small = min(la_eff, lb_eff)
            large = max(la_eff, lb_eff)
            if small > 0 and large > small * max_length_ratio:
                large = small * max_length_ratio
            if la_eff >= lb_eff:
                la_eff, lb_eff = large, small
            else:
                la_eff, lb_eff = small, large

        denom = max(la_eff, lb_eff)
        score = 1.0 if denom == 0 else 1.0 - (abs(la_eff - lb_eff) / float(denom))

        # Provide hashes for traceability (not used for scoring)
        a_hash = hashlib.sha1(a_sig.encode("utf-8"), usedforsecurity=False).hexdigest()
        b_hash = hashlib.sha1(b_sig.encode("utf-8"), usedforsecurity=False).hexdigest()

        return {
            "score": float(max(0.0, min(1.0, score))),
            "a_len": la,
            "b_len": lb,
            "a_hash": a_hash,
            "b_hash": b_hash,
            "used_normalization": bool(page_normalize),
            "pages_a": used_pages_a,
            "pages_b": used_pages_b,
            "max_length_ratio": max_length_ratio,
        }

    # ---------------------------- Internals -----------------------------
    def validate_pdf_reconstruction_quality(
        self,
        original_pdf: str,
        reconstructed_pdf: str,
        *,
        min_text_length_score: float = 0.9,
        min_layout_score: float = 0.7,
        require_font_preservation: bool = False,
        min_font_match_ratio: float = 0.8,
        page_normalize_layout: bool = False,
    ) -> dict[str, float | bool | None]:
        """Basic PDF quality validation using lightweight heuristics.

        Checks:
        - Text preservation via length-based similarity on extracted text
        - Layout preservation via length similarity (optionally per-page)
        - Font preservation via overlap of font names if available
        """
        warnings: list[str] = []

        # Text preservation: compare normalized extracted texts
        try:
            a_text = self._extract_text_direct_only(original_pdf)
            b_text = self._extract_text_direct_only(reconstructed_pdf)
        except (OSError, ValueError):
            a_text = ""
            b_text = ""
            warnings.append("text extraction failed for one or both PDFs")

        a_text_norm = " ".join(" ".join(line.split()) for line in a_text.splitlines())
        b_text_norm = " ".join(" ".join(line.split()) for line in b_text.splitlines())
        la = len(a_text_norm)
        lb = len(b_text_norm)
        denom = max(la, lb)
        text_length_score = 1.0 if denom == 0 else 1.0 - (abs(la - lb) / float(denom))
        text_ok = text_length_score >= float(min_text_length_score)

        # Layout preservation: reuse compare_layout_hashes (length-based)
        layout_report = self.compare_layout_hashes(
            original_pdf,
            reconstructed_pdf,
            page_normalize=page_normalize_layout,
        )
        layout_score = cast(float, layout_report["score"])  # in [0, 1]
        layout_ok = layout_score >= float(min_layout_score)

        # Font preservation: attempt to collect font names from both PDFs
        fonts_a = self._collect_fonts(original_pdf)
        fonts_b = self._collect_fonts(reconstructed_pdf)

        if fonts_a or fonts_b:
            union = fonts_a.union(fonts_b)
            inter = fonts_a.intersection(fonts_b)
            font_overlap_ratio: float | None = (
                (len(inter) / float(len(union))) if union else None
            )
        else:
            font_overlap_ratio = None

        if font_overlap_ratio is None:
            font_ok = not require_font_preservation
            if require_font_preservation:
                warnings.append("font preservation check skipped (unavailable)")
        else:
            font_ok = font_overlap_ratio >= float(min_font_match_ratio)

        passed = text_ok and layout_ok and font_ok

        return {
            "passed": passed,
            "text_length_score": float(text_length_score),
            "text_ok": bool(text_ok),
            "layout_score": float(layout_score),
            "layout_ok": bool(layout_ok),
            "font_overlap_ratio": (
                None if font_overlap_ratio is None else float(font_overlap_ratio)
            ),
            "font_ok": bool(font_ok),
            "used_page_normalization": bool(page_normalize_layout),
            "warnings": warnings,
        }

    def _collect_fonts(self, pdf_path: str) -> set[str]:
        """Extract font names from a PDF using pypdf.

        Returns a set of distinct font names found in the first 50 pages.
        Returns empty set on import/read errors.
        """
        try:
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(pdf_path)
            names: set[str] = set()
            for page in list(reader.pages)[:50]:
                try:
                    resources = None
                    if hasattr(page, "get"):
                        resources = page.get("/Resources") or page.get("Resources")
                    if resources is None:
                        resources = getattr(page, "resources", None)
                    fonts_dict = None
                    if resources is not None and hasattr(resources, "get"):
                        fonts_dict = resources.get("/Font") or resources.get("Font")
                    if fonts_dict is None:
                        fonts_dict = getattr(page, "fonts", None)
                    if isinstance(fonts_dict, dict):
                        for key, font_obj in fonts_dict.items():
                            name = None
                            try:
                                if hasattr(font_obj, "get"):
                                    name = font_obj.get("/BaseFont") or font_obj.get(
                                        "BaseFont"
                                    )
                            except (ValueError, RuntimeError, TypeError):
                                name = None
                            if not name:
                                name = str(key)
                            if isinstance(name, bytes):
                                try:
                                    name = name.decode("latin1", "ignore")
                                except (ValueError, RuntimeError, TypeError):
                                    name = None
                            if isinstance(name, str):
                                names.add(name.strip("/"))
                except (ValueError, RuntimeError, TypeError, OSError):
                    continue
            return names
        except (ImportError, OSError, ValueError):
            return set()

    def _extract_text_direct_only(self, pdf_path: str) -> str:
        """Fast direct extraction helper used by compare_layout_hashes.

        Attempts pypdf first, then pdfminer for remaining gaps. Avoids OCR.
        """
        text = ""
        page_texts: list[str] = []
        total_pages = 0
        pypdf_reader = None
        try:
            pypdf = importlib.import_module("pypdf")
            pypdf_reader = pypdf.PdfReader(pdf_path)
            total_pages = len(pypdf_reader.pages)
            for i in range(total_pages):
                try:
                    page = pypdf_reader.pages[i]
                    try:
                        t = page.extract_text(
                            extraction_mode="layout",
                        )
                    except (ValueError, RuntimeError, TypeError):
                        t = page.extract_text()
                    page_texts.append(t or "")
                except (ValueError, RuntimeError, TypeError):
                    page_texts.append("")
        except (ImportError, OSError, ValueError):
            pass

        remaining = [i for i, t in enumerate(page_texts) if not t]
        if remaining:
            try:
                pdfminer_high = importlib.import_module("pdfminer.high_level")
                page_numbers = [i + 1 for i in remaining]
                try:
                    mined = pdfminer_high.extract_text(
                        pdf_path, page_numbers=page_numbers
                    )
                except TypeError:
                    mined = pdfminer_high.extract_text(
                        pdf_path, page_numbers=tuple(page_numbers)
                    )
                parts = mined.split("\x0c") if mined else []
                for local_idx, page_i in enumerate(remaining):
                    page_texts[page_i] = (
                        parts[local_idx] if local_idx < len(parts) else ""
                    )
            except (ImportError, OSError, ValueError):
                pass

        if page_texts:
            text = "\n".join(page_texts)
        return text
