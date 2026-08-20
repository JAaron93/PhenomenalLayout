# Implementation Tasks: Google Cloud Document Translation & Neologism Orchestration

## 1. Plan Overview & Book-Scale Execution Strategy

This implementation plan decomposes the requirements from [`requirements.md`](spec/gcp-migration/requirements.md) into concrete, test-driven work packages tailored for **full-length book translation** with **Asynchronous GCS Batch Translation as the primary default**, deployed on **Modal Labs** under a **Bring Your Own Key (BYOK)** model.

The tasks are organized into four **Execution Tracks**:
* **Track 1: GCP Batch Translation Engine & BYOK Infrastructure** (Primary pipeline & credential vault)
* **Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store** (Runs in parallel with Track 1)
* **Track 3: Deprecation & Codebase Streamlining** (Independent cleanup)
* **Track 4: Book Orchestrator, Modal Deployment, UI & E2E Validation** (Sequential integration)

---

## 2. Track Breakdown & Parallelism Map

```
┌────────────────────────────────────────────────────────────────────────┐
│ Track 1: GCP Batch Translation Engine & BYOK Infrastructure            │
│ [Task 1.1: Config & Deps] ──> [Task 1.2: BYOK Credentials Manager]    │
│                           ──> [Task 1.3: GCS Batch Service]            │
│                           ──> [Task 1.4: LRO Progress Monitor]         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store    │
│ [Task 2.1: User Vocabulary Store] ──> [Task 2.2: TSV Compiler]        │
│                                   ──> [Task 2.3: Glossary Sync Mgr]    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 3: Codebase Streamlining & Redundant Engine Deprecation          │
│ [Task 3.1: Deprecate Canvas Reconstructor & Legacy Heuristics]        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 4: Book Orchestrator, Modal Deployment, UI & E2E Validation      │
│ [Task 4.1: Book Orchestrator] ──> [Task 4.2: UI with BYOK & Vocab]    │
│                               ──> [Task 4.3: Modal App Scaffolding]    │
│                               ──> [Task 4.4: Full-Book E2E Test Suite] │
└────────────────────────────────────────────────────────────────────────┘
```

> [!TIP] PARALLEL EXECUTION
> **Track 1** (GCP Batch Translation & BYOK Vault) and **Track 2** (User Vocabulary Store & Glossary Sync) are decoupled and can be built and tested concurrently.

---

## 3. Detailed Task Specifications

### Track 1: GCP Batch Translation Engine & BYOK Infrastructure

#### Task 1.1: Configure Dependencies and Environment Defaults
* **ID**: `TASK-1.1`
* **Traceability**: FR-03, NFR-03
* **Dependencies**: None
* **Description**:
  Add `google-cloud-translate>=3.15.0`, `google-cloud-storage>=2.14.0`, and `modal>=0.60.0` to `requirements.txt`. Add configuration dataclasses in `config/settings.py` for default GCP locations (`us-central1`), poll intervals, and Modal volume paths (`/data`).
* **Acceptance Criteria (TDD)**:
  * Unit test verifies settings dataclasses load defaults cleanly without requiring hardcoded secrets in the environment.

---

#### Task 1.2: Implement `BYOKCredentialsManager`
* **ID**: `TASK-1.2`
* **Traceability**: FR-05, NFR-03, NFR-05
* **Dependencies**: `TASK-1.1`
* **Description**:
  Develop [`services/byok_credentials_manager.py`](services/byok_credentials_manager.py):
  1. `set_credentials(user_id: str, project_id: str, bucket_name: str, sa_json_content: str | dict) -> bool`: Ingests and binds user GCP credentials in session memory.
  2. `validate_credentials(user_id: str) -> ValidationResult`: Performs a zero-cost API check (`projects.locations.glossaries.list`) to confirm GCP Translation & Storage IAM permissions.
  3. `get_translation_client(user_id: str) -> TranslationServiceClient`: Returns authenticated Google Cloud Translation v3 client.
  4. `get_storage_client(user_id: str) -> StorageClient`: Returns authenticated Google Cloud Storage client.
  5. `clear_credentials(user_id: str) -> None`: Evicts session credentials.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Validate user Service Account credentials
    Given valid Service Account JSON for project "my-gcp-project"
    When BYOKCredentialsManager.set_credentials is called for user "user-1"
    Then validate_credentials returns status VALID with detected bucket access
    And credentials are never written to disk or logs
  ```
  * Test suite: `tests/test_byok_credentials_manager.py` with mock Google Auth and Translation clients ($\ge 90\%$ coverage).

---

#### Task 1.3: Implement `GCPBatchTranslationService` with GCS Staging
* **ID**: `TASK-1.3`
* **Traceability**: FR-03, NFR-01, NFR-02
* **Dependencies**: `TASK-1.2`
* **Description**:
  Develop [`services/gcp_batch_translation_service.py`](services/gcp_batch_translation_service.py):
  1. `upload_book_to_gcs(user_id: str, local_pdf_path: Path, gcs_destination_uri: str) -> str`: Streams PDF to user's GCS bucket.
  2. `submit_batch_job(user_id: str, gcs_input_uri: str, gcs_output_uri_prefix: str, source_lang: str, target_lang: str, glossary_resource_name: str) -> str`: Dispatches `batch_translate_document` and returns LRO operation name.
  3. `download_translated_book(user_id: str, gcs_output_prefix: str, local_output_path: Path) -> Path`: Downloads completed translated book from user's GCS bucket.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Dispatch full-book batch translation request
    Given a source book at "gs://user-bucket/inputs/book_1/source.pdf"
    And glossary "projects/user-p1/locations/us-central1/glossaries/klages_glossary"
    When submit_batch_job is called for user "user-1"
    Then batch_translate_document is invoked with GcsSource and GcsDestination
    And the returned LRO operation name is stored
  ```
  * Test suite: `tests/test_gcp_batch_translation_service.py` with mock GCS and Translation client ($\ge 90\%$ coverage).

---

#### Task 1.4: Implement `LROProgressMonitor`
* **ID**: `TASK-1.4`
* **Traceability**: FR-04, NFR-02
* **Dependencies**: `TASK-1.3`
* **Description**:
  Develop [`services/lro_progress_monitor.py`](services/lro_progress_monitor.py) to poll LRO operations via `TranslationServiceClient.get_operation`, parse `BatchTranslateDocumentMetadata` (`total_pages`, `translated_pages`, `failed_pages`, `state`), and compute completion percentage and remaining time estimates.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies accurate progress calculation from mock LRO metadata states (`RUNNING`, `SUCCEEDED`, `FAILED`) and `translated_pages` count.

---

### Track 2: Dual-Tier Glossary Sync & Persistent User Vocabulary Store

> [!TIP] PARALLEL EXECUTION
> Can run concurrently with Track 1.

#### Task 2.1: Implement `UserVocabularyStore` (Persistent Memory)
* **ID**: `TASK-2.1`
* **Traceability**: FR-06, NFR-03, NFR-06
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
  3. `cleanup_session_glossary(user_id, glossary_resource_name)`: Deletes temporary book session glossary after batch completion.
* **Acceptance Criteria (TDD & BDD)**:
  * Test suite: `tests/test_glossary_sync_manager.py` with mock GCP Translation client.

---

### Track 3: Codebase Streamlining & Deprecation

#### Task 3.1: Deprecate Legacy Heuristic Layout & Canvas Modules
* **ID**: `TASK-3.1`
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

### Track 4: Book Orchestrator, Modal Deployment, UI & E2E Validation

#### Task 4.1: Build `BookTranslationOrchestrator`
* **ID**: `TASK-4.1`
* **Traceability**: FR-01, FR-02, FR-03, FR-04, FR-05, FR-06
* **Dependencies**: `TASK-1.3`, `TASK-1.4`, `TASK-2.1`, `TASK-2.3`, `TASK-3.1`
* **Description**:
  Develop [`services/book_translation_orchestrator.py`](services/book_translation_orchestrator.py) integrating the end-to-end book workflow:
  1. Pre-scan book stream for neologisms, cross-referencing `UserVocabularyStore`.
  2. Present pre-filled terminology table in UI.
  3. Update user vocabulary store with finalized choices.
  4. Trigger glossary synchronization with user's GCP project.
  5. Dispatch batch translation to user's GCS bucket and monitor LRO.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_book_translation_orchestrator.py`.

---

#### Task 4.2: Update UI with BYOK Panel, User Vocab & Live LRO Progress
* **ID**: `TASK-4.2`
* **Traceability**: US-01, US-02, US-03, US-04, US-05, US-06
* **Dependencies**: `TASK-4.1`
* **Description**:
  Update [`app.py`](app.py) and [`api/routes.py`](api/routes.py):
  1. **BYOK Setup Panel**: Input GCP Project ID, GCS Bucket, Service Account JSON upload with instant validation indicator.
  2. **Book Upload & Pre-Scan View**: Streaming page index and chapter estimation.
  3. **Terminology Memory Table**: Visual indicator of terms auto-populated from saved user vocabulary vs. new novel coined compounds.
  4. **Live Batch LRO Progress**: Real-time progress bar displaying page count (e.g. `142/350 Pages Translated`) and download button.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_app_routes.py`.

---

#### Task 4.3: Implement Modal Labs Serverless Web Deployment
* **ID**: `TASK-4.3`
* **Traceability**: FR-08, NFR-05
* **Dependencies**: `TASK-4.2`
* **Description**:
  Create `modal_app.py` defining:
  1. `modal.App("phenomenallayout")`.
  2. `modal.Volume.from_name("phenomenal-user-data")` mounted to `/data` for user vocabulary databases.
  3. `@app.function` with `@modal.asgi_app()` serving the FastAPI/Gradio app.
  4. Configured with 300s scale-to-zero idle timeout.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies `modal_app.py` imports and mounts volume without syntax or configuration errors.

---

#### Task 4.4: End-to-End Book Translation & BYOK Integration Test Suite
* **ID**: `TASK-4.4`
* **Traceability**: NFR-01, NFR-03, NFR-05, NFR-06, NFR-07
* **Dependencies**: `TASK-4.3`
* **Description**:
  Create full end-to-end test suite `tests/test_book_translation_e2e.py` verifying full BYOK credential validation, user vocabulary recall, glossary sync, batch job dispatch, simulated LRO polling, and final PDF output.
* **Acceptance Criteria (TDD)**:
  * All tests pass with $\ge 90\%$ code coverage.

---

## 4. Traceability & Dependencies Matrix

| Task ID | Component | Upstream Dependencies | FR / NFR Traceability | Execution Mode |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-1.1** | Config & Deps | None | FR-03, NFR-03 | Sequential |
| **TASK-1.2** | BYOK Credentials Manager| TASK-1.1 | FR-05, NFR-03, NFR-05 | Sequential (Track 1) |
| **TASK-1.3** | GCS Batch Service | TASK-1.2 | FR-03, NFR-01, NFR-02 | Sequential (Track 1) |
| **TASK-1.4** | LRO Progress Monitor| TASK-1.3 | FR-04, NFR-02 | Sequential (Track 1) |
| **TASK-2.1** | User Vocabulary Store | None | FR-06, NFR-03, NFR-06 | **Parallel (Track 2)** |
| **TASK-2.2** | TSV Compiler | TASK-2.1 | FR-02, NFR-04 | Sequential (Track 2) |
| **TASK-2.3** | Glossary Sync Mgr | TASK-1.2, TASK-2.2 | FR-02, FR-06, NFR-04 | Sequential (Track 2) |
| **TASK-3.1** | Deprecation | None | Cleanup | **Parallel (Track 3)** |
| **TASK-4.1** | Book Orchestrator | TASK-1.4, TASK-2.3, TASK-3.1 | FR-01, FR-02, FR-03, FR-04 | Sequential (Track 4) |
| **TASK-4.2** | BYOK UI & Live LRO | TASK-4.1 | US-01 to US-06, FR-05 | Sequential (Track 4) |
| **TASK-4.3** | Modal App Deployment| TASK-4.2 | FR-08, NFR-05 | Sequential (Track 4) |
| **TASK-4.4** | Full-Book E2E Test | TASK-4.3 | NFR-01, NFR-05, NFR-06 | Sequential (Track 4) |
