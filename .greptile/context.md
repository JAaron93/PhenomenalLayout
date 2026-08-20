# Greptile Architectural Context: PhenomenalLayout

## 1. Domain Background
PhenomenalLayout translates full-length philosophical treatises (e.g. Ludwig Klages, Kant, Heidegger) from German to English. Because German compound terms expand by 20–30% in English, traditional PDF translation breaks document layouts, tables, and embedded diagrams.

## 2. Technical Stack
* **Language & Runtime**: Python 3.11 / 3.12, FastAPI, Gradio UI.
* **Translation & Document Engine**: Google Cloud Translation API v3 (`google-cloud-translate>=3.15.0`).
  - `batchTranslateDocument`: Primary default asynchronous pipeline using Google Cloud Storage (`google-cloud-storage>=2.14.0`).
  - `translateDocument`: Secondary synchronous pipeline for rapid 1–3 page sample previews.
  - Native features enabled: `enableShadowRemovalNativePdf=True`, `enableRotationCorrection=True`.
* **Linguistics & Neologism Engine**:
  - `services/neologism_detector.py`: German compound detection and morphological parsing (spaCy `de_core_news_sm`).
  - `services/philosophical_context_analyzer.py`: Philosophical density calculation.
  - `core/dynamic_choice_engine.py`: User disambiguation and translation preference state.
  - `services/glossary_sync_manager.py`: Compiles and synchronizes Dual-Tier TSV Glossaries with GCP Cloud Translation in `us-central1`.

## 3. Specifications & Reference Docs
* [System Design Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/design.md)
* [Requirements Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/requirements.md)
* [Implementation Tasks Spec](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/tasks.md)
* [ADR 0001: Migration to Google Cloud Document Translation](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/docs/adr/0001-migrate-to-google-cloud-document-translation.md)
