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
- **Scholarly Resilience**: Fraktur OCR script assessment, atomic LRO session resumption, transparent failed-page surfacing with 1-click re-run, and synchronized dual-pane reading.

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

- **User-bound Google Cloud Translation v3 (BYOK)** for high-quality translation with layout awareness
- **Layout-informed translation processing** that considers formatting constraints during translation
- **Asynchronous GCS batch engine** optimized for large-scale document translation (up to 2,000+ pages)
- **Automatic language detection** with confidence scoring and layout compatibility analysis
- **Element-by-element translation** with intelligent layout preservation for each text block
- **Fail-closed credential semantics** — translation never silently falls back to source text
- **Real-time progress tracking** with detailed layout preservation metrics

### 🚀 Asynchronous Batch Translation (Large Documents)

- **GCS-staged batch processing** for large documents (up to 2,000+ pages)
- **Long-Running Operation (LRO) progress** with `translated_pages`/`total_pages`/`failed_pages` metadata
- **Dual-tier glossary synchronization** (base terminology + per-book session glossaries in `us-central1`)
- **Zero-downtime blue-green glossary replacement** bounded to two regional slots
- **Automatic job resumption** across browser closes and container scale-downs
- **Transparent failed-page surfacing** with isolated re-run submissions
- **Real-time progress monitoring** with time estimation
- **Zero host PDF storage** — streams directly to/from the user's GCS bucket

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

6. **Neologism Detection Engine** (`services/neologism_detector.py`, `utils/language_utils.py`)
   - Canonical `is_german_compound_word` with precompiled regexes and inflected derivational suffix filtering (`utils/language_utils.py`)
   - Unified morphological compound analysis and decomposition across `ConfidenceScorer`, `MorphologicalAnalyzer`, and `NeologismDetector`
   - Philosophical context analyzer & confidence scoring
   - Built-in domain dictionaries (`config/klages_terminology.json`)

7. **User Choice & Disambiguation Manager** (`models/user_choice_models.py`, `services/user_choice_manager.py`)
   - Interactive review for coined philosophical terms
   - High-performance term-bucketed conflict detection (`detect_choice_conflicts`) reducing comparison complexity from $O(N^2)$ to $O(N + \sum K_i^2)$ (< 50ms benchmark for $N=1,000$ choices)
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

15. **Transparent Failed-Page Surfacing & Re-run Isolation** (`services/book_translation_orchestrator.py`)
    - Native Google Cloud Document Translation Advanced (v3) batch processing without local synthesis (ADR 0002)
    - Transparent reporting of layout-parsing failures (`failed_pages > 0`) with 1-click re-run action under isolated GCS output prefixes (`{book_id}-r2`)

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

#### Google Cloud Document Translation Advanced (v3) Integration
- **Direct GCS Asynchronous Batch Translation**: Zero host disk caching via `batchTranslateDocument`
- **Native Layout & Typography Preservation**: Preserves multi-column tables, figures, footnotes, and typography natively
- **Dual-Tier Regional Glossaries**: Synchronizes base philosophical terminology (`klages_terminology.json`) with dynamic session user choices in `us-central1`
- **7-Day Staging Lifecycle**: Automatic object expiration preventing unbounded user storage costs

#### PhenomenalLayout's Unique Contribution
- **Bridges the gap** between cloud translation scale and nuanced philosophical vocabulary
- **Interactive Neologism Resolution**: Empowers scholars to define or preserve coined compounds
- **Scholarly Verification**: Synchronized dual-pane bilingual verification and 1-click Google Drive export
- **Production Resilience**: Atomic LRO reconnection across container scale-downs and isolated re-run workflows for partial failures (ADR 0002)

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

**Prerequisites**: Python 3.12+ (3.13 recommended — matches the CI environment). The codebase uses PEP 695 generic syntax (`class Foo[T]`), which requires Python 3.12 or later.

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

- Python 3.12 or 3.13 supported (3.13 recommended; enforced via `requires-python = ">=3.12"` in `pyproject.toml`).
- Core libs are pinned in `requirements.txt` (e.g., `fastapi==0.162.0`, `starlette==1.10.0`, `pypdf==6.21.4`, `google-cloud-translate==3.28.0`, `google-cloud-storage==3.17.1`).
- Poppler & OCR runtimes: Retired under ADR 0002. OCR and document layout parsing are outsourced directly to Google Cloud Document Translation Advanced v3.
- Client/Server: `fastapi`, `uvicorn`, `httpx`, `starlette>=1.0.0`
- UI: Bespoke zero-build vanilla ES modules single-page application served directly from `static/`
- Testing: `pytest>=9.0,<10.0`, `pytest-cov`, `pytest-asyncio`, `pytest-playwright`
- BYOK credentials: personal Google Cloud Translation v3 Service Account JSON, validated in-session (no env keys)

## 📁 Key Files

### Core Application

- `app.py` - Main FastAPI application serving the bespoke vanilla ES single-page interface (`static/`)
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
- `services/gcp_sync_translation_service.py` - User-bound synchronous GCP translation engine (BYOK, fail-closed)
- `services/philosophy_enhanced_translation_service.py` - Philosophy-enhanced translation with neologism handling over the BYOK engine

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
- requirements.txt → Pinned runtime deps (auto-generated from requirements.in)
- requirements-dev.txt → Pinned dev and CI test/lint dependencies

Common workflows
```bash
# Dev setup (installs runtime + dev deps)
./scripts/sync-deps.sh

# Prod-only setup (runtime deps)
./scripts/sync-deps.sh prod

# Update runtime pins from requirements.in
./scripts/update-deps.sh
```

Important
- Don't edit requirements.txt directly. Edit requirements.in and run `uv pip compile requirements.in -o requirements.txt`
- Runtime Pillow, pdf2image, and ReportLab have been retired under ADR 0002. Test fixtures keep ReportLab in requirements-dev.txt only.

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
- `PDF_DPI` (int): Resolution for PDF rendering. Default: 300 DPI.
- `PRESERVE_IMAGES` (bool): Preserve embedded images. Default: true.
- `MEMORY_THRESHOLD_MB` (int): Memory threshold used by some validators. Default: 500.
- `MAX_CONCURRENT_REQUESTS` (int): Concurrency for translation.
- `MAX_REQUESTS_PER_SECOND` (float): Token-bucket rate for translation requests.
- `TRANSLATION_BATCH_SIZE` (int): Text batch size for translation.

### Translation & GCP API Configuration
**Cloud Translation (BYOK):**
- Provided interactively per user session or via `GOOGLE_APPLICATION_CREDENTIALS`
- `GCP_PROJECT_ID`: User's Google Cloud project ID
- `GCS_BUCKET_NAME`: User's Cloud Storage bucket for staging and outputs

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

The serverless Modal application includes essential security measures:

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

### User-Bound GCP Translation Engine (BYOK)
The only request-path engine: one instance represents one user's content-tier engine:

```python
import asyncio
from services.byok_credentials_manager import BYOKCredentialsManager
from services.gcp_sync_translation_service import GcpSyncTranslator

async def translate_texts():
    # Manager holds the user's Service Account JSON in session memory only
    manager = BYOKCredentialsManager()

    # Bind the engine to one user's vault
    service = GcpSyncTranslator(manager, "scholar-42")

    texts = ["Text 1", "Text 2", "Text 3"]
    translated = await service.translate_batch(
        texts=texts,
        source_lang="de",
        target_lang="en",
    )

    # Statistics: stable per-engine telemetry
    print(service.get_statistics())

    # Lifecycle no-op: BYOK owns the clients; engine holds no host sessions
    await service.aclose()

asyncio.run(translate_texts())
```

### Philosophy-Enhanced Translation with Neologism Handling
Neologism detection and user-choice preservation ride on the BYOK engine:

```python
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
)

service = PhilosophyEnhancedTranslationService(
    translation_service=bound_engine,  # user-bound GcpSyncTranslator
)

result = service.translate_text_with_neologism_handling(
    "Das Wirklichkeitsbewusstsein ist zentral...",
    source_lang="de",
    target_lang="en",
)
print(result.translated_text)          # translation with neologisms preserved
print(result.neologisms_preserved)     # per-term handling decisions
```

### Fail-Closed Credential Semantics
Without a bound engine (or with rejected credentials), translation fails closed:

```python
from services.gcp_sync_translation_service import GcpSyncCredentialsRequiredError

try:
    await service.translate_batch(texts=texts, source_lang="de", target_lang="en")
except GcpSyncCredentialsRequiredError as exc:
    assert exc.code == "GCP_CREDENTIALS_REQUIRED"
    # The UI surfaces the BYOK setup flow; source text is NEVER returned as a
    # silent fallback (ADR 0004 invariant).
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
- **Runtime Dependency Pruning**: Heavy dependencies like `reportlab`, `pdf2image`, and `Pillow` have been fully eradicated from all dependency manifests (runtime and dev). PDF test fixtures use the stdlib-only `build_test_pdf()` helper in `tests/conftest.py`.
- **Scholarly Fallback & Unicode Fidelity**: Fallback page synthesis uses `pypdf` composite Type 0 fonts (`/CIDFontType2`) with format 4/12 TrueType `cmap` parsing and dynamic sequential 16-bit CID allocation, completely replacing legacy ReportLab canvas painting.

### Deprecated Components & Replacements

| Legacy Component | Deprecation Status | Modern Replacement |
| :--- | :--- | :--- |
| `services/pdf_document_reconstructor.py` | Permanently deleted (ADR 0001) | Google Cloud Document Translation Advanced (v3) |
| `services/dolphin_client.py` | Permanently deleted (ADR 0001) | Google Cloud Document Translation Advanced (v3) |
| `services/dolphin_modal_service.py` | Permanently deleted (ADR 0001) | Serverless ASGI app on Modal (`modal_app.py`) + GCP Translation |
| `core/dynamic_layout_engine.py` | Deprecated (ADR 0001) | Cloud Translation handles typography scaling natively |
| `services/enhanced_document_processor.py` | Deprecated (ADR 0001) | `services/gcp_batch_translation_service.py` |
| `services/fallback_translator.py` | Permanently deleted (ADR 0002) | Google Cloud Document Translation sole pipeline; transparent failed-page re-run |
| `ui/gradio_interface.py` | Permanently deleted (ADR 0002) | Bespoke zero-build vanilla ES modules SPA (`static/`) |
| `reportlab` (all manifests) | Permanently removed (PR #147) | `build_test_pdf(pages)` in `tests/conftest.py` — stdlib-only PDF 1.4 writer; Pillow now fully eradicated from all dependency trees |
| `services/translation_service.py` / `services/mcp_lingo_client.py` / `services/parallel_translation_service.py` / `services/enhanced_translation_service.py` | Permanently deleted (ADR 0004) | User-bound `GcpSyncTranslator` BYOK engines; `mcp` SDK pruned (`python-multipart` now explicit) |

### 🚀 Asynchronous Batch Translation
- **BYOK Credentials Required**: Personal Google Cloud Translation v3 Service Account JSON, validated in-session (ADR 0004)
- **Rate Limiting**: Transient 429/500/503 errors retried with truncated exponential backoff and ±20% jitter
- **Memory Efficiency**: Designed for large documents; zero host PDF storage keeps instances lean
- **Fail-Closed Semantics**: Missing or rejected credentials raise `GcpSyncCredentialsRequiredError` — never silent source-text fallback
- **Error Resilience**: Partial layout-parsing failures (`failed_pages > 0`) are surfaced transparently with isolated re-run submissions
- **Configuration**: Fine-tune performance settings via environment variables for your specific use case

### Best Practices
- Start with default settings and adjust based on your GCP quotas and performance needs
- Monitor API usage in your own Google Cloud console (translation is billed to your project)
- Use progress callbacks for long-running operations to provide user feedback
- Test with smaller documents before processing large batches
- Use the dual-pane viewer to verify translations against the German original

## 📈 Performance Considerations

### Traditional Processing
- **Memory Usage**: Higher due to image rendering, managed with automatic garbage collection
- **Processing Time**: Longer for complex documents, with progress tracking
- **Quality**: Significantly improved formatting preservation
- **Scalability**: Designed for production use with proper resource management

### Performance Benchmarks (Historical — Lingo.dev Era)
The parallel-vs-sequential benchmark tables published in earlier revisions
were measured against the retired Lingo.dev parallel translation stack
(`ParallelTranslationService`/`EnhancedTranslationService`, deleted under
ADR 0004) and its third-party API latencies. They are retained only as
history and no longer describe this codebase.

Current performance characteristics ride on Google Cloud Document
Translation v3: synchronous preview calls for 1–3 sample pages and
asynchronous `batchTranslateDocument` LROs for full-length books, with
progress derived from LRO metadata (`translated_pages` / `total_pages` /
`failed_pages`). Measure your own workloads against your GCP project's
quotas and regional latency.

## 🤝 Contributing

See `CONTRIBUTING.md` for development workflow, lint/type-check configurations, pytest markers, and automated dependency updates (Dependabot). This ensures local and CI runs use the same rules and remain reproducible.
