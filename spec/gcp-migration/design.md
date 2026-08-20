# System Design: Google Cloud Document Translation & Neologism Orchestration Engine

## 1. Executive Summary & Book-Scale Vision

**PhenomenalLayout** is engineered specifically for **full-length books and long-form philosophical treatises** (e.g., Ludwig Klages' *Der Geist als Widersacher der Seele*, Kantian critiques, Heideggerian texts).

Because books range from 50 to 1,000+ pages with complex multi-column layouts, footnotes, diagrams, and dense terminology, PhenomenalLayout establishes **Asynchronous Google Cloud Document Batch Translation (`batchTranslateDocument`) using Google Cloud Storage (GCS) buckets as the primary/default translation pipeline**.

PhenomenalLayout is deployed as a **serverless cloud application on Modal Labs** under a **Bring Your Own Key (BYOK)** model. Users provide their own Google Cloud credentials and project billing, while Modal Labs orchestrates the web interface, text streaming, German morphological analysis, dynamic glossary compilation, and persistent user-level neologism preferences.

---

## 2. Compute Topology & Division of Labor (Modal Labs vs. User GCP Project)

To maximize efficiency and operate within Modal Labs' free compute tier ($30/month) while maintaining zero cloud translation costs for the host, the compute topology is divided into two distinct zones:

```mermaid
flowchart TB
    subgraph Modal_Zone["Modal Labs Serverless Cloud (Host: Near-Zero Compute / Auto-Scale to 0)"]
        UI["Web UI & Fast API Endpoint (Gradio / FastAPI)"]
        AUTH["BYOK Credentials Manager (Session-Scoped Vault)"]
        NEO["Neologism & Morphological Detector (spaCy de_core_news_sm)"]
        VOCAB[("User Vocabulary Store on Modal Volume /data/users/")]
        GLOSS_COMP["Dual-Tier TSV Glossary Compiler"]
        LRO_MON["Async LRO Poller & Progress Monitor"]
    end

    subgraph GCP_Zone["User's GCP Cloud Project (BYOK Billed to User's Account)"]
        GCS_BUCKET[("User's GCS Bucket: gs://user-bucket/")]
        GCP_GLOSS["Cloud Translation v3 Regional Glossaries (us-central1)"]
        GCP_BATCH["Cloud Document Translation API (batchTranslateDocument)"]
        GCP_OCR["Google Cloud Native OCR & Layout Preservation Engine"]
    end

    UI --> AUTH
    AUTH -->|Validate Credentials| GCP_BATCH
    UI --> NEO
    NEO <--> VOCAB
    NEO --> GLOSS_COMP
    VOCAB --> GLOSS_COMP
    AUTH -->|Upload TSV & Book PDF| GCS_BUCKET
    GLOSS_COMP -->|Register Glossary| GCP_GLOSS
    GCS_BUCKET -->|Input PDF| GCP_BATCH
    GCP_GLOSS -->|Apply Glossary| GCP_BATCH
    GCP_BATCH --> GCP_OCR
    GCP_BATCH -->|LRO State| LRO_MON
    GCP_OCR -->|Output PDF| GCS_BUCKET
    LRO_MON --> UI
    GCS_BUCKET -->|Download Translated Book| UI
```

### 2.1 Workload & Cost Allocation Matrix

| Workload Component | Host Layer | Resource Profile | Cost & Scaling Model |
| :--- | :--- | :--- | :--- |
| **Web Interface & API** | Modal Labs Web Endpoint | Lightweight Python FastAPI / Gradio | Auto-scales down to 0 when idle. Consumes < $2–$5/mo of Modal's $30 free compute tier. |
| **Neologism Pre-Scanning & Parsing** | Modal CPU Worker | Python streaming chunk reader + spaCy NLP | ~2–5 seconds CPU burst per chapter. Highly optimized memory footprint (< 256MB RAM). |
| **User Account & Vocabulary Store** | Modal Persistent Volume (`modal.Volume`) | SQLite / JSON store on `/data/user_profiles/` | Persistent storage across user sessions. Zero recurring compute cost when idle. |
| **Dual-Tier TSV Compilation** | Modal CPU Worker | In-memory RFC 4180 TSV generation | Instantaneous (< 100ms). |
| **Book & Glossary Storage** | User's GCS Bucket (`gs://<user_bucket>/`) | Google Cloud Storage Standard / Nearline | Billed directly to User's GCP account (~$0.02/GB/mo). Host incurs zero storage/egress fees. |
| **Document Translation & Layout Reconstruction** | User's GCP Cloud Translation API v3 | Google Cloud Tensor & Document Processing | Billed directly to User's GCP billing account ($0.08/page). Host incurs zero translation costs. |
| **LRO Progress Monitoring** | Modal Async Worker | Lightweight async polling loop (every 10s) | Near-zero CPU overhead while waiting for GCP LRO completion. |

---

## 3. Bring Your Own Key (BYOK) Architecture & Security Model

PhenomenalLayout provides a dedicated **BYOK Setup & Credentials Vault**:

1. **Credential Ingestion**:
   * Users supply their **Google Cloud Project ID**, **Target GCS Bucket Name**, and **GCP Service Account Key (JSON)** or temporary OAuth access token.
   * Service Account must have permissions: `roles/cloudtranslate.editor` and `roles/storage.objectAdmin` on the target bucket.
2. **Session-Scoped Isolation**:
   * Credentials are held strictly in memory for the active browser session (or encrypted at rest on client-side encrypted tokens).
   * Credentials are never logged, never exposed to other users, and never persisted to public storage.
3. **Instant Validation**:
   * Upon entry, the system tests connectivity by issuing a zero-cost GCP call (`projects.locations.glossaries.list`) to verify permissions and regional endpoint availability (`us-central1`).

---

## 4. User-Tied Neologism Memory & Vocabulary Persistence

Philosophical translators build specific terminology preferences over time. PhenomenalLayout introduces the **Persistent User Vocabulary Engine**:

1. **User Identity & Storage**:
   * Managed on a persistent Modal Volume: `modal.Volume.from_name("phenomenal-user-data", create_if_missing=True)`.
   * Stored under `/data/user_vocabularies/{user_id}.sqlite` or `.json`.
2. **Translation Choice Memory**:
   * Whenever a user selects a translation (e.g. `Geist` $\rightarrow$ `Spirit`, `Wirklichkeit` $\rightarrow$ `Actuality`, or `Schauung` $\rightarrow$ `[Preserve Untranslated: Schauung]`), the preference is saved to their persistent profile.
3. **Smart Auto-Populate for New Books**:
   * When the user uploads a subsequent book, the Neologism Pre-Scanner checks the user's saved vocabulary first.
   * Saved terms are automatically pre-selected in the terminology review table with high confidence, drastically reducing repetitive translator input across a multi-volume treatise.

---

## 5. Component Architecture & System Boundaries

```mermaid
classDiagram
    class BYOKCredentialsManager {
        +set_credentials(user_id, project_id, gcs_bucket, sa_json) bool
        +get_client(user_id) TranslationServiceClient
        +get_storage_client(user_id) StorageClient
        +validate_gcp_access(user_id) ValidationResult
        +clear_session(user_id) void
    }

    class UserVocabularyStore {
        +get_user_preferences(user_id) dict
        +save_preference(user_id, term, translation, note) void
        +bulk_save_preferences(user_id, preferences_dict) void
        +export_user_dictionary(user_id) bytes
    }

    class GCPBatchTranslationService {
        +submit_batch_job(gcs_input_uri, gcs_output_uri, source_lang, target_lang, glossary_resource_name, credentials) str
        +poll_operation(operation_name, credentials) LROStatus
        +download_translated_book(gcs_output_uri, local_dest_path, credentials) Path
    }

    class GlossarySyncManager {
        +sync_base_glossary(glossary_name, terms_dict, credentials) str
        +sync_book_session_glossary(session_id, user_choices, base_glossary_name, credentials) str
        +compile_tsv(base_terms, user_terms, book_terms) bytes
        +upload_glossary_to_gcs(tsv_bytes, gcs_path, credentials) str
        +ensure_glossary_ready(glossary_resource_name, credentials) bool
        +delete_session_glossary(glossary_resource_name, credentials) bool
    }

    class NeologismDetector {
        +analyze_book_stream(pdf_path, chunk_size, user_saved_vocab) NeologismAnalysis
        +extract_candidates(text) list
        +analyze_morphology(term) MorphologicalAnalysis
        +analyze_philosophical_context(term, text) PhilosophicalContext
    }

    class BookTranslationOrchestrator {
        +pre_scan_book(user_id, book_pdf_path) BookScanResult
        +start_book_translation(user_id, book_id, session_id) JobHandle
        +get_job_progress(job_handle) JobProgress
    }

    BookTranslationOrchestrator --> BYOKCredentialsManager
    BookTranslationOrchestrator --> UserVocabularyStore
    BookTranslationOrchestrator --> NeologismDetector
    BookTranslationOrchestrator --> GlossarySyncManager
    BookTranslationOrchestrator --> GCPBatchTranslationService
    GlossarySyncManager --> GCPBatchTranslationService
```

---

## 6. Subsystem Deep-Dive

### 6.1 Subsystem 1: Book-Scale Text Ingestion & Neologism Pre-Scanning
* **Stream-Based Chunking**: Full books (100–1,000 pages) are processed in streaming chunks via `pypdf` without loading entire uncompressed page bitmaps into memory.
* **Linguistic Analysis**:
  * [`NeologismDetector`](services/neologism_detector.py) identifies German compounds, prefixes, and suffixes.
  * [`PhilosophicalContextAnalyzer`](services/philosophical_context_analyzer.py) scores term frequency, chapter distribution, and philosophical relevance.
  * Pre-populates suggestions using:
    1. User's saved preferences from `UserVocabularyStore`.
    2. Built-in domain foundation dictionary ([`config/klages_terminology.json`](config/klages_terminology.json)).
    3. Morphological root decomposition for novel coined compounds.

---

### 6.2 Subsystem 2: Dual-Tier Glossary Synchronization & Lifecycle Management
Translating books requires strict terminology consistency across thousands of paragraphs. The **Glossary Sync Manager** operates two tiers:

1. **Tier 1: Persistent Domain Glossaries (Base Tier)**
   * Static foundation dictionaries (e.g. `klages-philosophical-base-v1`) provisioned once in Google Cloud Translation in user's project (`projects/<user_proj>/locations/us-central1/glossaries/klages-philosophical-base-v1`).
   * Reused across all translations of related treatises to avoid redundant GCS uploads.

2. **Tier 2: Dynamic Book Session Glossaries (Overlay Tier)**
   * Merges Tier 1 + User Saved Vocabulary + Book-Specific Choices.
   * Compiles the mapping into a RFC 4180-compliant TSV (`source_code\ttarget_code`).
   * Stages the file in user's GCS: `gs://<user_bucket>/glossaries/sessions/<book_id>_<timestamp>.tsv`.
   * Invokes Cloud Translation v3 `create_glossary` in `us-central1` and polls until status is active.
   * Automatic TTL/cleanup policies prune transient session glossaries after job completion.

---

### 6.3 Subsystem 3: Primary Default Pipeline - Asynchronous GCS Batch Translation
Because books exceed inline API payload and timeout limits, **Asynchronous Batch Translation (`batchTranslateDocument`) is the primary, default execution engine**:

1. **Book Upload to User GCS**:
   * The source book PDF is streamed to `gs://<user_bucket>/inputs/<book_id>/source.pdf`.
2. **Batch Request Dispatch**:
   * Constructs `BatchTranslateDocumentRequest`:
     * `parent = f"projects/{user_project_id}/locations/{location}"`
     * `source_language_code = "de"`
     * `target_language_codes = ["en"]`
     * `input_configs = [{"gcs_source": {"input_uri": "gs://<user_bucket>/inputs/<book_id>/source.pdf"}, "mime_type": "application/pdf"}]`
     * `output_config = {"gcs_destination": {"output_uri_prefix": "gs://<user_bucket>/outputs/<book_id>/"}}`
     * `glossaries = {"en": {"glossary": glossary_resource_name}}`
   * Dispatches asynchronous request via `TranslationServiceClient.batch_translate_document`.
3. **Long-Running Operation (LRO) Monitoring**:
   * Tracks operation progress metadata via `BatchTranslateDocumentMetadata` (`metadata.state == SUCCEEDED`, `metadata.translated_pages / metadata.total_pages`, `metadata.failed_pages`).
   * Emits progress events to the Gradio/FastAPI interface for live chapter/page tracking.
4. **Automated Fetch & Validation**:
   * Once LRO transitions to `SUCCEEDED` (or `done == True`), downloads the translated PDF from `gs://<user_bucket>/outputs/<book_id>/` to local cache.
   * Runs validation check ensuring page count matches and PDF structure is intact.

*(Note: Synchronous `translateDocument` is retained purely as an optional rapid preview tool for single sample pages).*

---

## 7. Sequence Diagram: Modal BYOK Book Translation Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Translator as User / Translator
    participant UI as Modal Web App (Gradio / FastAPI)
    participant BYOK as BYOKCredentialsManager
    participant Vocab as UserVocabularyStore (Modal Volume)
    participant Orch as BookTranslationOrchestrator
    participant Neologism as NeologismDetector
    participant GlossarySync as GlossarySyncManager
    participant UserGCS as User GCS Bucket
    participant UserGCP as User Cloud Translation API v3

    Translator->>UI: Input GCP Project ID, GCS Bucket & Upload SA Key JSON
    UI->>BYOK: Set & Validate Credentials
    BYOK->>UserGCP: Test Connection (List Glossaries)
    UserGCP-->>BYOK: Access Confirmed (200 OK)
    BYOK-->>UI: BYOK Connected Ready

    Translator->>UI: Upload Book PDF (e.g. 350-page Klages Treatise)
    UI->>Vocab: Load User's Saved Terminology Preferences
    Vocab-->>Orch: Return User Neologism Dictionary
    UI->>Orch: Submit Book for Pre-Scan
    Orch->>Neologism: Scan Text Stream & Match Compounds + Saved Prefs
    Neologism-->>Orch: Return Analysis with Auto-Filled User Choices
    Orch-->>UI: Display Interactive Terminology Review Table
    
    Translator->>UI: Confirm Choices & Modify New Novel Terms
    UI->>Vocab: Persist Updated Terminology Choices to User Profile
    UI->>Orch: Start Book Translation Job
    
    rect rgb(240, 248, 255)
    Note over Orch,UserGCP: Dual-Tier Glossary Synchronization
    Orch->>GlossarySync: Build Composite Glossary (Klages Base + User Profile + Book Choices)
    GlossarySync->>UserGCS: Upload TSV to gs://user-bucket/glossaries/book_101.tsv
    GlossarySync->>UserGCP: create_glossary(name="book_101_glossary", gcs_uri)
    UserGCP-->>GlossarySync: LRO Complete -> Glossary Ready
    end

    rect rgb(255, 250, 240)
    Note over Orch,UserGCP: Primary Asynchronous Batch Translation
    Orch->>UserGCS: Upload Book to gs://user-bucket/inputs/book_101/source.pdf
    Orch->>UserGCP: batchTranslateDocument(inputs, output_prefix, glossary="book_101_glossary")
    UserGCP-->>Orch: Return Long Running Operation (LRO)
    
    loop Every 10s until Complete
        Orch->>UserGCP: get_operation(LRO)
        UserGCP-->>Orch: Operation Metadata (translated_pages / total_pages)
        Orch-->>UI: Update Live Progress Bar (e.g. 142/350 Pages)
    end
    
    UserGCP-->>Orch: LRO State = SUCCEEDED
    Orch->>UserGCS: Download Translated PDF from gs://user-bucket/outputs/book_101/
    end

    Orch-->>UI: Notify Completion & Provide Download Link
    UI-->>Translator: Render Preview & Download Pixel-Perfect Translated Book PDF
```

---

## 8. Modal Labs Serverless Deployment Architecture

```python
# modal_app.py architecture outline
import modal

app = modal.App("phenomenallayout")
volume = modal.Volume.from_name("phenomenal-user-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi",
        "uvicorn",
        "gradio",
        "pypdf>=6.14.0",
        "google-cloud-translate>=3.15.0",
        "google-cloud-storage>=2.14.0",
        "spacy>=3.7.0",
        "pydantic>=2.10.0",
    )
    .run_commands("python -m spacy download de_core_news_sm")
)

@app.function(
    image=image,
    volumes={"/data": volume},
    timeout=3600,
    scaledown_window=300,
)
@modal.asgi_app()
def web_entrypoint():
    from app import create_app
    return create_app()
```

---

## 9. Configuration & Environment Variables

| Variable | Description | Source / Scope |
| :--- | :--- | :--- |
| `MODAL_VOLUME_PATH` | Path for persistent user profiles and vocabularies | Modal Container (`/data`) |
| `GCP_LOCATION` | Regional endpoint for Translation & Glossaries | User Config (`us-central1`) |
| `BATCH_POLL_INTERVAL_SEC`| Interval in seconds for checking batch LRO status | System Default (`10s`) |
| `MAX_INLINE_PREVIEW_PAGES`| Max pages allowed for synchronous sample previews | System Default (`3`) |
| `USER_BYOK_PROJECT_ID` | Google Cloud Project ID | User BYOK Input |
| `USER_BYOK_BUCKET` | Google Cloud Storage Bucket Name | User BYOK Input |
| `USER_BYOK_CREDENTIALS` | Google Service Account Key JSON | User BYOK Input / Vault |
