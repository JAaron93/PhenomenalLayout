# Implementation Tasks: Google Cloud Document Translation & Neologism Orchestration

## 1. Plan Overview & Book-Scale Execution Strategy

This implementation plan decomposes the requirements from [`requirements.md`](.kiro/specs/gcp-migration/requirements.md) into concrete, test-driven work packages tailored for **full-length book translation** with **Asynchronous GCS Batch Translation as the primary default**, deployed on **Modal Labs** under a **Bring Your Own Key (BYOK)** model with **Pre-Auth Cost & Storage Estimation**, **Zero Host Storage**, **Seamless Google Drive Export**, and **Scholarly Resilience Enhancements**.

The tasks are organized into five **Execution Tracks**:
* **Track 1: GCP Batch Translation Engine, BYOK & Exporters** (Primary pipeline, auth vault, quote engine & Drive exporter)
* **Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store** (Vocabulary memory, TSV compilation & quota cleanup)
* **Track 3: Scholarly Resilience, Fraktur OCR & Failure Fallbacks** (Historical German OCR rating, job recovery, plaintext fallback & dual-pane viewer)
* **Track 4: Deprecation & Codebase Streamlining** (Independent cleanup of legacy canvas engines)
* **Track 5: Book Orchestrator, Modal Deployment, UI & E2E Validation** (Integration, UI and comprehensive test suite)

---

## 2. Track Breakdown & Parallelism Map

```
┌────────────────────────────────────────────────────────────────────────┐
│ Track 1: GCP Batch Translation Engine, BYOK & Exporters                │
│ [Task 1.1: Config & Deps] ──> [Task 1.2: BYOK Credentials Manager]    │
│                           ──> [Task 1.3: GCS Batch Service]            │
│                           ──> [Task 1.4: LRO Progress Monitor]         │
│                           ──> [Task 1.5: Pre-Auth Cost & Storage Est]  │
│                           ──> [Task 1.6: Google Drive Exporter (GIS)]  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store    │
│ [Task 2.1: User Vocabulary Store] ──> [Task 2.2: TSV Compiler]        │
│                                   ──> [Task 2.3: Glossary Sync Mgr]    │
│                                   ──> [Task 2.4: Quota Auto-Cleanup]   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 3: Scholarly Resilience, Fraktur OCR & Failure Fallbacks         │
│ [Task 3.1: Fraktur Script Classifier]                                  │
│ [Task 3.2: Batch Job Recovery Manager]                                 │
│ [Task 3.3: Fallback Plaintext Page Translator]                         │
│ [Task 3.4: Dual-Pane Viewer Controller]                                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 4: Codebase Streamlining & Redundant Engine Deprecation          │
│ [Task 4.1: Deprecate Canvas Reconstructor & Legacy Heuristics]        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 5: Book Orchestrator, Modal Deployment, UI & E2E Validation      │
│ [Task 5.1: Book Orchestrator] ──> [Task 5.2: UI with Dual-Pane & Auth] │
│                               ──> [Task 5.3: Modal App Scaffolding]    │
│                               ──> [Task 5.4: Full-Book E2E Test Suite] │
└────────────────────────────────────────────────────────────────────────┘
```

> [!TIP] PARALLEL EXECUTION
> **Track 1** (GCP Batch Translation, BYOK Vault & Drive Exporter), **Track 2** (User Vocabulary Store & Glossary Sync), and **Track 3** (Fraktur Classifier & Fallback Translator) are decoupled and can be built and tested concurrently.

---

## 3. Detailed Task Specifications

### Track 1: GCP Batch Translation Engine, BYOK & Exporters

#### Task 1.1: Configure Dependencies and Environment Defaults
* **ID**: `TASK-1.1`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-03, NFR-03
* **Dependencies**: None
* **Description**:
  Add `google-cloud-translate>=3.15.0`, `google-cloud-storage>=2.14.0`, `google-api-python-client>=2.120.0`, and `modal>=0.60.0` to `requirements.txt`. Add configuration dataclasses in `config/settings.py` for default GCP locations (`us-central1`), pricing constants (`$0.080/page`, `$0.020/GB/mo`, 5GB free tier, 7-day staging lifecycle), poll intervals, and Modal volume paths (`/data`).
* **Acceptance Criteria (TDD)**:
  * Unit test verifies settings dataclasses load defaults cleanly without requiring hardcoded secrets in the environment.

---

#### Task 1.2: Implement `BYOKCredentialsManager` with Dual-Service Validation & Walkthrough Guide
* **ID**: `TASK-1.2`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-05, FR-08, NFR-03, NFR-05, NFR-11
* **Dependencies**: `TASK-1.1`
* **Description**:
  Develop [`services/byok_credentials_manager.py`](services/byok_credentials_manager.py):
  1. `set_credentials(user_id: str, project_id: str, bucket_name: str, sa_json_content: str | dict) -> bool`: Ingests and binds user GCP credentials in session memory.
  2. `validate_credentials(user_id: str) -> ValidationResult`: Performs comprehensive dual-service non-billable validation:
     * Validates Translation API access via `projects.locations.glossaries.list` in `us-central1`.
     * Validates GCS bucket accessibility, object CRUD permissions, and lifecycle configuration authority via `storage_client.get_bucket(bucket_name)` and `bucket.test_iam_permissions(['storage.objects.create', 'storage.objects.get', 'storage.objects.delete', 'storage.buckets.get', 'storage.buckets.update'])`.
     * Returns `status=VALID` only if **both** Translation and Storage permissions succeed; otherwise returns granular actionable error details.
  3. `get_translation_client(user_id: str) -> TranslationServiceClient`: Returns authenticated Google Cloud Translation v3 client.
  4. `get_storage_client(user_id: str) -> StorageClient`: Returns authenticated Google Cloud Storage client.
  5. `get_onboarding_guide() -> list[GuideStep]`: Returns structured 6-step walkthrough data with direct GCP console links and copyable, auditable `gcloud` setup commands (specifying `roles/storage.admin` on the bucket).
  6. `clear_credentials(user_id: str) -> None`: Evicts session credentials.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Validate user Service Account credentials with dual checks
    Given valid Service Account JSON for project "my-gcp-project" and bucket "my-trans-bucket"
    When BYOKCredentialsManager.set_credentials is called for user "user-1"
    Then validate_credentials verifies Translation glossary listing and Storage bucket IAM (including lifecycle update permissions)
    And returns status VALID with confirmed bucket access
    And credentials are never written to disk or logs
  ```
  * Test suite: `tests/test_byok_credentials_manager.py` with mock Google Auth, Translation, and Storage clients ($\ge 90\%$ coverage).

---

#### Task 1.3: Implement `GCPBatchTranslationService` (Zero Host Storage & 7-Day Staging Lifecycle)
* **ID**: `TASK-1.3`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-03, FR-10, NFR-01, NFR-02, NFR-07
* **Dependencies**: `TASK-1.2`
* **Description**:
  Develop [`services/gcp_batch_translation_service.py`](services/gcp_batch_translation_service.py):
  1. `upload_book_to_gcs(user_id: str, local_pdf_path_or_stream, gcs_destination_uri: str) -> str`: Streams PDF directly to user's GCS bucket without caching on host disk.
  2. `ensure_staging_lifecycle_policy(user_id: str, bucket_name: str, staging_prefix: str = "inputs/", age_days: int = 7) -> bool`: Specifically inspects bucket lifecycle rules for a rule matching `action.type == "Delete"` and `condition.matches_prefix == [staging_prefix]`. If no rule covering `staging_prefix` exists, appends/merges the prefix-scoped 7-day auto-delete rule into the bucket's existing lifecycle rule list and patches the bucket metadata.
  3. `submit_batch_job(user_id: str, gcs_input_uri: str, gcs_output_uri_prefix: str, source_lang: str, target_lang: str, glossary_resource_name: str) -> str`: Dispatches `batch_translate_document` and returns LRO operation name.
  4. `stream_translated_book(user_id: str, gcs_output_uri: str) -> BinaryIO`: Returns non-blocking stream directly from user GCS bucket.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Dispatch full-book batch translation request and verify lifecycle rule
    Given a source book at "gs://user-bucket/inputs/book_1/source.pdf"
    And glossary "projects/user-p1/locations/us-central1/glossaries/klages_glossary"
    When submit_batch_job is called for user "user-1"
    Then ensure_staging_lifecycle_policy verifies or appends the prefix-scoped 7-day auto-delete rule on "inputs/"
    And batch_translate_document is invoked with GcsSource and GcsDestination
    And the returned LRO operation name is stored
  ```
  * Test suite: `tests/test_gcp_batch_translation_service.py` with mock GCS and Translation client ($\ge 90\%$ coverage).

---

#### Task 1.4: Implement `LROProgressMonitor`
* **ID**: `TASK-1.4`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-04, NFR-02
* **Dependencies**: `TASK-1.3`
* **Description**:
  Develop [`services/lro_progress_monitor.py`](services/lro_progress_monitor.py) to poll LRO operations via `TranslationServiceClient.get_operation`, parse `BatchTranslateDocumentMetadata` (`total_pages`, `translated_pages`, `failed_pages`, `state`), and compute completion percentage and remaining time estimates.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies accurate progress calculation from mock LRO metadata states (`RUNNING`, `SUCCEEDED`, `FAILED`) and `translated_pages` count.

---

#### Task 1.5: Implement Pre-Auth `GCPCostEstimator` with GCS 7-Day Staging & Retention Schedules
* **ID**: `TASK-1.5`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-07, NFR-06
* **Dependencies**: `TASK-1.1`
* **Description**:
  Develop [`services/cost_estimator.py`](services/cost_estimator.py):
  1. `estimate_book_cost(pdf_path_or_bytes: Path | bytes) -> CostQuote`: Inspects PDF page count, file size, and text density without requiring user authentication or GCP credentials.
  2. Computes itemized pricing:
     - Document Translation ($0.080/page).
     - 7-Day GCS Staging lifecycle overhead.
     - GCS Always Free 5 GB Tier eligibility check.
     - 1-Month and 12-Month GCS storage retention schedule ($0.020/GB/mo Standard, $0.0012/GB/mo Archive).
  3. Returns `CostQuote` dataclass with `total_pages`, `base_cost`, `staging_overhead_cost`, `storage_cost_1mo`, `storage_cost_12mo`, `free_tier_covered`, `total_estimate`, and `tolerance_range` ($\pm \$5.00$).
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Estimate translation & storage costs for 350-page book
    Given a 350-page PDF file (15MB)
    When estimate_book_cost is called
    Then base cost is $28.00 ($0.080 * 350)
    And 7-day staging and 1-month GCS storage are estimated as $0.00 (under 5GB Free Tier)
    And total quote is within $28.00 - $28.50
  ```
  * Test suite: `tests/test_cost_estimator.py` ($\ge 90\%$ coverage).

---

#### Task 1.6: Implement `GoogleDriveExporter` (Google Identity Services GIS)
* **ID**: `TASK-1.6`
* **Status**: `[COMPLETED]`
* **Traceability**: FR-09, FR-10, NFR-03, NFR-07, NFR-09
* **Dependencies**: `TASK-1.1`
* **Description**:
  Develop [`services/google_drive_exporter.py`](services/google_drive_exporter.py):
  1. `export_stream_to_drive(access_token: str, file_stream: BinaryIO, filename: str, mime_type: str = "application/pdf") -> DriveExportResult`: Streams PDF directly into the user's Google Drive via Drive v3 API `files.create` using the client's `drive.file` scoped token.
  2. Zero temporary files on host disk: Uses non-blocking streaming pipes.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Stream translated PDF to Google Drive
    Given a valid GIS OAuth access token with scope "drive.file"
    When export_stream_to_drive is called with PDF stream
    Then Drive v3 multipart upload creates the file in the user's Drive
    And the returned result contains the file ID and webViewLink
    And zero PDF bytes are written to host disk
  ```
  * Test suite: `tests/test_google_drive_exporter.py` with mock Google Drive v3 API ($\ge 90\%$ coverage).

---

### Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store

#### Task 2.1: Implement `UserVocabularyStore` (Persistent Memory)
* **ID**: `TASK-2.1`
* **Traceability**: FR-06, NFR-03, NFR-09
* **Dependencies**: None
* **Description**:
  Develop [`services/user_vocabulary_store.py`](services/user_vocabulary_store.py) to manage user-specific terminology dictionaries stored persistently on Modal Volume (`/data/user_vocabularies/{user_id}.sqlite` or `.json`):
  1. `get_user_preferences(user_id: str) -> dict[str, TermPreference]`: Loads user's saved translations.
  2. `save_preference(user_id: str, german_term: str, preferred_translation: str, notes: str)`: Persists user choice.
  3. `bulk_save_preferences(user_id: str, preferences: dict)`: Batch update after book review.
  4. `export_tsv(user_id: str) -> bytes`: Exports personal dictionary.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_user_vocabulary_store.py` verifying persistence, retrieval, and concurrent read/write safety.

---

#### Task 2.2: Implement RFC 4180 Glossary TSV Compiler
* **ID**: `TASK-2.2`
* **Traceability**: FR-02, NFR-04
* **Dependencies**: `TASK-2.1`
* **Description**:
  Create [`services/glossary_compiler.py`](services/glossary_compiler.py) to combine:
  1. Base philosophical terms ([`config/klages_terminology.json`](config/klages_terminology.json)).
  2. User's persistent vocabulary ([`UserVocabularyStore`](services/user_vocabulary_store.py)).
  3. Current book session overrides.
  Produces strictly formatted RFC 4180 TSV bytes with header `de\ten`.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_glossary_compiler.py` verifying TSV encoding, quote escaping, deduplication, and priority overrides (Book Override > User Vocabulary > Base Dictionary).

---

#### Task 2.3: Implement `GlossarySyncManager`
* **ID**: `TASK-2.3`
* **Traceability**: FR-02, FR-06, NFR-04
* **Dependencies**: `TASK-1.2`, `TASK-2.2`
* **Description**:
  Develop [`services/glossary_sync_manager.py`](services/glossary_sync_manager.py):
  1. `sync_base_glossary(user_id)`: Provisions persistent Tier 1 base glossary if not already active in user's GCP region.
  2. `sync_book_session_glossary(user_id, session_id, user_choices)`: Uploads combined TSV to `gs://<user_bucket>/glossaries/sessions/<session_id>.tsv`, invokes `create_glossary`, polls until `READY`, and returns glossary resource name.
* **Acceptance Criteria (TDD & BDD)**:
  * Test suite: `tests/test_glossary_sync_manager.py` with mock GCP Translation client.

---

#### Task 2.4: Implement `SessionGlossaryLifecycleManager` (GCP Quota Auto-Cleanup)
* **ID**: `TASK-2.4`
* **Traceability**: FR-14, NFR-03
* **Dependencies**: `TASK-2.3`
* **Description**:
  Develop [`services/session_glossary_lifecycle.py`](services/session_glossary_lifecycle.py):
  1. `register_session_glossary(user_id, session_id, glossary_resource_name, gcs_tsv_uri)`: Tracks active transient session glossaries.
  2. `cleanup_session_glossary(user_id, session_id)`: Invokes non-blocking GCP `delete_glossary` and deletes GCS TSV once a batch job is complete or expired.
  3. `audit_project_glossaries(user_id)`: Verifies user GCP project glossary count remains well below the 1,000 regional quota.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_session_glossary_lifecycle.py` ($\ge 90\%$ coverage).

---

### Track 3: Scholarly Resilience, Fraktur OCR & Failure Fallbacks

#### Task 3.1: Implement `FrakturClassifier` (OCR Script Confidence Rating)
* **ID**: `TASK-3.1`
* **Traceability**: FR-11, NFR-01, NFR-09
* **Dependencies**: None
* **Description**:
  Develop [`services/fraktur_classifier.py`](services/fraktur_classifier.py):
  1. `classify_script(pdf_path_or_stream) -> ScriptAnalysisResult`: Analyzes font metadata, Unicode Fraktur ligature patterns (`ſ`, `tz`, `ch`, `ck`), and histogram features.
  2. `get_ocr_confidence_rating(pdf_path) -> OCRConfidence`: Computes confidence score ($0.0–1.0$) and emits recommendations (e.g. "Recommend 2 sample preview pages" if score $< 0.85$).
* **Acceptance Criteria (TDD & BDD)**:
  * Test suite: `tests/test_fraktur_classifier.py` with sample Antiqua and Fraktur documents ($\ge 90\%$ coverage).

---

#### Task 3.2: Implement `BatchJobRecoveryManager` (Job Resumption)
* **ID**: `TASK-3.2`
* **Traceability**: FR-12, NFR-02, NFR-08
* **Dependencies**: `TASK-1.4`
* **Description**:
  Develop [`services/batch_job_recovery.py`](services/batch_job_recovery.py):
  1. `save_active_job(user_id, session_id, book_id, lro_name, gcs_output_uri)`: Stores active job metadata to `/data/sessions/{user_id}_{book_id}.json`.
  2. `resume_active_job(session_id)`: Recalls state and re-attaches to live GCP LRO polling.
  3. `list_active_jobs(user_id)`: Lists pending jobs for reconnecting users.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_batch_job_recovery.py` ($\ge 90\%$ coverage).

---

#### Task 3.3: Implement `FallbackPageTranslator` (Raw Text Fallback for Complex Skipped Pages)
* **ID**: `TASK-3.3`
* **Traceability**: FR-13, NFR-02, NFR-09
* **Dependencies**: `TASK-1.3`
* **Description**:
  Develop [`services/fallback_translator.py`](services/fallback_translator.py):
  1. `extract_failed_pages_text(source_pdf_stream, failed_page_indices: list[int]) -> list[PageText]`: Extracts raw unformatted text from skipped/failed pages.
  2. `translate_failed_pages(user_id, pages_text, glossary_name) -> list[TranslatedPage]`: Translates raw text using Cloud Translation Text v3 with the session glossary.
  3. `splice_fallback_pages(layout_pdf_stream, translated_fallback_pages) -> BinaryIO`: Injects translated plaintext pages into the final output PDF to achieve a 98% layout-preserved, 100% translated book.
* **Acceptance Criteria (TDD & BDD)**:
  * Test suite: `tests/test_fallback_translator.py` ($\ge 90\%$ coverage).

---

#### Task 3.4: Implement `DualPaneViewerController` (Side-by-Side Reading Mode)
* **ID**: `TASK-3.4`
* **Traceability**: FR-15, NFR-05, NFR-09
* **Dependencies**: None
* **Description**:
  Develop [`services/dual_pane_viewer.py`](services/dual_pane_viewer.py):
  1. `get_bilingual_page_pair(german_pdf_stream, english_pdf_stream, page_number) -> BilingualPagePair`: Serves synchronized German/English page images for web rendering.
  2. `search_term_across_panes(german_term, english_term, page_number) -> HighlightCoordinates`: Highlights corresponding neologism locations in both panes.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_dual_pane_viewer.py` ($\ge 90\%$ coverage).

---

### Track 4: Codebase Streamlining & Deprecation

#### Task 4.1: Deprecate Legacy Heuristic Layout & Canvas Modules
* **ID**: `TASK-4.1`
* **Traceability**: Architecture Cleanup
* **Dependencies**: None
* **Description**:
  Deprecate and remove redundant legacy modules:
  * Delete `services/pdf_document_reconstructor.py`.
  * Delete `services/dolphin_client.py` and `services/dolphin_modal_service.py`.
  * Retire `core/dynamic_layout_engine.py` and `core/dynamic_programming.py`.
  * Clean up `requirements.txt` of unused heavy dependencies.
* **Acceptance Criteria (TDD)**:
  * Verify full test suite runs without broken legacy imports.

---

### Track 5: Book Orchestrator, Modal Deployment, UI & E2E Validation

#### Task 5.1: Build `BookTranslationOrchestrator`
* **ID**: `TASK-5.1`
* **Traceability**: FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-10 to FR-14
* **Dependencies**: `TASK-1.3`, `TASK-1.4`, `TASK-2.3`, `TASK-2.4`, `TASK-3.1` to `TASK-3.3`, `TASK-4.1`
* **Description**:
  Develop [`services/book_translation_orchestrator.py`](services/book_translation_orchestrator.py) integrating the end-to-end book workflow:
  1. Pre-scan book stream for neologisms and Fraktur script confidence, cross-referencing `UserVocabularyStore`.
  2. Present pre-filled terminology table in UI.
  3. Trigger glossary synchronization and dispatch batch translation to user's GCS bucket.
  4. Track LRO with `BatchJobRecoveryManager`.
  5. If `failed_pages > 0`, offer `FallbackPageTranslator` for 100% complete translation.
  6. Trigger `SessionGlossaryLifecycleManager` cleanup upon job completion.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_book_translation_orchestrator.py`.

---

#### Task 5.2: Update UI with BYOK Panel, Dual-Pane Viewer, Google Drive & Cost Quote
* **ID**: `TASK-5.2`
* **Traceability**: US-01 to US-13, FR-05, FR-07, FR-08, FR-09, FR-11, FR-15
* **Dependencies**: `TASK-1.2`, `TASK-1.5`, `TASK-1.6`, `TASK-3.1`, `TASK-3.4`, `TASK-5.1`
* **Description**:
  Update [`app.py`](app.py) and [`api/routes.py`](api/routes.py):
  1. **Zero-Auth Cost Estimator Widget**: Instant upload zone generating itemized GCP budget quotes (translation, 7-day staging lifecycle & monthly retention) without login.
  2. **Interactive GCP Onboarding Walkthrough Modal**: Step-by-step modal with direct console links and copyable `gcloud` script.
  3. **BYOK Setup Panel**: Input GCP Project ID, GCS Bucket, Service Account JSON upload with instant dual Translation & Storage validation indicators.
  4. **Pre-Scan View**: Streaming page index, chapter estimation, and **Fraktur OCR Confidence Rating badge**.
  5. **Terminology Memory Table**: Visual indicator of terms auto-populated from saved user vocabulary.
  6. **Live Batch LRO Progress & Recovery**: Real-time progress bar with reconnect/resume capability.
  7. **Scholarly Delivery Actions**: 1-click **"Save to Google Drive"** (GIS OAuth), direct download, fallback plaintext translation trigger for failed pages, and **Side-by-Side Dual-Pane Reading Mode**.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_app_routes.py`.

---

#### Task 5.3: Implement Modal Labs Serverless Web Deployment
* **ID**: `TASK-5.3`
* **Traceability**: FR-17, NFR-05, NFR-07
* **Dependencies**: `TASK-5.2`
* **Description**:
  Create `modal_app.py` defining:
  1. `modal.App("phenomenallayout")`.
  2. `modal.Volume.from_name("phenomenal-user-data")` mounted to `/data` for lightweight user vocabulary and recovery databases ($\le 5\text{MB}$).
  3. `@app.function` with `@modal.asgi_app()` serving the FastAPI/Gradio app.
  4. Configured with 300s scale-to-zero idle timeout.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies `modal_app.py` imports and mounts volume without syntax or configuration errors.

---

#### Task 5.4: End-to-End Book Translation & Scholarly Resilience Test Suite
* **ID**: `TASK-5.4`
* **Traceability**: NFR-01 to NFR-11
* **Dependencies**: `TASK-5.3`
* **Description**:
  Create full end-to-end test suite `tests/test_book_translation_e2e.py` verifying zero-auth cost quote generation with storage retention, Fraktur classification, walkthrough modal data delivery, full BYOK credential validation (Translation + Storage), user vocabulary recall, glossary sync, batch job dispatch, job recovery after disconnect, fallback plaintext translation on failed pages, Google Drive GIS export, dual-pane viewing, and zero host PDF disk footprint.
* **Acceptance Criteria (TDD)**:
  * All tests pass with $\ge 90\%$ code coverage.

---

## 4. Traceability & Dependencies Matrix

| Task ID | Component | Upstream Dependencies | FR / NFR Traceability | Execution Mode |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-1.1** | Config & Deps | None | FR-03, NFR-03 | Sequential |
| **TASK-1.2** | BYOK Credentials Manager| TASK-1.1 | FR-05, FR-08, NFR-03, NFR-11 | Sequential (Track 1) |
| **TASK-1.3** | GCS Batch Service | TASK-1.2 | FR-03, FR-10, NFR-01, NFR-07 | Sequential (Track 1) |
| **TASK-1.4** | LRO Progress Monitor| TASK-1.3 | FR-04, NFR-02 | Sequential (Track 1) |
| **TASK-1.5** | Pre-Auth Cost & Storage| TASK-1.1 | FR-07, NFR-06 | **Parallel (Track 1)** |
| **TASK-1.6** | Google Drive Exporter | TASK-1.1 | FR-09, FR-10, NFR-03, NFR-07 | **Parallel (Track 1)** |
| **TASK-2.1** | User Vocabulary Store | None | FR-06, NFR-03, NFR-09 | **Parallel (Track 2)** |
| **TASK-2.2** | TSV Compiler | TASK-2.1 | FR-02, NFR-04 | Sequential (Track 2) |
| **TASK-2.3** | Glossary Sync Mgr | TASK-1.2, TASK-2.2 | FR-02, FR-06, NFR-04 | Sequential (Track 2) |
| **TASK-2.4** | Quota Auto-Cleanup | TASK-2.3 | FR-14, NFR-03 | Sequential (Track 2) |
| **TASK-3.1** | Fraktur Classifier | None | FR-11, NFR-01, NFR-09 | **Parallel (Track 3)** |
| **TASK-3.2** | Job Recovery Manager | TASK-1.4 | FR-12, NFR-02, NFR-08 | Sequential (Track 3) |
| **TASK-3.3** | Fallback Page Translator| TASK-1.3 | FR-13, NFR-02, NFR-09 | Sequential (Track 3) |
| **TASK-3.4** | Dual-Pane Viewer | None | FR-15, NFR-05, NFR-09 | **Parallel (Track 3)** |
| **TASK-4.1** | Deprecation | None | Cleanup | **Parallel (Track 4)** |
| **TASK-5.1** | Book Orchestrator | TASK-1.3, 1.4, 2.3, 2.4, 3.1-3.3, 4.1 | FR-01, FR-02, FR-03, FR-04, FR-10-14 | Sequential (Track 5) |
| **TASK-5.2** | UI & Delivery Actions | TASK-1.2, 1.5, 1.6, 3.1, 3.4, 5.1 | US-01 to US-13, FR-05, 07, 08, 09, 11, 15 | Sequential (Track 5) |
| **TASK-5.3** | Modal App Deployment| TASK-5.2 | FR-17, NFR-05, NFR-07 | Sequential (Track 5) |
| **TASK-5.4** | Full-Book E2E Test | TASK-5.3 | NFR-01 to NFR-11 | Sequential (Track 5) |
