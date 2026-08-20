# PhenomenalLayout: Agent Operating Guidelines & Architecture Constitution

This document governs the architectural standards, workflow invariants, and prohibited patterns for AI agents working in the **PhenomenalLayout** repository.

---

## 1. Core Domain Mission & Strategic Direction

PhenomenalLayout is a domain-specific **German Philosophical Book Translation & Neologism Orchestration Engine**.

The system pairs **Google Cloud Document Translation API (Cloud Translation - Advanced v3)** with a specialized **German Philosophical Neologism Detection Engine** to translate full-length books (50–1,000+ pages) from German to English with pixel-perfect preservation of typography, multi-column tables, diagrams, and footnotes.

The application runs serverless on **Modal Labs** under a **Bring Your Own Key (BYOK)** model.

---

## 2. Translation & Document Pipeline Standards

### 2.1 Primary Default: Asynchronous GCS Batch Translation
* **Book-Scale Default**: For full-length books (50–1,000+ pages), the pipeline **MUST** use asynchronous `batchTranslateDocument` via Google Cloud Storage (`gs://<bucket>/inputs/...` $\rightarrow$ `gs://<bucket>/outputs/...`).
* **Synchronous Preview Mode**: Synchronous `translateDocument` is reserved strictly as a secondary rapid preview mechanism for 1–3 sample pages.
* **LRO Progress Contract**: When monitoring Long-Running Operations (LROs), always adhere to the official Google Cloud Translation v3 metadata contract:
  - Progress fields: `metadata.translated_pages`, `metadata.total_pages`, `metadata.failed_pages`.
  - State enumeration: `SUBMITTED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLING`, `CANCELLED`.
  - Success check: `metadata.state == SUCCEEDED` (or `operation.done == True`).

### 2.2 Dual-Tier Glossary Synchronization
* **Tier 1 (Persistent Base Glossary)**: Static philosophical foundation dictionaries (`config/klages_terminology.json`) provisioned once as regional GCP Glossaries in `us-central1`.
* **Tier 2 (Dynamic Book Session Glossary)**: Dynamic user choices and novel coined compounds compiled into RFC 4180 TSVs (`de\ten`), uploaded to GCS, and registered with Cloud Translation before the batch job executes.
* **Glossary Lifecycle**: Temporary book session glossaries must have automated TTL/cleanup policies upon job completion.

### 2.3 Bring Your Own Key (BYOK) & Billing Isolation
* **User-Billed Cloud Compute**: All Google Cloud Document Translation charges ($0.08/page) and GCS bucket storage are billed directly to each user's personal GCP billing account. The host maintains zero translation API or cloud storage costs.
* **Credential Isolation**: User-provided Service Account JSON keys must be held strictly in session memory and never written to disk, logged, or shared across user sessions.
* **Zero-Cost Validation**: Credentials must be validated upon entry using non-billable API calls (`projects.locations.glossaries.list`).
* **Onboarding Walkthrough Modal**: The BYOK setup panel must include an interactive 6-step guided walkthrough modal with direct GCP console links and a copyable `gcloud` setup script.

### 2.4 Pre-Auth Zero-Credential Cost Estimator
* The web interface must provide an unauthenticated PDF cost quote calculation on Modal CPU without requiring user sign-in or GCP credentials.
* Pricing estimates must include per-page translation rates ($0.080/page), GCS staging buffers, and sample preview allowances with variance within $\pm \$5.00$.

### 2.5 Persistent User Neologism Vocabulary Store
* User translation choices (translated equivalents, untranslated directives, notes) must be persisted per `user_id` on the Modal Volume (`modal.Volume.from_name("phenomenal-user-data")` mounted at `/data`).
* When pre-scanning subsequent books, the engine must automatically recall and pre-fill saved user vocabulary.

---

## 3. Modal Labs Serverless Deployment Architecture
* **Framework**: Deployable as a serverless ASGI web app (`modal_app.py`, `@modal.asgi_app()`).
* **Compute Tier**: Must operate efficiently within Modal Labs' $30/month free compute tier by enforcing automatic scale-to-zero when idle (`scaledown_window=300`).
* **Storage**: Persistent storage must utilize `modal.Volume` for user profile and database storage (`/data/`).

---

## 4. Deprecated Patterns & Deny List (Strictly Prohibited)

Agents must NEVER introduce or write code that relies on the following deprecated legacy systems:

| Prohibited Component / Pattern | Reason | Required Modern Replacement |
| :--- | :--- | :--- |
| **Custom Canvas Reconstruction** (`services/pdf_document_reconstructor.py`, ReportLab canvas drawing) | Heuristic font-scaling and box expansion broke tables and figures. | Rely on Google Cloud Document Translation, which natively generates complete, layout-preserved PDFs. |
| **Dedicated GPU OCR Workers** (Modal Dolphin OCR instances, `services/dolphin_client.py`) | High operational complexity and cost. | Outsource OCR and document layout parsing directly to Google Cloud. |
| **Dynamic Programming Layout Placement** (`core/dynamic_layout_engine.py`, `core/dynamic_programming.py`) | Fragile heuristics and technical debt. | Cloud Translation handles typography scaling and line wrapping natively. |
| **Absolute Local Worktree Links** (`file:///Users/...`) | Breaks portability across machines and GitHub UI. | All markdown documentation and spec links must be repository-relative (`spec/gcp-migration/design.md`). |
| **Blocking Sync I/O in Async Paths** | Degrades throughput on multi-chapter books. | Use `asyncio` and non-blocking streaming I/O for GCS uploads and LRO polling. |
| **Hardcoded Credentials or `.env` Commits** | Security vulnerability. | Use session-scoped BYOK vaults or Google Cloud Application Default Credentials (ADC). |

---

## 5. Documentation & Specification Hierarchy

* **Specification Organization**: All feature specifications, designs, and task plans must reside in topical subdirectories under `spec/` (e.g., `spec/gcp-migration/`, `spec/<feature-name>/`).
* **Spec Suite Structure**: Follow the 3-document sequence:
  1. `design.md`: Architectural overview, component diagrams, data flows.
  2. `requirements.md`: User Stories, Functional/Non-Functional Requirements with Gherkin BDD scenarios.
  3. `tasks.md`: Test-driven implementation plan with explicit execution tracks and TDD criteria.
* **Architecture Decision Records (ADRs)**: Major architectural shifts must be documented in `docs/adr/XXXX-<title>.md`.

---

## 6. Test-Driven Development (TDD) & Code Quality

* **Strict TDD Sequence**: All new services and bug fixes must be preceded by unit/integration tests with $\ge 90\%$ test coverage.
* **Type Annotations**: Strict Python type hints on all signatures (`from __future__ import annotations`, `typing.Optional`, `Path`, etc.).
* **Retry & Resilience**: All external GCP API interactions must implement exponential backoff retry for HTTP 429/503 errors.
