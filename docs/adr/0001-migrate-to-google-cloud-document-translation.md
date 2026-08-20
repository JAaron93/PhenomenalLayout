# ADR 0001: Migrate to Google Cloud Document Translation API & Consolidate around Book-Scale Neologism Orchestration

## Status
**Accepted**

## Date
2026-08-19

## Context & Problem Statement

PhenomenalLayout is designed specifically for **full-length books and philosophical treatises** (e.g., Ludwig Klages' *Der Geist als Widersacher der Seele*, Kant, Heidegger), ranging from 50 to over 1,000 pages with complex layouts, multi-column tables, diagrams, and dense terminology.

Translating books from German to English introduces continuous character expansion (20–30%), which broke bounding boxes in earlier versions of PhenomenalLayout. The project attempted to solve this via a complex, heuristic-heavy stack:
1. High-resolution rendering at 300 DPI via `pdf2image`.
2. Dolphin OCR running on dedicated Modal GPU workers.
3. Plain-text batch translation via external APIs.
4. Dynamic text-fitting algorithms (font scaling `0.6x–1.2x`, line wrapping penalties, bounding box expansion).
5. Canvas-level ReportLab reconstruction.

### The Pain Points in Book Processing
* **Formatting Drift & Broken Layouts**: Heuristic scaling corrupted multi-page tables, headers, footers, and diagrams.
* **Shadow Text & Memory Exhaustion**: Rendering and manipulating hundreds of 300 DPI bitmaps caused memory exhaustion and shadow text overlays.
* **Operational Overhead**: Maintaining Modal GPU workers for OCR on 500+ page books was slow, expensive, and fragile.
* **Terminology Inconsistency**: Machine translation without centralized glossary enforcement translated recurring core philosophical concepts (e.g. *Geist*, *Seele*, *Biozentrik*, *Wirklichkeit*) inconsistently across different chapters of the same book.

---

## Decision

We will adopt **Google Cloud Document Translation API (Cloud Translation - Advanced v3)** with **Asynchronous GCS Batch Translation (`batchTranslateDocument`) as the primary default pipeline**, combined with a **Dual-Tier Glossary Synchronization Subsystem** and PhenomenalLayout's **German Philosophical Neologism Detection Engine**.

### Architectural Tenets
1. **Default to Asynchronous Batch Document Translation via GCS (`batchTranslateDocument`)**:
   * All book translation requests default to staging the PDF in Google Cloud Storage (`gs://<bucket>/inputs/<book_id>/source.pdf`).
   * Dispatches asynchronous `batchTranslateDocument` with regional output destinations (`gs://<bucket>/outputs/<book_id>/`).
   * Long-Running Operations (LRO) are polled asynchronously, reporting live page-by-page progress to the UI.
   * Google Cloud natively preserves multi-column book layouts, footnotes, typography, tables, and images while removing shadow text.
2. **Dual-Tier Glossary Synchronization**:
   * **Tier 1 (Persistent Base Glossary)**: Static philosophical foundation dictionaries ([`config/klages_terminology.json`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/config/klages_terminology.json)) registered as persistent Cloud Translation Glossaries in `us-central1`.
   * **Tier 2 (Dynamic Book Session Glossary)**: Dynamic user choices and novel coined compounds compiled into RFC 4180 TSVs, staged in GCS, and registered with Cloud Translation before the batch job starts.
3. **Retain and Elevate the Neologism & Terminology Subsystem**:
   * Pre-scan book text streams using lightweight streaming parsing.
   * Run [`NeologismDetector`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/neologism_detector.py) and [`PhilosophicalContextAnalyzer`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/philosophical_context_analyzer.py) to aggregate coined terms and present them in a pre-translation review UI.
4. **Retire Redundant Code**:
   * Deprecate and delete `services/pdf_document_reconstructor.py`, `core/dynamic_layout_engine.py`, `core/dynamic_programming.py`, `services/dolphin_client.py`, and `services/dolphin_modal_service.py`.

---

## Consequences

### Positive Consequences
* **Seamless Book-Scale Processing**: Easily translates 500+ page books with zero timeout failures or memory exhaustion.
* **Flawless Formatting & Typography**: Preserves intricate multi-column layouts, tables, footnotes, and embedded diagrams natively.
* **Strict Terminology Consistency**: The dual-tier glossary sync guarantees that every philosophical term is translated identically from chapter 1 to the index.
* **Infrastructure Elimination**: No need to maintain or scale custom Modal GPU OCR instances.

### Negative Consequences & Trade-offs
* **GCP & GCS Requirement**: Requires a Google Cloud Project with Cloud Translation API enabled, GCS bucket access, and ADC credentials.
* **Batch Latency**: Asynchronous batch translation involves GCS upload, queueing, and polling, which is ideal for books but incurs a brief queue overhead (sample single pages can still use synchronous preview).

---

## References
* [System Design Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/gcp-migration/design.md)
* [Requirements & BDD Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/gcp-migration/requirements.md)
* [Tasks Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/gcp-migration/tasks.md)
* [Google Cloud Translation Document Translation API](https://cloud.google.com/translate/docs/advanced/translate-documents)
