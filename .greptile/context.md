# Greptile Architectural Context: PhenomenalLayout

## 1. Domain Background
PhenomenalLayout translates full-length philosophical treatises (e.g. Ludwig Klages, Kant, Heidegger) from German to English. Because German compound terms expand by 20–30% in English, traditional PDF translation breaks document layouts, tables, and embedded diagrams.

## 2. Technical Stack & Deployment
* **Deployment & Hosting**: Serverless on **Modal Labs** (`modal>=0.60.0`, `modal_app.py`) with automatic scale-to-zero when idle, operating within Modal's $30/mo free compute tier.
* **Persistent Storage**: Modal Volume (`modal.Volume.from_name("phenomenal-user-data")`) mounted at `/data` for user profiles and neologism dictionaries.
* **Language & Runtime**: Python 3.11 / 3.12, FastAPI, Gradio UI.
* **Translation & Document Engine**: Google Cloud Translation API v3 (`google-cloud-translate>=3.15.0`).
  - `batchTranslateDocument`: Primary default asynchronous pipeline using Google Cloud Storage (`google-cloud-storage>=2.14.0`).
  - `translateDocument`: Secondary synchronous pipeline for rapid 1–3 page sample previews.
  - Native features enabled: `enableShadowRemovalNativePdf=True`, `enableRotationCorrection=True`.
* **Architecture Model**: **Bring Your Own Key (BYOK)** where users supply their own GCP Project ID, GCS Bucket, and Service Account key. Host pays zero translation and zero GCS storage costs.
* **Pre-Auth Cost Quote**: Zero-credential estimation endpoint on Modal CPU (`services/cost_estimator.py`) providing an itemized quote within a $\pm \$5.00$ margin of error before login.
* **Linguistics & Neologism Engine**:
  - `services/neologism_detector.py`: German compound detection and morphological parsing (spaCy `de_core_news_sm`).
  - `services/philosophical_context_analyzer.py`: Philosophical density calculation.
  - `services/user_vocabulary_store.py`: User-tied terminology memory stored on Modal Volume.
  - `services/byok_credentials_manager.py`: In-memory credential vault and onboarding walkthrough data.
  - `services/glossary_sync_manager.py`: Compiles and synchronizes Dual-Tier TSV Glossaries with GCP Cloud Translation in `us-central1`.

## 3. Specifications & Reference Docs
* [System Design Spec](spec/gcp-migration/design.md)
* [Requirements Spec](spec/gcp-migration/requirements.md)
* [Implementation Tasks Spec](spec/gcp-migration/tasks.md)
* [ADR 0001: Migration to Google Cloud Document Translation](docs/adr/0001-migrate-to-google-cloud-document-translation.md)
