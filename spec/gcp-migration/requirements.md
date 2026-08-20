# Requirements Specification: Google Cloud Document Translation & Neologism Orchestration

## 1. Overview & Book-Scale Scope

This specification defines the functional, non-functional, behavioral (BDD), and test-driven (TDD) requirements for PhenomenalLayout, focused on **full-length books and long-form philosophical manuscripts**.

The core system consists of:
1. Stream-based text extraction and neologism pre-scanning for large book PDFs.
2. Dual-tier glossary synchronization (persistent domain dictionaries + dynamic user overrides).
3. **Primary Default Pipeline: Asynchronous batch document translation (`batchTranslateDocument`) via Google Cloud Storage (GCS)**.
4. Live Long-Running Operation (LRO) progress monitoring for book translation jobs.
5. Secondary synchronous preview translation for single sample pages.

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

---

## 3. Functional Requirements (FR) & BDD Scenarios

### FR-01: Stream-Based PDF Book Ingestion & Neologism Pre-Scanning
* **Description**: Ingest full book PDFs using stream-based chunking, scan text streams with [`NeologismDetector`](file:///Users/pretermodernist/.gemini/antigravity/worktrees/PhenomenalLayout/fix_translation_layout_formatting/services/neologism_detector.py), and aggregate frequency and sentence context without loading high-resolution page bitmaps into memory.
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
* **Description**: The system must maintain persistent base glossaries (Tier 1) and dynamic book session glossaries (Tier 2). It must compile terms into RFC 4180 TSV files, upload them to GCS (`gs://<bucket>/glossaries/...`), and ensure a corresponding Cloud Translation v3 Glossary resource is created and in `READY` state.
* **Traceability**: US-02

#### BDD Scenario FR-02.1: Synchronize Dynamic Book Glossary to GCP
```gherkin
Feature: Dual-Tier Glossary Sync
  Scenario: Provision book session glossary overlaying base dictionary
    Given a base dictionary with 120 Klages terms
    And 25 book-specific user choices recorded in session "book-sess-42"
    When the GlossarySyncManager compiles and provisions the glossary in region "us-central1"
    Then a combined TSV is uploaded to "gs://trans-bucket/glossaries/sessions/book-sess-42.tsv"
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
    Given a book PDF staged at "gs://trans-bucket/inputs/book-101/source.pdf"
    And an active glossary resource "projects/p1/locations/us-central1/glossaries/book-sess-42"
    When the orchestrator submits batch_translate_document
    Then an asynchronous Long Running Operation (LRO) is created
    And the job state transitions to "RUNNING"
```

---

### FR-04: Batch Job Monitoring & Progress Polling
* **Description**: The system must poll the GCP Translation LRO operation every $N$ seconds, extract `pages_completed` and `total_pages` metadata, and publish progress updates to the UI.
* **Traceability**: US-04

#### BDD Scenario FR-04.1: Track LRO Progress to Completion
```gherkin
Feature: Batch Translation LRO Monitoring
  Scenario: Poll batch translation progress until completion
    Given an active batch translation LRO "projects/p1/locations/us-central1/operations/op-99"
    When the progress monitor polls the operation
    Then progress metadata is emitted (e.g. 150/300 pages completed)
    And when the LRO reaches "DONE", the translated PDF is downloaded from GCS outputs
    And output PDF page count is verified to equal 300
```

---

### FR-05: Single-Page Rapid Preview Translation (Secondary Mode)
* **Description**: Allow translators to test translation quality on 1–3 sample pages using synchronous `translateDocument` with `enableShadowRemovalNativePdf=True` before committing to a full book batch run.
* **Traceability**: US-01, US-02

---

### FR-06: Glossary & File Staging Lifecycle Management
* **Description**: The system must apply 7-day TTL lifecycle rules to transient GCS input/output book objects and session glossaries, while preserving persistent base glossaries.
* **Traceability**: US-02, US-03

---

## 4. Non-Functional Requirements (NFR)

| ID | Category | Requirement Description | Metric / Standard |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **Scalability** | Batch pipeline must support translating long books up to 1,000 pages without memory starvation. | Peak RAM usage $\le 256\text{ MB}$; streaming file handling. |
| **NFR-02** | **Reliability** | Long-running operation polling and GCS downloads must recover from network disconnects. | Exponential backoff retry with up to 5 attempts. |
| **NFR-03** | **Security** | Zero credential leaks: No GCP service account JSON files or private keys stored in code or repository commits. | Mandatory check against `.gitignore` / ADC environment validation. |
| **NFR-04** | **Glossary Consistency** | 100% of defined glossary terms must be supplied in compliant UTF-8 TSV format. | Zero TSV syntax errors; validation pass prior to GCS upload. |
| **NFR-05** | **Test Coverage** | New GCS batch translation client, glossary sync manager, and orchestrator modules must be covered by automated tests. | $\ge 90\%$ line and branch coverage. |
| **NFR-06** | **TDD 3-Strike Gate** | All bug fixes and feature development must follow strict TDD sequences with a 3-strike fail-safe abort. | Test pass rate must not fall below $90\%$ across 3 consecutive loops. |

---

## 5. Traceability Matrix

| User Story | Functional Requirement | Non-Functional Requirement | Test Target |
| :--- | :--- | :--- | :--- |
| **US-01** | FR-01, FR-05 | NFR-01 | `tests/test_book_pre_scanner.py` |
| **US-02** | FR-02, FR-06 | NFR-03, NFR-04 | `tests/test_glossary_sync_manager.py` |
| **US-03** | FR-03, FR-04 | NFR-01, NFR-02, NFR-05 | `tests/test_gcp_batch_translation_service.py` |
| **US-04** | FR-04 | NFR-02 | `tests/test_lro_progress_monitor.py` |
| **All** | FR-01 to FR-06 | NFR-05, NFR-06 | `tests/test_book_translation_e2e.py` |
