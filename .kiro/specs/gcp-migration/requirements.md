# Requirements Specification: Google Cloud Document Translation & Neologism Orchestration

## 1. Overview & Book-Scale Scope

This specification defines the functional, non-functional, behavioral (BDD), and test-driven (TDD) requirements for PhenomenalLayout, focused on **full-length books and long-form philosophical manuscripts**.

The core system consists of:
1. Stream-based text extraction and neologism pre-scanning for large book PDFs.
2. Dual-tier glossary synchronization (persistent domain dictionaries + dynamic user overrides).
3. **Primary Default Pipeline: Asynchronous batch document translation (`batchTranslateDocument`) via Google Cloud Storage (GCS)**.
4. Live Long-Running Operation (LRO) progress monitoring for book translation jobs.
5. **Bring Your Own Key (BYOK) credential management** for user-billed GCP translation and storage with dual Translation & Storage validation.
6. **Zero Host Storage & 7-Day Staging Lifecycle**: Source and translated PDF files are stored strictly in the user's GCS bucket (with 7-day staging auto-expiration) or Google Drive; Modal backend stores zero book PDFs.
7. **Persistent user vocabulary storage** for remembering terminology decisions across sessions and books.
8. **Pre-auth zero-credential GCP cost & GCS storage retention estimator** providing an itemized quote within a $\pm \$5.00$ tolerance margin.
9. **Interactive GCP Onboarding Walkthrough Modal** guiding translators through setting up their GCP account, APIs, bucket, and service account key with auditable `gcloud` commands.
10. **Seamless Google Drive Export**: 1-click export via client-side Google Identity Services (GIS) OAuth (`drive.file` scope) with no third-party auth middleware (no Auth0 / no Clerk).
11. **Fraktur / Blackletter OCR Script Assessment**: Evaluates historical printings and outputs confidence ratings.
12. **Long Batch Job Recovery & Resumption**: Preserves LRO progress across browser disconnects and container scale-downs.
13. **Partial Page Failure Resilience & Fallback Plaintext Translation**: Translates unformatted raw text for complex skipped pages to produce a 98% layout-preserved, 100% translated book.
14. **Tier 2 Session Glossary Lifecycle & Quota Auto-Cleanup**: Prevents GCP project glossary bloat.
15. **Synchronized Side-by-Side Dual-Pane Reading Mode**: Bilingual reading environment for scholarly translation verification.
16. **Serverless deployment on Modal Labs** with scale-to-zero idle compute.

---

## 2. User Stories (US)

### US-01: Book-Scale Terminology Pre-Scanning
> **As a** translator working on a 300-page German philosophical book,  
> **I want** to upload the manuscript and get a complete, deduplicated inventory of coined compounds and philosophical terms mapped across chapters,  
> **So that** I can establish terminology decisions prior to full-book translation.

### US-02: Dual-Tier Glossary Synchronization & Management
> **As a** scholar,  
> **I want** the system to automatically synchronize our base philosophical dictionary with my custom book-specific term overrides into a Google Cloud Translation Glossary resource,  
> **So that** specialized terms (e.g. Klages' distinction of *Geist*, *Seele*, and *Biozentrik*) are translated consistently across every single page.

### US-03: Asynchronous Full-Book Batch Translation via GCS (Primary Default)
> **As a** user translating an entire book (50–1,000 pages),  
> **I want** the system to automatically stage the book in Google Cloud Storage, dispatch an asynchronous batch translation job, and track page-by-page progress,  
> **So that** the entire book is translated without timeouts while preserving all formatting, multi-column tables, diagrams, and footnotes.

### US-04: Real-Time Book Translation Progress Tracking
> **As a** user running a long batch translation job,  
> **I want** real-time progress indicators displaying completed pages and estimated time remaining,  
> **So that** I have full visibility into the background translation process.

### US-05: Bring Your Own Key (BYOK) Credentials & Project Isolation
> **As a** user accessing the web application,  
> **I want** to securely provide my own Google Cloud Project ID, GCS Bucket, and Service Account key,  
> **So that** all GCP translation and storage charges are billed directly to my personal GCP billing account while keeping my credentials strictly isolated.

### US-06: Persistent User Neologism Vocabulary Memory
> **As a** recurring translator translating multiple philosophical volumes,  
> **I want** my translation decisions (e.g. mapping *Schauung* or leaving *Dasein* untranslated) to be saved to my user profile on the persistent storage volume,  
> **So that** when I upload subsequent books, my previously chosen terminology is automatically pre-filled.

### US-07: Instant Pre-Auth GCP Translation & GCS Retention Cost Estimation
> **As a** prospective user visiting the website without signing in or supplying GCP credentials,  
> **I want** to upload my book PDF and receive an immediate, itemized GCP bill estimate (including document translation, 7-day staging lifecycle, and monthly GCS storage retention) within a $\pm \$5.00$ margin of error,  
> **So that** I know exactly how much budget to allocate in my Google Cloud billing account before setting up BYOK.

### US-08: Interactive GCP Setup Walkthrough Modal
> **As a** translator who is new to Google Cloud,  
> **I want** a step-by-step interactive onboarding modal in the web interface that guides me through creating a GCP account, enabling the Translation and Storage APIs, creating a bucket, and generating a Service Account JSON key with copyable `gcloud` commands,  
> **So that** I can configure my BYOK credentials without confusion or cloud friction.

### US-09: Seamless Personal Google Drive Export
> **As a** user who completed a book translation,  
> **I want** to click "Save to Google Drive" and authenticate with a simple Google popup to have the translated PDF saved directly into my personal Google Drive,  
> **So that** I can access my translated books anywhere without having to manually download large files to local storage or register for third-party auth platforms.

### US-10: Fraktur & Historical German OCR Script Assessment
> **As a** scholar translating an early 20th-century Fraktur / Gothic printed treatise,  
> **I want** the system to evaluate font characteristics and report an OCR Script Confidence Rating during pre-scanning,  
> **So that** I know whether my historical scan will produce clean translations or if I should test sample preview pages first.

### US-11: Long-Running Batch Job Recovery & Disconnect Resilience
> **As a** user translating an 800-page book taking 25 minutes,  
> **I want** to be able to close my laptop, leave the website, and reopen PhenomenalLayout later to find my translation progress still active,  
> **So that** browser disconnects or Modal container scale-downs never cancel or lose track of my GCP batch job.

### US-12: Fallback Plaintext Translation for Complex Skipped Pages
> **As a** translator whose book contains an ancient foldout chart or complex plate that GCP skipped during layout preservation,  
> **I want** a 1-click fallback option to translate the raw extracted text of those skipped pages without layout preservation,  
> **So that** I receive a 98% layout-preserved, 100% completely translated book with zero untranslated pages.

### US-13: Synchronized Side-by-Side Dual-Pane Reading Mode
> **As a** philosopher verifying a translated treatise,  
> **I want** an interactive side-by-side reading view showing the German original alongside the translated English page with synchronized scrolling and neologism highlighting,  
> **So that** I can closely compare and verify complex philosophical terminology in context.

---

## 3. Functional Requirements (FR) & BDD Scenarios

### FR-01: Stream-Based PDF Book Ingestion & Neologism Pre-Scanning
* **Description**: Ingest full book PDFs using stream-based chunking, scan text streams with [`NeologismDetector`](services/neologism_detector.py), and aggregate frequency and sentence context without loading high-resolution page bitmaps into memory.
* **Traceability**: US-01

#### BDD Scenario FR-01.1: Pre-Scan Full Book
```gherkin
Feature: Book Pre-Scanning
  Scenario: Stream-scan a 300-page book for philosophical compounds
    Given a 300-page German PDF "der_geist_als_widersacher.pdf"
    When the BookTranslationOrchestrator initiates pre-scanning
    Then text is streamed page by page with peak RAM remaining below 256MB
    And an aggregated NeologismAnalysis is returned containing unique compounds and their occurrences
```

---

### FR-02: Dual-Tier Glossary Synchronization Subsystem
* **Description**: The system must maintain persistent base glossaries (Tier 1) and dynamic book session glossaries (Tier 2). It must compile terms into RFC 4180 TSVs, upload them to GCS (`gs://<bucket>/glossaries/...`), and ensure a corresponding Cloud Translation v3 Glossary resource is created and in `READY` state.
* **Traceability**: US-02

#### BDD Scenario FR-02.1: Synchronize Dynamic Book Glossary to GCP
```gherkin
Feature: Dual-Tier Glossary Sync
  Scenario: Provision book session glossary overlaying base dictionary
    Given a base dictionary with 120 Klages terms
    And 25 book-specific user choices recorded in session "book-sess-42"
    When the GlossarySyncManager compiles and provisions the glossary in region "us-central1"
    Then a combined TSV is uploaded to "gs://user-bucket/glossaries/sessions/book-sess-42.tsv"
    And Cloud Translation create_glossary LRO completes successfully
    And the active glossary resource URI "projects/p1/locations/us-central1/glossaries/book-sess-42" is returned
```

---

### FR-03: Primary Default Pipeline: GCS Asynchronous Batch Translation
* **Description**: Default document translation pipeline must upload the source book PDF to GCS (`gs://<bucket>/inputs/<book_id>/source.pdf`), trigger `batchTranslateDocument` with attached glossary resource, and designate output prefix (`gs://<bucket>/outputs/<book_id>/`).
* **Traceability**: US-03

#### BDD Scenario FR-03.1: Submit Full-Book Batch Translation Job
```gherkin
Feature: GCS Batch Document Translation
  Scenario: Dispatch asynchronous batch job for 300-page book
    Given a book PDF staged at "gs://user-bucket/inputs/book-101/source.pdf"
    And an active glossary resource "projects/p1/locations/us-central1/glossaries/book-sess-42"
    When the orchestrator submits batch_translate_document
    Then an asynchronous Long Running Operation (LRO) is created
    And the job state transitions to "RUNNING"
```

---

### FR-04: Batch Job Monitoring & Progress Polling
* **Description**: The system must poll the GCP Translation LRO operation every $N$ seconds, extract `translated_pages`, `total_pages`, and `failed_pages` metadata, and publish progress updates to the UI.
* **Traceability**: US-04

#### BDD Scenario FR-04.1: Track LRO Progress to Completion
```gherkin
Feature: Batch Translation LRO Monitoring
  Scenario: Poll batch translation progress until completion
    Given an active batch translation LRO "projects/p1/locations/us-central1/operations/op-99"
    When the progress monitor polls the operation
    Then progress metadata is emitted (e.g. 150/300 pages translated)
    And when the LRO reaches state "SUCCEEDED", the translated PDF is located in GCS outputs
    And output PDF page count is verified to equal 300
```

---

### FR-05: Bring Your Own Key (BYOK) Credentials Vault & Dual-Service Validation
* **Description**: The web interface must provide a BYOK configuration panel where users provide GCP Project ID, GCS Bucket Name, and Service Account JSON credentials. The backend validates BOTH: (1) Translation API access via `projects.locations.glossaries.list` in `us-central1`, and (2) GCS bucket accessibility, object operations, and lifecycle update permissions via `storage_client.get_bucket(bucket_name)` and `bucket.test_iam_permissions(['storage.objects.create', 'storage.objects.get', 'storage.objects.delete', 'storage.buckets.get', 'storage.buckets.update'])`.
* **Traceability**: US-05

#### BDD Scenario FR-05.1: Validate and Bind User GCP Credentials
```gherkin
Feature: BYOK Credentials Management
  Scenario: Validate user Service Account with dual Translation & Storage checks
    Given a user "translator-01" provides a Service Account JSON for project "my-gcp-proj" and bucket "my-trans-bucket"
    When the BYOKCredentialsManager validates the credentials
    Then Translation API connectivity check succeeds via list_glossaries
    And Storage bucket permission check succeeds for "my-trans-bucket" including bucket-level update permissions
    And validate_credentials returns status VALID
    And the credentials are bound strictly to "translator-01" session context
    And no credential secrets are written to disk or logs
```

---

### FR-06: Persistent User Neologism Vocabulary Store
* **Description**: The system must persist user translation choices (translated equivalents, contextual notes, or "keep untranslated" directives) to a persistent storage volume (`modal.Volume`). When a user pre-scans a new book, the engine automatically matches and pre-fills terms from their personal vocabulary.
* **Traceability**: US-06

#### BDD Scenario FR-06.1: Recall User Vocabulary for New Book Pre-Scan
```gherkin
Feature: User Vocabulary Persistence
  Scenario: Auto-populate terminology choices from user history
    Given user "translator-01" has previously saved term "Schauung" -> "Intuitive Vision"
    When user "translator-01" uploads a new book containing "Schauung"
    Then the Neologism Pre-Scanner recognizes "Schauung" from the user vocabulary
    And the review table pre-selects "Intuitive Vision" with high confidence
```

---

### FR-07: Pre-Auth Zero-Credential Cost & GCS Retention Estimator
* **Description**: The application must provide a publicly accessible endpoint and UI widget allowing users to upload a PDF without signing in or providing GCP credentials, computing page-level counts and emitting an itemized GCP billing estimate with:
  1. Base Document Translation cost ($0.080/page).
  2. GCS 7-day staging lifecycle overhead and Always Free 5 GB Tier eligibility check.
  3. 1-month and 12-month GCS storage retention schedule.
  4. Total variance strictly within $\pm \$5.00$.
* **Traceability**: US-07

#### BDD Scenario FR-07.1: Calculate Zero-Auth Translation & Storage Quote
```gherkin
Feature: Pre-Auth Cost & Storage Estimation
  Scenario: Generate itemized quote for a 350-page PDF with GCS retention
    Given an unauthenticated user uploads a 350-page PDF "klages_der_mensch.pdf" (12MB)
    When the GCPCostEstimator analyzes the document
    Then the calculated base translation cost is $28.00 (350 * $0.080)
    And 7-day GCS staging storage is estimated as $0.00 (Covered by GCP Always Free 5GB Tier)
    And the total quote is returned as $28.00 with tolerance range "$28.00 - $28.50"
    And the estimation completes in less than 1.0 second on Modal CPU
```

---

### FR-08: Interactive GCP Setup Walkthrough Modal
* **Description**: The web application must include an interactive guided modal dialog ("Step-by-Step GCP Setup Guide") containing 6 progressive steps: (1) Account creation & free credit claim, (2) Project creation, (3) Enabling Translation & Storage APIs, (4) Creating a GCS Bucket in `us-central1`, (5) Creating a Service Account with `roles/cloudtranslate.editor` and `roles/storage.admin` on the bucket and downloading JSON key, and (6) Drag-and-drop credential validation. Also includes explicit, auditable copyable `gcloud` setup commands.
* **Traceability**: US-08

---

### FR-09: Seamless Personal Google Drive Export Subsystem
* **Description**: The application must integrate client-side **Google Identity Services (GIS)** OAuth 2.0. When a user clicks "Save to Google Drive", a native Google OAuth popup requests permission for scope `https://www.googleapis.com/auth/drive.file`. Upon authorization, the translated PDF is streamed directly from the user's GCS bucket to Google Drive v3 API (`files.create`) without requiring third-party authentication middleware (no Auth0 / no Clerk) and without saving the file on the Modal backend.
* **Traceability**: US-09

#### BDD Scenario FR-09.1: Export Translated Book to Google Drive via GIS
```gherkin
Feature: Google Drive Export
  Scenario: 1-Click export to personal Google Drive
    Given a completed translation in "gs://user-bucket/outputs/book-101/source_de_en.pdf"
    When the user clicks "Save to Google Drive" and approves the GIS OAuth prompt (drive.file)
    Then the translated PDF is streamed to Google Drive v3 API
    And the file is created in the user's Google Drive root or "PhenomenalLayout Translations" folder
    And the direct Google Drive file link is returned to the user
    And zero book PDF bytes are stored on the Modal backend disk
```

---

### FR-10: Zero Host PDF Storage Invariant & 7-Day GCS Staging Lifecycle
* **Description**: Modal Labs backend containers and persistent volumes must never store full-length source or translated PDF files. All PDF storage is strictly isolated to the user's GCS bucket and personal Google Drive. Staged input objects in `gs://<bucket>/inputs/...` must have a 7-day auto-deletion lifecycle policy. Modal Volume storage is restricted strictly to lightweight user vocabulary and metadata databases ($\le 5\text{MB}$).
* **Traceability**: US-03, US-05, US-07, US-09

---

### FR-11: Historical German OCR & Fraktur Script Classifier
* **Description**: During pre-scan, inspect font descriptors and Fraktur unicode patterns to emit a `ScriptAnalysisResult` with `script_type` (`Antiqua` vs. `Fraktur` vs. `Hybrid`) and `ocr_confidence_score` ($0.0–1.0$). If score $< 0.85$, prompt translator to review sample preview pages.
* **Traceability**: US-10

#### BDD Scenario FR-11.1: Detect Fraktur Font in Historical Treatise
```gherkin
Feature: Fraktur Script Classification
  Scenario: Analyze 1929 Fraktur edition of Klages
    Given a scanned PDF of Klages' 1929 edition containing long-s (ſ) ligatures
    When FrakturClassifier evaluates the document stream
    Then script_type is detected as "Fraktur"
    And ocr_confidence_score is calculated as 0.88
    And a prompt recommends "Preview 2 sample pages before full batch"
```

---

### FR-12: Long-Running Batch Job Recovery & Resumption
* **Description**: Persist active GCP LRO Operation metadata, session ID, user ID, and GCS output path to `/data/sessions/{user_id}_{book_id}.json`. When a user reconnects, restore active LRO monitoring without restarting or abandoning running cloud jobs.
* **Traceability**: US-11

#### BDD Scenario FR-12.1: Re-attach to Long-Running LRO After Browser Reconnect
```gherkin
Feature: Job Resumption
  Scenario: User reconnects while 800-page job is in progress
    Given user "translator-01" dispatched an 800-page batch job with LRO "operations/op-789"
    And user closed browser tab and Modal container scaled to zero
    When user re-opens PhenomenalLayout with session "book-sess-800"
    Then the active job is recalled from "/data/sessions/translator-01_book-sess-800.json"
    And the UI live progress bar instantly displays current progress (e.g. 520/800 pages)
```

---

### FR-13: Partial Page Failure Resilience & Fallback Plaintext Translation
* **Description**: When GCP Document Translation completes with `metadata.failed_pages > 0`, extract the text content of the failed page indices, translate them via Cloud Translation Text API v3 using the active glossary, and stitch them back into the final document, delivering a 98% layout-preserved, 100% translated book.
* **Traceability**: US-12

#### BDD Scenario FR-13.1: Fallback Raw Translation for Skipped Plate Page
```gherkin
Feature: Fallback Page Translation
  Scenario: Translate skipped diagram page as raw text
    Given a 500-page book where Page 214 failed complex layout parsing (failed_pages = 1)
    When the user triggers "Translate Failed Pages as Raw Text"
    Then raw text from Page 214 is extracted and translated via Cloud Translation Text v3
    And the translated text page replaces the placeholder in the output PDF
    And the final PDF contains 500 fully translated pages (499 layout-preserved + 1 plaintext-translated)
```

---

### FR-14: Tier 2 Session Glossary Lifecycle & GCP Quota Auto-Cleanup
* **Description**: Automatically register cleanup triggers upon job completion to prune dynamic book session glossaries from Google Cloud Translation and delete temporary TSV files in GCS, keeping project glossary count under the regional 1,000 quota.
* **Traceability**: US-02

---

### FR-15: Synchronized Side-by-Side Dual-Pane Reading Mode
* **Description**: Render an embedded bilingual reading view displaying the original German scan on the left and the translated English layout PDF on the right with synchronized page turns and neologism highlighting.
* **Traceability**: US-13

---

### FR-16: Single-Page Rapid Preview Translation (Secondary Mode)
* **Description**: Allow translators to test translation quality on 1–3 sample pages using synchronous `translateDocument` with `enableShadowRemovalNativePdf=True` using their BYOK credentials before committing to a full book batch run.
* **Traceability**: US-01, US-02, US-05, US-10

---

### FR-17: Modal Labs Serverless Web Deployment & Scale-to-Zero
* **Description**: The application must be deployable as a serverless ASGI/WSGI web app on Modal Labs (`modal_app.py`). When no requests or batch monitoring jobs are active, the container scales to zero.
* **Traceability**: US-01 to US-13

---

## 4. Non-Functional Requirements (NFR)

| ID | Category | Requirement Description | Metric / Standard |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **Scalability** | Batch pipeline must support translating long books up to 1,000 pages without memory starvation. | Peak RAM usage $\le 256\text{ MB}$; streaming file handling. |
| **NFR-02** | **Reliability** | Long-running operation polling, GCS downloads, and Drive uploads must recover from transient network disconnects. | Exponential backoff retry with up to 5 attempts. |
| **NFR-03** | **Security & Privacy** | Zero credential leaks: BYOK credentials held strictly in encrypted session memory. Google Drive OAuth uses restricted `drive.file` scope. | Zero credentials stored on disk; zero access to unrelated user Drive files. |
| **NFR-04** | **Glossary Consistency** | 100% of defined glossary terms must be supplied in compliant UTF-8 TSV format. | Zero TSV syntax errors; validation pass prior to GCS upload. |
| **NFR-05** | **Cost Efficiency** | Host compute must remain within Modal Labs' $30/month free tier with near-zero idle cost. | Scaledown window $\le 300\text{s}$; zero GPU requirement for host. |
| **NFR-06** | **Cost Precision** | Pre-auth cost estimate must deviate from actual GCP bill by no more than \$5.00. | Estimate variance $\le \pm \$5.00$ per document. |
| **NFR-07** | **Zero Host Storage** | Modal persistent storage is restricted to user metadata; zero book PDF bytes stored on host disk. Staged GCS inputs auto-expire after 7 days. | Host PDF disk usage $= 0\text{ MB}$ persistent. |
| **NFR-08** | **Job Resumption Time**| Reconnecting to an active cloud batch job must take less than 1.0 second. | Session restoration latency $\le 1000\text{ms}$. |
| **NFR-09** | **Test Coverage** | All services, classifiers, recovery managers, and translators must be covered by automated tests. | $\ge 90\%$ line and branch coverage. |
| **NFR-10** | **TDD 3-Strike Gate** | All feature development must follow strict TDD sequences with a 3-strike fail-safe abort. | Test pass rate must not fall below $90\%$ across 3 consecutive loops. |
| **NFR-11** | **Onboarding Usability**| Walkthrough modal must enable non-technical users to complete GCP credential creation in under 5 minutes. | 6 clear steps with visual instructions and direct Google Cloud Console links. |

---

## 5. Traceability Matrix

| User Story | Functional Requirement | Non-Functional Requirement | Test Target |
| :--- | :--- | :--- | :--- |
| **US-01** | FR-01, FR-16 | NFR-01 | `tests/test_book_pre_scanner.py` |
| **US-02** | FR-02, FR-14 | NFR-03, NFR-04 | `tests/test_glossary_sync_manager.py` |
| **US-03** | FR-03, FR-04, FR-10 | NFR-01, NFR-02, NFR-07, NFR-09 | `tests/test_gcp_batch_translation_service.py` |
| **US-04** | FR-04 | NFR-02 | `tests/test_lro_progress_monitor.py` |
| **US-05** | FR-05, FR-17 | NFR-03, NFR-05 | `tests/test_byok_credentials_manager.py` |
| **US-06** | FR-06 | NFR-03, NFR-09 | `tests/test_user_vocabulary_store.py` |
| **US-07** | FR-07, FR-10 | NFR-05, NFR-06, NFR-07 | `tests/test_cost_estimator.py` |
| **US-08** | FR-08 | NFR-11 | `tests/test_app_routes.py` |
| **US-09** | FR-09, FR-10 | NFR-03, NFR-07, NFR-09 | `tests/test_google_drive_exporter.py` |
| **US-10** | FR-11 | NFR-01, NFR-09 | `tests/test_fraktur_classifier.py` |
| **US-11** | FR-12 | NFR-02, NFR-08 | `tests/test_batch_job_recovery.py` |
| **US-12** | FR-13 | NFR-02, NFR-09 | `tests/test_fallback_translator.py` |
| **US-13** | FR-15 | NFR-05, NFR-09 | `tests/test_dual_pane_viewer.py` |
| **All** | FR-01 to FR-17 | NFR-09, NFR-10, NFR-11 | `tests/test_book_translation_e2e.py` |
