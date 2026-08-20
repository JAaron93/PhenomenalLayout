# Implementation Tasks: Google Cloud Document Translation & Neologism Orchestration

## 1. Plan Overview & Book-Scale Execution Strategy

This implementation plan decomposes the requirements from [`requirements.md`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/spec/gcp-migration/requirements.md) into concrete, test-driven work packages tailored for **full-length book translation** with **Asynchronous GCS Batch Translation as the primary default**.

The tasks are organized into four **Execution Tracks**:
* **Track 1: GCP Batch Translation Engine & GCS File Staging** (Primary pipeline infrastructure)
* **Track 2: Dual-Tier Glossary Synchronization Subsystem** (Runs in parallel with Track 1)
* **Track 3: Deprecation & Codebase Streamlining** (Independent cleanup)
* **Track 4: Book Orchestrator, Live LRO UI & E2E Validation** (Sequential integration)

---

## 2. Track Breakdown & Parallelism Map

```
┌─────────────────────────────────────────────────────────────┐
│ Track 1: GCP Batch Translation Engine & GCS Staging        │
│ [Task 1.1: Config & GCS Deps] ──> [Task 1.2: Batch Client]  │
│                               ──> [Task 1.3: LRO Monitor]   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Track 2: Dual-Tier Glossary Synchronization Subsystem        │
│ [Task 2.1: TSV Compiler] ──> [Task 2.2: Glossary Sync Mgr]  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Track 3: Codebase Streamlining & Redundant Engine Deprecation│
│ [Task 3.1: Deprecate Canvas Reconstructor & Modal Workers]  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Track 4: Book Orchestrator, Live LRO UI & E2E Validation     │
│ [Task 4.1: Book Orchestrator] ──> [Task 4.2: UI Live LRO]   │
│                               ──> [Task 4.3: Full-Book E2E] │
└─────────────────────────────────────────────────────────────┘
```

> [!TIP] PARALLEL EXECUTION
> **Track 1** (GCP Batch Translation & GCS Staging) and **Track 2** (Glossary Synchronization Subsystem) are completely decoupled and can be built and tested simultaneously.

---

## 3. Detailed Task Specifications

### Track 1: GCP Batch Translation Engine & GCS File Staging

#### Task 1.1: Configure Dependencies and GCS Bucket Settings
* **ID**: `TASK-1.1`
* **Traceability**: FR-03, NFR-03
* **Dependencies**: None
* **Description**:
  Add `google-cloud-translate>=3.15.0` and `google-cloud-storage>=2.14.0` to `requirements.in` and `requirements.txt`. Add configuration in `config/settings.py` for `GCP_PROJECT_ID`, `GCP_LOCATION`, `GCP_TRANSLATION_BUCKET`, `GCP_BASE_GLOSSARY_ID`, and `BATCH_POLL_INTERVAL_SEC`.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies settings load valid environment variables and default regional endpoints (`us-central1`).

---

#### Task 1.2: Implement `GCPBatchTranslationService` with GCS Staging
* **ID**: `TASK-1.2`
* **Traceability**: FR-03, NFR-01, NFR-02
* **Dependencies**: `TASK-1.1`
* **Description**:
  Develop [`services/gcp_batch_translation_service.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/gcp_batch_translation_service.py):
  1. `upload_book_to_gcs(local_pdf_path: Path, gcs_destination_uri: str) -> str`: Streaming GCS upload.
  2. `submit_batch_job(gcs_input_uri: str, gcs_output_uri_prefix: str, source_lang: str, target_lang: str, glossary_resource_name: str) -> str`: Dispatches `batch_translate_document` and returns LRO operation name.
  3. `download_translated_book(gcs_output_prefix: str, local_output_path: Path) -> Path`: Downloads completed translated book from GCS.
* **Acceptance Criteria (TDD & BDD)**:
  ```gherkin
  Scenario: Dispatch full-book batch translation request
    Given a source book at "gs://bucket/inputs/book_1/source.pdf"
    And glossary "projects/p1/locations/us-central1/glossaries/klages_glossary"
    When submit_batch_job is called
    Then batch_translate_document is invoked with GcsSource and GcsDestination
    And the returned LRO operation name is stored
  ```
  * Test suite: `tests/test_gcp_batch_translation_service.py` with mock GCS and Translation client ($\ge 90\%$ coverage).

---

#### Task 1.3: Implement `LROProgressMonitor`
* **ID**: `TASK-1.3`
* **Traceability**: FR-04, NFR-02
* **Dependencies**: `TASK-1.2`
* **Description**:
  Develop [`services/lro_progress_monitor.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/lro_progress_monitor.py) to poll LRO operations via `TranslationServiceClient.get_operation`, parse `BatchTranslateDocumentMetadata` (total pages, completed pages, failed pages, state), and compute completion percentage and remaining time estimates.
* **Acceptance Criteria (TDD)**:
  * Unit test verifies accurate progress calculation from mock LRO metadata states (`RUNNING`, `SUCCESS`, `FAILED`).

---

### Track 2: Dual-Tier Glossary Synchronization Subsystem

> [!TIP] PARALLEL EXECUTION
> Can run concurrently with Track 1.

#### Task 2.1: Implement RFC 4180 Glossary TSV/CSV Compiler
* **ID**: `TASK-2.1`
* **Traceability**: FR-02, NFR-04
* **Dependencies**: None
* **Description**:
  Create [`services/glossary_compiler.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/glossary_compiler.py) to combine base philosophical terms ([`config/klages_terminology.json`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/config/klages_terminology.json)) with book-specific user choices ([`core/dynamic_choice_engine.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/core/dynamic_choice_engine.py)), producing strictly formatted TSV bytes with header `de\ten`.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_glossary_compiler.py` verifying TSV encoding, quote escaping, and deduplication.

---

#### Task 2.2: Implement `GlossarySyncManager` (Dual-Tier Provisioning)
* **ID**: `TASK-2.2`
* **Traceability**: FR-02, FR-06, NFR-04
* **Dependencies**: `TASK-1.1`, `TASK-2.1`
* **Description**:
  Develop [`services/glossary_sync_manager.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/glossary_sync_manager.py):
  1. `sync_base_glossary()`: Provisions persistent Tier 1 base glossary if not already active in GCP region.
  2. `sync_book_session_glossary(session_id, user_choices)`: Uploads combined TSV to `gs://<bucket>/glossaries/sessions/<session_id>.tsv`, invokes `create_glossary`, polls until `READY`, and returns glossary resource name.
  3. `cleanup_session_glossary(glossary_resource_name)`: Deletes temporary book session glossary after batch completion.
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

### Track 4: Book Orchestrator, Live LRO UI & E2E Validation

#### Task 4.1: Build `BookTranslationOrchestrator`
* **ID**: `TASK-4.1`
* **Traceability**: FR-01, FR-02, FR-03, FR-04, FR-05
* **Dependencies**: `TASK-1.2`, `TASK-1.3`, `TASK-2.2`, `TASK-3.1`
* **Description**:
  Develop [`services/book_translation_orchestrator.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/book_translation_orchestrator.py) integrating the end-to-end book workflow:
  1. Pre-scan book stream for neologisms.
  2. Register user choices in choice engine.
  3. Trigger glossary synchronization with GCP.
  4. Dispatch batch translation to GCS and spawn LRO monitoring worker.
  5. Provide optional single-page inline preview method.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_book_translation_orchestrator.py`.

---

#### Task 4.2: Update UI with Book Pre-Scan & Live Batch LRO Progress
* **ID**: `TASK-4.2`
* **Traceability**: US-01, US-02, US-03, US-04
* **Dependencies**: `TASK-4.1`
* **Description**:
  Update [`app.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/app.py) and [`api/routes.py`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/api/routes.py):
  1. Book upload interface with chapter/page estimation.
  2. Terminology review table for philosophical neologisms.
  3. "Start Full-Book Translation (Batch)" action triggering GCS batch workflow.
  4. Real-time LRO progress bar displaying page count (e.g. `142/350 Pages Translated`) and download button upon job completion.
* **Acceptance Criteria (TDD)**:
  * Test suite: `tests/test_app_routes.py`.

---

#### Task 4.3: End-to-End Book Translation Test Suite
* **ID**: `TASK-4.3`
* **Traceability**: NFR-01, NFR-05, NFR-06
* **Dependencies**: `TASK-4.2`
* **Description**:
  Create full end-to-end test suite `tests/test_book_translation_e2e.py` verifying full-book pre-scan, glossary sync, batch job dispatch, simulated LRO polling, and final PDF verification.
* **Acceptance Criteria (TDD)**:
  * All tests pass with $\ge 90\%$ code coverage.

---

## 4. Traceability & Dependencies Matrix

| Task ID | Component | Upstream Dependencies | FR / NFR Traceability | Execution Mode |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-1.1** | Config & GCS Deps | None | FR-03, NFR-03 | Sequential |
| **TASK-1.2** | GCS Batch Service | TASK-1.1 | FR-03, NFR-01, NFR-02 | Sequential (Track 1) |
| **TASK-1.3** | LRO Progress Monitor| TASK-1.2 | FR-04, NFR-02 | Sequential (Track 1) |
| **TASK-2.1** | TSV Compiler | None | FR-02, NFR-04 | **Parallel (Track 2)** |
| **TASK-2.2** | Glossary Sync Mgr | TASK-1.1, TASK-2.1 | FR-02, FR-06, NFR-04 | Sequential (Track 2) |
| **TASK-3.1** | Deprecation | None | Cleanup | **Parallel (Track 3)** |
| **TASK-4.1** | Book Orchestrator | TASK-1.3, TASK-2.2, TASK-3.1 | FR-01, FR-02, FR-03, FR-04 | Sequential (Track 4) |
| **TASK-4.2** | Live LRO UI & API | TASK-4.1 | US-01, US-02, US-03, US-04 | Sequential (Track 4) |
| **TASK-4.3** | Full-Book E2E Test | TASK-4.2 | NFR-01, NFR-05, NFR-06 | Sequential (Track 4) |
