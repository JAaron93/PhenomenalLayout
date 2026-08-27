# Fallback Plaintext Translation Architecture & Limitations

## 1. Architectural Purpose & Scope

PhenomenalLayout is a domain-specific book translation engine designed for German philosophical literature. In production, document translation follows a dual-tier model:

1. **Primary Default (Google Cloud Document Translation Advanced v3)**:
   - Natively translates 98%+ of full-length book pages (50–1,000+ pages) with pixel-perfect preservation of original typography, multi-column tables, diagrams, and footnotes.
2. **Secondary Fallback Engine (`FallbackPageTranslator`, TASK-3.3, FR-13)**:
   - Activated automatically or via 1-click retry when complex graphical elements or malformed vector geometry cause Google Cloud Document Translation to report layout failures (`metadata.failed_pages > 0`).
   - Extracts unformatted raw text from failed page indices, translates the text via Cloud Translation Text v3 with the regional session glossary, and synthesizes a clean fallback PDF page.
   - Slices and splices the translated pages back into the layout-preserved PDF to guarantee a **98% layout-preserved, 100% translated book**.

---

## 2. Invariants & Design Principles

* **Strict 1-to-1 Page Alignment**: Each failed source page is replaced by exactly one synthesized fallback page. This preserves exact physical page numbering and enables synchronized side-by-side reading in `DualPaneViewerController` without desynchronization.
* **No Heuristic Canvas Reconstruction**: In accordance with the repository constitution (`AGENTS.md §4`), fragile heuristic box-expansion and canvas-drawing algorithms (e.g. legacy ReportLab canvas reconstruction) are strictly prohibited. The fallback engine focuses solely on clear, legible, and unclipped plaintext presentation.
* **100% Translation Fidelity (Zero Transliteration)**: Translated text must never be altered, transliterated (e.g. converting Cyrillic `бытие` to `bytie`), or replaced with placeholder tokens (e.g. `[CJK UNIFIED IDEOGRAPH]`). All Unicode code points are preserved verbatim.

---

## 3. Typography & Glyph Mapping Architecture

The fallback renderer generates PDF pages directly via low-level `pypdf` content streams and composite Type 0 fonts (`/CIDFontType2`):

```
+-------------------------------------------------------------------------+
| Fallback Page Content Stream (BT /F1 ... <cids> Tj ... ET)              |
+------------------------------------+------------------------------------+
                                     |
                                     v
                  +---------------------------------------+
                  | /Type0 Composite Font (/F1)           |
                  |  - /Encoding /Identity-H              |
                  |  - /ToUnicode (Custom CMap)           |
                  +-------------------+-------------------+
                                      |
                                      v
                  +---------------------------------------+
                  | /CIDFontType2 Descendant Font         |
                  |  - /CIDToGIDMap (Dynamic Stream)      |
                  |  - /W (Advance Widths Array)          |
                  |  - /FontDescriptor                    |
                  |      - /FontFile2 (Embedded TTF)      |
                  +-------------------+-------------------+
```

### Dynamic 16-Bit Sequential CID Allocation
Rather than writing raw UTF-16 code units directly into the PDF content stream—which causes surrogate pairs for supplementary Unicode characters above `U+FFFF` (such as mathematical Fraktur letters like 𝔄 `U+1D504`) to be split into two separate CIDs—the engine dynamically allocates sequential 16-bit Character Identifiers ($1 \dots N$) for all unique characters on the page:
1. **Dynamic CID Assignment**: Unique characters $C = [c_1, c_2, \dots, c_N]$ are assigned CIDs $1 \dots N$.
2. **`/ToUnicode` CMap**: Maps each 16-bit dynamic CID directly to its Unicode code point. BMP characters ($\le \text{U+FFFF}$) map to 4-digit hex; supplementary characters ($> \text{U+FFFF}$) map to UTF-16 surrogate pairs in big-endian hex.
3. **`/CIDToGIDMap` Stream**: A pure-Python TrueType parser extracts both format 4 (BMP) and format 12 (supplementary 32-bit) `cmap` subtables from the embedded font program, mapping each dynamic CID directly to its actual TrueType Glyph ID (GID).
4. **`/W` Width Array**: Glyph advance widths from the TrueType `hhea` and `hmtx` tables are normalized to 1000 units and emitted into `/W`.

---

## 4. Known Operational Limitations

| Limitation Area | Behavior & Impact | Operational Workaround / Recommendation |
| :--- | :--- | :--- |
| **Vector Diagrams & Images** | Graphical figures, illustrations, charts, and drawings on the failed page are not reproduced. Only extracted textual captions and paragraphs are rendered. | Scholars can view the original German diagram side-by-side using the `DualPaneViewerController`. |
| **Complex Table Formatting** | Multi-tier or nested tabular data is extracted as sequential line items and wrapped to column widths rather than rendered as tabular grid cells. | Sufficient for reading textual content; complex numerical tables should be cross-referenced against the original German page. |
| **Font Glyph Coverage** | The embedded font program provides standard coverage (Latin, Greek, Cyrillic, Hebrew, Arabic, common math symbols). If a translated page contains extremely rare glyphs (e.g. archaic hieroglyphs or unmapped CJK ideographs) missing from the host font, the PDF viewer renders the font's `.notdef` box (`▯`). | Text extraction via copy-paste or screen readers preserves 100% of the Unicode code points via `/ToUnicode`. Users can install comprehensive system fonts (e.g. Arial Unicode) in standard font paths. |
| **Bidirectional Text Mixing** | Embedded RTL phrases (Hebrew or Arabic philosophical citations) are segmented into directional runs. While character sequences are preserved, complex bidirectional layout shaping (e.g. contextual ligatures) depends on the PDF viewer's font rendering engine. | Retains text fidelity and prevents `pypdf` text-extraction flushing errors. |
| **Dynamic Page Height** | For extreme text overflow (> 200 lines), page height expands dynamically beyond standard letter height to guarantee leading $\ge 11.0\text{pt}$ and font size $\ge 8.5\text{pt}$, preventing line overlap or text clipping. | Fallback pages remain legible, though their physical page dimensions may exceed standard $8.5 \times 11\text{ inch}$ bounds. |
