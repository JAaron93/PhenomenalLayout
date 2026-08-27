# PhenomenalLayout

Domain-specific **German Philosophical Book Translation & Neologism Orchestration Engine**. PhenomenalLayout pairs **Google Cloud Document Translation API (Cloud Translation - Advanced v3)** with a specialized **German Philosophical Neologism Detection Engine** to translate full-length books (50–1,000+ pages) from German to English with pixel-perfect preservation of typography, multi-column tables, diagrams, and footnotes under a Bring Your Own Key (BYOK) serverless model on Modal Labs.

## 🎯 Core Innovation

**PhenomenalLayout is the intelligent orchestration layer** that bridges Google Cloud's Document Translation Advanced API with a specialized German philosophical terminology and compound decomposition engine, solving the fundamental challenge of translating complex philosophical texts while maintaining terminology consistency and visual layout integrity.

### What Makes PhenomenalLayout Unique

- **Native Cloud Document Translation**: Leverages Google Cloud Document Translation Advanced (v3) to deliver complete, layout-preserved PDFs with native typography, table formatting, and vector diagrams.
- **Dual-Tier Glossary Synchronization**: Synchronizes persistent foundation dictionaries (`klages_terminology.json`) with dynamic session user choices in GCP regional glossaries (`us-central1`).
- **German Philosophical Neologism Detector**: Morphological analysis and compound decomposition tailored for 19th- and 20th-century German philosophical texts.
- **Bring Your Own Key (BYOK) Billing Isolation**: All translation compute and storage are billed directly to the user's GCP project with zero translation host costs.
- **Zero Host PDF Storage Invariant**: Full-length book PDFs stream directly between user GCS buckets and personal Google Drive; zero book PDFs are stored on host disk.
- **Scholarly Resilience**: Fraktur OCR script assessment, atomic LRO session resumption, dynamic sequential 16-bit CID fallback page translation, and synchronized dual-pane reading.

## 🚀 Features

### 🎨 Advanced Layout Preservation Engine (Core Innovation)

- **Intelligent Text Fitting Analysis**: Proprietary algorithms that analyze translation length variations and automatically select optimal fitting strategies
- **Multi-Strategy Adaptation**:
  - Font scaling optimization (0.6-1.2x range) for minor size adjustments
  - Advanced text wrapping with quality-aware line breaks
  - Smart bounding box expansion with minimal visual impact
  - Quality scoring system to select the best preservation strategy
- **Translation-Aware Layout**: Deep integration between translation services and layout analysis for context-aware formatting decisions
- **Pixel-Perfect Positioning**: Precise text placement algorithms that maintain original document aesthetics

### 📝 Professional PDF Processing

- **Image-text overlay technique** for superior formatting preservation  
- **High-resolution rendering** (300 DPI) for precise text positioning
- **Complete layout analysis** with text element extraction
- **Background image preservation** with text overlay reconstruction
- **Comprehensive metadata extraction** including fonts, colors, and positioning

### Document Format Support

- **PDF only**: Advanced processing with image-text overlay preservation

### 🌍 Smart Translation Integration

- **Lingo.dev API orchestration** for high-quality translation with layout awareness
- **Layout-informed translation processing** that considers formatting constraints during translation
- **Parallel processing engine** optimized for large-scale document translation (5-10x faster)
- **Automatic language detection** with confidence scoring and layout compatibility analysis
- **Element-by-element translation** with intelligent layout preservation for each text block
- **Quality-aware fallback systems** with graceful degradation to original text when needed
- **Real-time progress tracking** with detailed layout preservation metrics

### 🚀 **NEW: High-Performance Parallel Translation**

- **5-10x faster processing** for large documents (up to 2,000 pages)
- **Async HTTP requests** with configurable concurrency (up to 10 concurrent)
- **Intelligent rate limiting** (5 requests/second default) to respect API limits
- **Batch processing** with configurable chunk sizes (50 texts per batch)
- **Automatic optimization** - chooses parallel vs sequential based on workload
- **Comprehensive error resilience** with exponential backoff retry
- **Real-time progress monitoring** with time estimation
- **Memory efficient** streaming processing for large documents

### Target Architecture: Google Cloud Document Translation & Neologism Orchestrator

PhenomenalLayout orchestrates Google Cloud's Document Translation API with an advanced German philosophical neologism detection and user-choice engine:

```mermaid
flowchart TD
    A[Upload German Book PDF] --> B[Fast Text Extraction & Neologism Scan]
    B --> C[Neologism Detector Identifies German Compounds & Terms]
    C --> D[User Choice UI: Confirm / Select Terminology Translations]
    D --> E[Generate Dynamic Cloud Translation Glossary]
    E --> F[Google Cloud Batch Document Translation: batchTranslateDocument (GCS)]
    F --> G[Download Pixel-Perfect Translated PDF with Intact Tables & Images]
```

> [!NOTE]
> For complete architectural details, see the [Architecture Decision Record (ADR 0001)](docs/adr/0001-migrate-to-google-cloud-document-translation.md) and the formal specification suite:
> - [System Design Spec](.kiro/specs/gcp-migration/design.md)
> - [Requirements & BDD Spec](.kiro/specs/gcp-migration/requirements.md)
> - [Actionable Tasks & TDD Plan](.kiro/specs/gcp-migration/tasks.md)

### Core Components

1. **GCP Batch Translation Service** (`services/gcp_batch_translation_service.py`)
   - Direct-to-GCS streamed PDF upload (`upload_book_to_gcs`) with zero host disk caching
   - Prefix-scoped 7-day auto-delete lifecycle policy management (`ensure_staging_lifecycle_policy`)
   - Asynchronous `batchTranslateDocument` dispatch (`submit_batch_job`) with dynamic glossary attachment
   - Non-blocking streaming reader (`stream_translated_book`)

2. **BYOK Credentials Manager** (`services/byok_credentials_manager.py`)
   - In-memory thread-safe user session vault with zero disk/logging persistence
   - Non-billable dual-service validation (`projects.locations.glossaries.list` + GCS bucket IAM checks)
   - 6-step guided onboarding modal guide with GCP console links and copyable `gcloud` scripts

3. **LRO Progress Monitor** (`services/lro_progress_monitor.py`)
   - Long-Running Operation (LRO) poller for `BatchTranslateDocumentMetadata`
   - Page-by-page progress tracking, percentage calculation, and linear ETA estimation
   - Exponential backoff retry on HTTP 429/503 errors

4. **Pre-Auth Cost Estimator** (`services/cost_estimator.py`)
   - Pre-auth PDF inspection via `pypdf.PdfReader` requiring zero credentials or network calls
   - Itemized quote: translation ($0.080/page), GCS 5 GB Always Free tier deduction, 7-day staging, and storage schedules ($\pm \$5.00$ tolerance)

5. **Google Drive GIS Exporter** (`services/google_drive_exporter.py`)
   - 1-click export to user's Google Drive via client-side Google Identity Services (GIS) OAuth (`drive.file` scope)
   - Direct multipart streaming upload via `MediaIoBaseUpload` with zero temporary host files

6. **Neologism Detection Engine** (`services/neologism_detector.py`)
   - Morphological compound analysis and decomposition
   - Philosophical context analyzer & confidence scoring
   - Built-in domain dictionaries (`config/klages_terminology.json`)

7. **User Choice & Disambiguation Manager** (`core/dynamic_choice_engine.py`, `services/user_choice_manager.py`)
   - Interactive review for coined philosophical terms
   - User override and custom translation management

8. **Web & API Interface** (`app.py`, `api/routes.py`)
   - Document upload, unauthenticated cost estimation, and terminology review
   - One-click asynchronous document translation and synchronized dual-pane viewer

9. **Persistent User Vocabulary Store** (`services/user_vocabulary_store.py`)
   - Thread-safe persistent SQLite storage in WAL mode (`/data/user_vocabularies/{user_id}.sqlite`)
   - Remembers user translation choices and `keep_untranslated` directives across book pre-scans
   - Automatic graceful fallback to local directory when `/data` volume root is read-only

10. **RFC 4180 Glossary TSV Compiler** (`services/glossary_compiler.py`)
    - Compiles UTF-8 RFC 4180 TSVs (`de\ten\n`) enforcing strict 3-tier precedence:
      `Book Session Overrides` > `User Persistent Vocabulary` > `Base Foundation Dictionary`
    - RFC 4180 quote escaping (`""`), alphabetical ordering, and German character preservation

11. **Dual-Tier Glossary Sync Manager** (`services/glossary_sync_manager.py`)
    - Idempotent regional provisioning of Tier 1 Base foundation glossary (`klages-philosophical-base-v1`)
    - Zero-downtime Blue-Green replacement (`-a` and `-b` slots) for Tier 2 Book Session glossaries
    - Strict 2-slot quota bounding, versioned GCS staging paths, and automatic rollback restoration on failure
    - Deterministic SHA-256 session token prefix isolation preventing collisions across sibling sessions

12. **Session Glossary Lifecycle Manager** (`services/session_glossary_lifecycle.py`)
    - Persistent session metadata tracking surviving serverless container restarts (`/data/session_glossaries.json`)
    - Automated cleanup of transient GCP glossaries and GCS staging TSVs upon book completion
    - Regional quota auditing (alerting at 900 of 1,000 regional quota limit in `us-central1`) and expiration pruning

13. **Historical Fraktur Font & OCR Script Classifier** (`services/fraktur_classifier.py`)
    - Evaluates font descriptors, font names (`Fraktur`, `Schwabacher`, `Gotisch`), and historical ligature distributions (`ſ`, `tz`, `ck`, `st`, `ch`)
    - Emits script classification (`FRAKTUR`, `ANTIQUA`, `HYBRID`) and calibrated OCR confidence rating $C \in [0.0, 1.0]$ for pre-1945 German editions

14. **Batch Job Recovery & Resumption Manager** (`services/batch_job_recovery.py`)
    - Atomic persistence of active LRO session state to Modal Volume storage (`/data/sessions/{user_id}_{book_id}.json`)
    - Seamless reconnection and sub-second (< 1.0s) job resumption across browser closes and serverless container scale-downs

15. **Fallback Plaintext Translation & Splicing Engine** (`services/fallback_translator.py`)
    - Secondary fallback for failed layout pages (`failed_pages > 0`), guaranteeing a 98% layout-preserved, 100% translated book
    - Strict 1-to-1 physical page correspondence with dynamic height expansion preventing line overlap or text clipping
    - Dynamic sequential 16-bit CID allocation per page with TrueType format 4 and format 12 (32-bit Unicode) `cmap` parsing and dynamic `/CIDToGIDMap` streams
    - 100% faithful preservation of Greek, Cyrillic, Hebrew, Arabic, German umlauts, Fraktur ligatures, and mathematical symbols without transliteration (documented in [`docs/FALLBACK_TRANSLATION_LIMITATIONS.md`](docs/FALLBACK_TRANSLATION_LIMITATIONS.md))

16. **Synchronized Dual-Pane Viewer Controller** (`services/dual_pane_viewer.py`)
    - Synchronized bilingual page retrieval (`BilingualPagePair`) mapping German original page $N$ directly to English translated page $N$
    - Word-level bounding box coordinate extraction (`HighlightCoordinates`, `TextBoundingBox`) for bilingual terminology highlighting
    - Graceful degradation for preview rasterization

## 🔬 Technical Deep-Dive: Layout Preservation Innovation

### The Translation-Layout Challenge

Translating documents presents a fundamental challenge: **translated text rarely matches the exact character count of the original**. For example:
- German → English: Often 20-30% longer
- English → Chinese: Character density varies dramatically
- Technical terms: May require longer explanations in target language

Traditional translation tools simply replace text, breaking layouts. **PhenomenalLayout solves this with sophisticated algorithms that adapt layouts to accommodate translation variations while preserving visual integrity.**

### PhenomenalLayout's Text Fitting Strategies

| Strategy | When Used | Algorithm | Quality Impact |
|----------|-----------|-----------|----------------|
| **NONE** | Translation fits perfectly | No adjustment needed | 1.0 (perfect) |
| **FONT_SCALE** | 5-20% size difference | Dynamic scaling (0.6-1.2x) | 0.8-0.95 |
| **TEXT_WRAP** | Significant overflow | Multi-line optimization | 0.7-0.9 |
| **BBOX_EXPAND** | Cannot fit otherwise | Intelligent expansion | 0.6-0.8 |

### Quality Assessment Engine

PhenomenalLayout includes a sophisticated quality scoring system:

```python
# Quality calculation (simplified)
quality_score = (
    font_scale_factor_impact +  # Penalty for font scaling
    text_wrapping_penalty +     # Cost of additional lines
    bbox_expansion_penalty      # Impact of size changes
) / total_factors

# Scores range from 0.0 (poor) to 1.0 (perfect)
```

### Integration with External Services

#### Lingo.dev Integration
- **High-quality translation** with context awareness
- **Batch processing optimization** for performance
- **Error handling** with graceful fallbacks
- **Rate limiting** respect for API constraints

#### Google Cloud Document Translation Advanced (v3) Integration
- **Direct GCS Asynchronous Batch Translation**: Zero host disk caching via `batchTranslateDocument`
- **Native Layout & Typography Preservation**: Preserves multi-column tables, figures, footnotes, and typography natively
- **Dual-Tier Regional Glossaries**: Synchronizes base philosophical terminology (`klages_terminology.json`) with dynamic session user choices in `us-central1`
- **7-Day Staging Lifecycle**: Automatic object expiration preventing unbounded user storage costs

#### PhenomenalLayout's Unique Contribution
- **Bridges the gap** between cloud translation scale and nuanced philosophical vocabulary
- **Interactive Neologism Resolution**: Empowers scholars to define or preserve coined compounds
- **Scholarly Verification**: Synchronized dual-pane bilingual verification and 1-click Google Drive export
- **Production Resilience**: Atomic LRO reconnection across container scale-downs and 100% translation completeness via fallback page synthesis

## 🛠️ Installation

### Quick Start

1. Clone the repository
2. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. *(Optional)* Configure GCP & Modal defaults via environment variables or `config/settings.py`:
   ```bash
   export GCP_LOCATION="us-central1"
   export GCP_DOC_PRICE_PER_PAGE="0.080"
   export GCS_STAGING_EXPIRATION_DAYS="7"
   export MODAL_VOLUME_PATH="/data"
   ```
4. Run the application:
   ```bash
   python app.py
   ```
5. In the web interface:
   - Calculate an unauthenticated cost quote for your German PDF book.
   - Enter your personal GCP Service Account credentials in the BYOK setup panel (validated non-billably in session memory).
   - Review and select neologism translations, then dispatch the batch translation job.

### Development Setup

**Prerequisites**: Python 3.11 or 3.12 recommended (match CI environment)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
python -m pip install -U pip
python -m pip install -r requirements-dev.txt

# Run all GCP migration test suites (Track 1 & Track 2 - 123 tests)
pytest -o addopts="" tests/test_dry_helpers.py tests/test_gcp_settings.py \
  tests/test_byok_credentials_manager.py tests/test_gcp_batch_translation_service.py \
  tests/test_lro_progress_monitor.py tests/test_cost_estimator.py \
  tests/test_google_drive_exporter.py tests/test_user_vocabulary_store.py \
  tests/test_glossary_compiler.py tests/test_glossary_sync_manager.py \
  tests/test_session_glossary_lifecycle.py -v

# Run linter and formatter manually
ruff check .
black --check .
mypy .
```

### Debug and Development Tools

For local development and debugging, several utility scripts are available in the `scripts/` directory:

- **Environment Debugging**: Verify configuration and test authentication
  ```bash
  python scripts/debug_test_env.py
  ```

- **Dependency Management**: Sync and update project dependencies
  ```bash
  ./scripts/sync-deps.sh
  ./scripts/update-deps.sh
  ```

See `scripts/README.md` for complete documentation of available development tools.

**Note**: Pre-commit hooks auto-format code (Black, trailing whitespace) and may abort your first commit attempt. Simply re-stage files and commit again.

For detailed development guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Requirements

- Python 3.11 or 3.12 recommended (3.8–3.12 supported). Python 3.13 support pending due to Pillow 10 wheels.
- Core libs are pinned in `requirements.txt` (e.g., `pdf2image==1.17.0`, `Pillow==11.3.0`, `reportlab==4.2.5`, `pypdf==6.7.3`).
- Poppler runtime required by `pdf2image` (provides `pdftoppm`/`pdfinfo`). Ensure it's installed and on PATH:
  - Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y poppler-utils`
  - macOS: `brew install poppler`
- Client/Server: `fastapi`, `uvicorn`, `httpx`
- UI: `gradio`
- Testing: `pytest`, `pytest-cov`
- Valid Lingo API key for translation functionality

## 📁 Key Files

### Core Application

- `app.py` - Main application with advanced Gradio interface
- `services/enhanced_document_processor.py` - PDF-only document handler

### Translation & Cloud Document Services

- `services/gcp_batch_translation_service.py` - Primary asynchronous GCS batch translation engine (`batchTranslateDocument`)
- `services/byok_credentials_manager.py` - In-memory BYOK credentials vault with non-billable validation
- `services/lro_progress_monitor.py` - Long-Running Operation (LRO) batch progress monitor
- `services/cost_estimator.py` - Pre-auth zero-credential PDF translation & GCS retention estimator
- `services/google_drive_exporter.py` - Streamed Google Drive export via Google Identity Services OAuth
- `services/glossary_sync_manager.py` - Dual-tier GCP regional glossary synchronizer (Blue-Green replacement)
- `services/session_glossary_lifecycle.py` - Session glossary tracking, regional quota auditing, and auto-cleanup
- `services/glossary_compiler.py` - RFC 4180 TSV glossary compiler enforcing 3-tier precedence
- `services/user_vocabulary_store.py` - Persistent user terminology store on Modal Volume SQLite
- `services/translation_service.py` - Legacy translation service with Lingo.dev integration

### Supporting Services

- `services/language_detector.py` - Language detection utilities
- `services/neologism_detector.py` - Philosophy-focused neologism detection
- `services/user_choice_manager.py` - User choice management for translations

### Configuration & Utilities

- `config.py` - Main configuration with parallel processing settings
- `config/settings.py` - Additional configuration management
- `utils/gcp_helpers.py` - Canonical GCS URI parsing, blob deletion, regional glossary naming, and exponential backoff retry utilities
- `utils/tsv_utils.py` - RFC 4180 compliant TSV quoting, formatting, and bytes serialization
- `utils/pdf_stream.py` - Polymorphic streaming context manager for PDF inputs with deterministic descriptor cleanup
- `utils/file_handler.py` - File handling, validation, and crash-safe atomic write routines (`atomic_write_json`, `atomic_write_text`, `atomic_write_bytes`)

### Testing & Examples

- `tests/test_parallel_translation.py` - Comprehensive parallel translation tests
- `examples/parallel_translation_demo.py` - Working demonstration of parallel capabilities
- `simple_test_runner.py` - Basic functionality tests

#### UI testing notes

- **GRADIO_SCHEMA_PATCH**
  - **Purpose**: Enables a test-only monkeypatch that tolerates boolean JSON Schema fragments emitted by some `gradio_client` versions. Prevents failures in API schema parsing without pinning Gradio.
  - **Accepted truthy values**: `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive).
  - **When to set**: Only during tests. Automatically enabled in CI by default; set locally if you encounter schema parsing errors.
  - **Default**: Off locally; On in CI.

- **GRADIO_SHARE**
  - **Purpose**: Forces use of a public share URL when localhost isn't reachable (e.g., headless/CI). Stabilizes Gradio UI tests that use `gradio_client`.
  - **Accepted truthy values**: `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive).
  - **When to set**: Headless environments or CI where `http://127.0.0.1` cannot be accessed.
  - **Default**: Off locally; typically On in CI via test helpers.

- **Pytest markers**
  - Use `-m "not slow"` to skip slower-running integration tests.

Example command:

```bash
GRADIO_SCHEMA_PATCH=true GRADIO_SHARE=true pytest -q -m "not slow" tests/test_ui_gradio.py
```

## ☁️ Cloud Architecture & Serverless Deployment (Modal Labs)

> [!NOTE]
> Under [ADR 0001](docs/adr/0001-migrate-to-google-cloud-document-translation.md) and Track 4 (`TASK-4.1`), dedicated GPU OCR worker instances (`services/dolphin_modal_service.py`, `services/dolphin_client.py`) and custom ReportLab canvas reconstruction were retired and permanently removed. Document OCR, font matching, and geometric layout preservation are now outsourced directly to **Google Cloud Document Translation Advanced (v3)**.

PhenomenalLayout runs serverless on **Modal Labs** under a **Bring Your Own Key (BYOK)** billing isolation architecture:

- **Serverless ASGI Web App**: Deployed via `@modal.asgi_app()` with automatic scale-to-zero when idle (`scaledown_window=300`), operating comfortably within Modal's free compute tier.
- **Zero Host PDF Storage Invariant**: The host maintains zero translation API or cloud storage costs. Source PDFs and translated outputs reside strictly in the user's GCS bucket or personal Google Drive.
- **Persistent Vocabulary Storage**: User neologism choices and translation directives are persisted per `user_id` on the Modal Volume (`modal.Volume.from_name("phenomenal-user-data")` mounted at `/data`).

### Deploying to Modal Labs

```bash
# Deploy the ASGI web application to Modal
modal deploy modal_app.py

# Local development / hot-reload
modal serve modal_app.py
```

### BYOK Onboarding & Credentials Setup

Users configure their personal Google Cloud credentials via an interactive 6-step guided walkthrough modal:

1. **Non-Billable Validation**: Credentials are validated via free API calls (`projects.locations.glossaries.list` + bucket permission checks) before any batch job is submitted.
2. **Lifecycle Policy Enforcement**: Staging prefixes (`inputs/`) enforce an unconditional 7-day auto-delete lifecycle policy on the user's bucket to prevent unbounded storage costs.
3. **Session Memory Isolation**: User Service Account keys are held strictly in ephemeral session memory and never written to disk or logs.

## 📦 Dependency management (pip-tools)

We manage pinned dependencies with pip-tools for reproducible builds.

Core files
- requirements.in → High-level runtime deps
- requirements.txt → Pinned runtime deps (auto-generated)
- dev-requirements.in → High-level dev deps (includes requirements.in)
- dev-requirements.txt → Pinned dev deps (auto-generated)

Common workflows
```bash
# Dev setup (installs dev deps)
./scripts/sync-deps.sh

# Prod-only setup (runtime deps)
./scripts/sync-deps.sh prod

# Update all pins from *.in
./scripts/update-deps.sh
```

Important
- Don't edit requirements.txt or dev-requirements.txt directly. Edit the *.in files and run ./scripts/update-deps.sh
- pdf2image is pinned to >=1.17.0 for compatibility with Debian Bookworm + poppler-utils in the Modal image

### Optional Security Scanning

For additional security, you can run basic security scans:

```bash
# Install security tools (optional)
pip install bandit safety

# Run security scans
bandit -r services/              # Static security analysis
safety check                     # Check for known vulnerabilities
```

## 🔧 Configuration

### Google Cloud & Dual-Tier Glossary Settings
Configure environment variables for Google Cloud Document Translation v3 and regional glossary synchronization:

- `GCP_PROJECT_ID` (str): Target Google Cloud project identifier.
- `GCS_BUCKET_NAME` (str): Google Cloud Storage bucket for document staging and TSV glossary storage.
- `GCP_TRANSLATION_LOCATION` (str): Regional GCP endpoint (default: `"us-central1"`).
- `GCP_BASE_GLOSSARY_ID` (str): Regional glossary ID for the Tier 1 base philosophical foundation dictionary (default: `"klages-philosophical-base-v1"`).
- `GCP_BASE_GLOSSARY_TSV_PATH` (str): Local path to the base terminology dictionary (default: `"config/klages_terminology.json"`).
- `GCP_GLOSSARY_QUOTA_ALERT_THRESHOLD` (int): Number of regional glossaries that triggers warning alerts (default: `900`).
- `GCP_GLOSSARY_QUOTA_LIMIT` (int): Hard regional limit for GCP Translation glossaries (default: `1000`).
- `GCP_SESSION_GLOSSARY_TTL_HOURS` (int): Time-to-live before pruning expired session glossaries (default: `24`).

### PDF Processing Settings
- `PDF_DPI` (int): Resolution for PDF rendering; affects pdf2image conversion. Default: 300 DPI.
- `PRESERVE_IMAGES` (bool): Preserve embedded images. Default: true.
- `MEMORY_THRESHOLD_MB` (int): Memory threshold used by some validators. Default: 500.
- `MAX_CONCURRENT_REQUESTS` (int): Concurrency for translation.
- `MAX_REQUESTS_PER_SECOND` (float): Token-bucket rate for translation requests.
- `TRANSLATION_BATCH_SIZE` (int): Text batch size for translation.

### Translation & GCP API Configuration
**Primary Cloud Translation (BYOK):**
- Provided interactively per user session or via `GOOGLE_APPLICATION_CREDENTIALS`
- `GCP_PROJECT_ID`: User's Google Cloud project ID
- `GCS_BUCKET_NAME`: User's Cloud Storage bucket for staging and outputs

**Secondary / Direct Translation API:**
- `LINGO_API_KEY`: Lingo.dev API key (optional rapid preview or fallback)

### 🚀 Parallel Translation Settings
Configure these environment variables to optimize performance for your use case:

- `MAX_CONCURRENT_REQUESTS`: Maximum concurrent API requests (default: 10)
- `MAX_REQUESTS_PER_SECOND`: Rate limit for API requests (default: 5.0)
- `TRANSLATION_BATCH_SIZE`: Number of texts per batch (default: 50)
- `TRANSLATION_MAX_RETRIES`: Maximum retry attempts for failed requests (default: 3)
- `TRANSLATION_REQUEST_TIMEOUT`: Request timeout in seconds (default: 30.0)
- `PARALLEL_PROCESSING_THRESHOLD`: Minimum texts to trigger parallel processing (default: 5)
- `MAX_FILE_SIZE_BYTES`: Maximum file size for uploads in bytes (default: 52428800, which is 50MB)

**Example configuration:**
```bash
# Basic API setup
export LINGO_API_KEY="your_lingo_api_key_here"

# High-performance setup for large documents
export MAX_CONCURRENT_REQUESTS=15
export MAX_REQUESTS_PER_SECOND=8.0
export TRANSLATION_BATCH_SIZE=100
export MAX_FILE_SIZE_BYTES=104857600  # 100MB

# Conservative setup for API rate limits
export MAX_CONCURRENT_REQUESTS=5
export MAX_REQUESTS_PER_SECOND=2.0
export TRANSLATION_BATCH_SIZE=25
export MAX_FILE_SIZE_BYTES=26214400   # 25MB
```

## 🔒 Security

### Basic Security Features

The Dolphin Modal service includes essential security measures:

#### File Upload Security
- **Content Validation**: PDF Content-Type and magic bytes validation
- **File Size Limits**: Configurable via `MAX_FILE_SIZE_BYTES` (default: 50MB)
- **Filename Sanitization**: Protection against directory traversal attacks

#### Security Headers
Basic security headers are automatically applied:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=31536000
```

#### Rate Limiting
- Basic rate limiting: 60 requests per minute per IP (configurable)
- Set via environment variable: `API_RATE_LIMIT_PER_MINUTE`

#### Optional Authentication
For production deployments, you can enable simple API key authentication:

```bash
# Set API key for protected access
export ADMIN_API_KEY="your-secure-api-key"

# Use API key in requests
curl -X POST https://your-domain/ \
  -H "X-API-Key: your-secure-api-key" \
  -F "pdf_file=@document.pdf"
```

#### Environment Variables
```bash
# File upload limits
export MAX_FILE_SIZE_BYTES="52428800"  # 50MB

# Rate limiting
export API_RATE_LIMIT_PER_MINUTE="60"

# Optional authentication
export ADMIN_API_KEY="your-api-key"  # Optional

# CORS (for web apps)
export ALLOWED_ORIGINS="*"  # Or specific domains
```

### Security Best Practices

1. **Deploy with HTTPS**: Always use TLS in production
2. **Limit File Sizes**: Adjust `MAX_FILE_SIZE_BYTES` for your needs
3. **Monitor Logs**: Check for suspicious upload patterns
4. **API Key Protection**: If using authentication, keep API keys secure

## 💻 Usage Examples

### Enhanced Translation Service (Recommended)
Drop-in replacement with automatic parallel processing optimization:

```python
import asyncio
from services.enhanced_translation_service import EnhancedTranslationService

async def translate_document():
    # Initialize service (automatically detects optimal processing method)
    service = EnhancedTranslationService()

    # Translate a batch of texts (automatically uses parallel processing for large batches)
    texts = ["Text 1", "Text 2", "Text 3", ...]  # Up to 2,000+ texts
    translated = await service.translate_batch_enhanced(
        texts=texts,
        source_lang="de",
        target_lang="en",
        progress_callback=lambda current, total: print(f"Progress: {current}/{total}")
    )

    # Translate document content
    document_content = {"pages": {...}}  # Your document structure
    translated_doc = await service.translate_document_enhanced(
        content=document_content,
        source_lang="de",
        target_lang="en",
        progress_callback=lambda progress: print(f"Progress: {progress}%")
    )

    # Get performance statistics
    stats = service.get_performance_stats()
    print(f"Parallel usage: {stats['parallel_usage_percentage']:.1f}%")
    print(f"Average processing time: {stats['average_request_time']:.2f}s")

    await service.close()

# Run the example
asyncio.run(translate_document())
```

### Direct Parallel Translation Service
For advanced users who need direct control over parallel processing:

```python
import asyncio
from services.parallel_translation_service import (
    ParallelTranslationService,
    ParallelTranslationConfig,
    BatchProgress
)

async def advanced_parallel_translation():
    # Custom configuration for high-performance processing
    config = ParallelTranslationConfig(
        max_concurrent_requests=15,
        max_requests_per_second=8.0,
        batch_size=100,
        max_retries=5
    )

    # Initialize parallel service
    async with ParallelTranslationService("your_lingo_api_key", config) as service:
        # Translate large batch with progress tracking
        texts = ["Text {}".format(i) for i in range(1000)]  # Large batch

        def progress_callback(progress: BatchProgress):
            print(f"Completed: {progress.completed_tasks}/{progress.total_tasks}")
            print(f"Progress: {progress.progress_percentage:.1f}%")
            print(f"Estimated remaining: {progress.estimated_remaining_time:.1f}s")

        translated = await service.translate_batch_texts(
            texts=texts,
            source_lang="de",
            target_lang="en",
            progress_callback=progress_callback
        )

        print(f"Translated {len(translated)} texts successfully!")

# Run the advanced example
asyncio.run(advanced_parallel_translation())
```

### Backward Compatibility
The enhanced service maintains full compatibility with existing code:

```python
# Existing code continues to work unchanged
from services.enhanced_translation_service import EnhancedTranslationService

service = EnhancedTranslationService()
# All existing TranslationService methods work exactly the same
result = await service.translate_text("Hello", "en", "de")
batch_result = await service.translate_batch(texts, "en", "de")
```

## 🎯 Advantages Over the Previous PDF Approach

1. **Superior Formatting Preservation**
   - Image-text overlay technique maintains exact visual layout
   - High-resolution rendering captures fine details
   - Precise text positioning with pixel-level accuracy

2. **Comprehensive Layout Analysis**
   - Complete extraction of text elements with metadata
   - Font, color, and styling information preservation
   - Advanced handling of complex page structures

3. **Robust Error Handling**
   - Graceful degradation when translation fails
   - Memory management for large documents
   - Automatic cleanup and resource management

4. **Enhanced User Experience**
   - Real-time processing status with detailed metrics
   - Advanced preview with processing information
   - Multiple output format options

## 📊 Processing Metrics

The system provides detailed processing metrics:
- File type and size analysis
- Processing time tracking
- Text element count and distribution
- Memory usage monitoring
- Translation progress and success rates

## 🔄 Architectural Evolution: From Heuristic Overlays to Google Cloud Document Translation

PhenomenalLayout has evolved through three major architectural eras:

1. **Era 1 (Legacy PyMuPDF)**: Primitive text-extraction and heuristic overlay positioning (retired).
2. **Era 2 (Dolphin OCR & ReportLab)**: Dedicated GPU OCR containers on Modal and ReportLab canvas box-fitting (retired under ADR 0001 / Track 4).
3. **Era 3 (Google Cloud Document Translation Advanced v3)**: Native document-scale translation preserving multi-column typography, tables, and figures with zero host PDF storage and regional dual-tier glossary synchronization.

### Modern Architecture Invariants (Track 4 Streamlining)
- **Direct-to-GCS Processing**: Large book PDFs stream directly into user GCS staging buckets (`inputs/`) with an unconditional 7-day auto-delete policy.
- **Native Layout Preservation**: Google Cloud Document Translation handles font scaling, column wrapping, diagram overlays, and vector graphics natively.
- **Runtime Dependency Pruning**: Heavy dependencies like `reportlab` have been eliminated from runtime production requirements (retained solely in `requirements-dev.txt` for mock test fixtures).
- **Scholarly Fallback & Unicode Fidelity**: Fallback page synthesis uses `pypdf` composite Type 0 fonts (`/CIDFontType2`) with format 4/12 TrueType `cmap` parsing and dynamic sequential 16-bit CID allocation, completely replacing legacy ReportLab canvas painting.

### Deprecated Components & Replacements

| Legacy Component | Deprecation Status | Modern Replacement |
| :--- | :--- | :--- |
| `services/pdf_document_reconstructor.py` | Permanently deleted | Google Cloud Document Translation Advanced (v3) |
| `services/dolphin_client.py` | Permanently deleted | Google Cloud Document Translation Advanced (v3) |
| `services/dolphin_modal_service.py` | Permanently deleted | Serverless ASGI app on Modal (`modal_app.py`) + GCP Translation |
| `core/dynamic_layout_engine.py` | Deprecated (ADR 0001) | Cloud Translation handles typography scaling natively |
| `services/enhanced_document_processor.py` | Deprecated (ADR 0001) | `services/gcp_batch_translation_service.py` |
| `reportlab` (runtime) | Removed from `requirements.txt` | Cloud Translation + `pypdf` TrueType fallback renderer |

### 🚀 Parallel Translation
- **API Key Required**: Valid Lingo.dev API key is mandatory for translation functionality
- **Rate Limiting**: Respects API rate limits automatically with intelligent throttling
- **Memory Efficiency**: Designed for large documents but monitor memory usage for 2,000+ pages
- **Backward Compatibility**: All existing code continues to work without modification
- **Automatic Optimization**: System automatically chooses parallel vs sequential processing
- **Error Resilience**: Failed translations fall back to original text, ensuring no data loss
- **Configuration**: Fine-tune performance settings via environment variables for your specific use case

### Best Practices
- Start with default settings and adjust based on your API limits and performance needs
- Monitor API usage to stay within your Lingo.dev plan limits
- Use progress callbacks for long-running operations to provide user feedback
- Test with smaller documents before processing large batches
- Consider using `EnhancedTranslationService` for most use cases (automatic optimization)

## 📈 Performance Considerations

### Traditional Processing
- **Memory Usage**: Higher due to image rendering, managed with automatic garbage collection
- **Processing Time**: Longer for complex documents, with progress tracking
- **Quality**: Significantly improved formatting preservation
- **Scalability**: Designed for production use with proper resource management

### 🚀 Parallel Translation Performance
- **Speed Improvement**: 5-10x faster for large documents (2,000+ pages)
- **Throughput**: Up to 10 concurrent requests with intelligent rate limiting
- **Memory Efficiency**: Streaming processing minimizes memory footprint
- **Scalability**: Handles enterprise-scale document processing
- **Reliability**: Comprehensive error handling with automatic retry
- **Monitoring**: Real-time progress tracking with time estimation

### Performance Benchmarks
| Document Size | Sequential Time | Parallel Time | Improvement |
|---------------|----------------|---------------|-------------|
| 50 pages      | ~25 seconds    | ~8 seconds    | 3.1x faster |
| 200 pages     | ~100 seconds   | ~15 seconds   | 6.7x faster |
| 1000 pages    | ~500 seconds   | ~60 seconds   | 8.3x faster |
| 2000 pages    | ~1000 seconds  | ~120 seconds  | 8.3x faster |

### 🧪 Testing Methodology & Benchmark Context

#### Test Environment
- **Hardware**: MacBook Pro M2, 16GB RAM, macOS Sonoma
- **Python Version**: 3.13.x with asyncio event loop
- **Network**: Stable broadband connection (100+ Mbps)
- **API Provider**: Lingo.dev with standard rate limits
- **Test Location**: US West Coast (optimal for API latency)

#### Test Configuration
```bash
# Benchmark Configuration Used
MAX_CONCURRENT_REQUESTS=10
MAX_REQUESTS_PER_SECOND=5.0
TRANSLATION_BATCH_SIZE=50
TRANSLATION_MAX_RETRIES=3
TRANSLATION_REQUEST_TIMEOUT=30.0
```

#### Test Methodology
1. **Document Preparation**:
   - Used German philosophical texts (Kant, Heidegger, Husserl)
   - Average text density: ~250 words per page
   - Mixed content: paragraphs, quotes, footnotes, technical terminology
   - Text extracted and segmented into translation units

2. **Measurement Process**:
   - Each test run 3 times, results averaged
   - Timing measured from translation start to completion
   - Excluded document parsing and setup time
   - Measured pure translation processing time only

3. **Sequential Baseline**:
   - Standard `TranslationService` with 0.1s delay between requests
   - Single-threaded processing with synchronous HTTP requests
   - No concurrent processing or batching optimizations

4. **Parallel Testing**:
   - `EnhancedTranslationService` with automatic optimization
   - Async HTTP requests with configurable concurrency
   - Intelligent batching and rate limiting applied

#### Important Disclaimers

⚠️ **Performance Variability Factors**:
- **Document Content**: Technical texts with specialized terminology may process slower
- **Network Conditions**: Internet latency and bandwidth affect API response times
- **API Response Times**: Lingo.dev server load and geographic location impact speed
- **System Resources**: Available CPU, memory, and concurrent processes affect performance
- **Rate Limiting**: API quotas and rate limits may throttle processing speed
- **Text Complexity**: Dense philosophical content may require longer processing

⚠️ **Benchmark Limitations**:
- Results based on specific test environment and may not reflect your setup
- Performance improvements depend on optimal network conditions
- API rate limits and quotas may vary by subscription plan
- Actual performance may be 20-50% different based on your specific conditions

⚠️ **Recommendations for Your Environment**:
- Start with small test batches to measure your actual performance
- Monitor API usage and adjust concurrency settings accordingly
- Test with your specific document types and content complexity
- Consider your network latency to Lingo.dev servers
- Adjust `MAX_CONCURRENT_REQUESTS` based on your API plan limits

#### Reproducing Benchmarks
To test performance in your environment:

```python
import asyncio
import time
from services.enhanced_translation_service import EnhancedTranslationService

async def benchmark_translation():
    service = EnhancedTranslationService()

    # Create test texts (adjust size as needed)
    test_texts = ["Sample German text..."] * 100  # 100 texts for testing

    # Measure sequential processing
    start_time = time.time()
    # Use original TranslationService for baseline
    sequential_time = time.time() - start_time

    # Measure parallel processing
    start_time = time.time()
    results = await service.translate_batch_enhanced(
        test_texts, "de", "en"
    )
    parallel_time = time.time() - start_time

    improvement = sequential_time / parallel_time
    print(f"Improvement: {improvement:.1f}x faster")

    await service.close()

# Run your own benchmark
asyncio.run(benchmark_translation())
```

## 🤝 Contributing

See `CONTRIBUTING.md` for development workflow, lint/type-check configurations, pytest markers, and automated dependency updates (Dependabot). This ensures local and CI runs use the same rules and remain reproducible.
