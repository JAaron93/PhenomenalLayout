# PhenomenalLayout: Agent Operating Guidelines & Architecture Constitution

This document governs the architectural standards, workflow invariants, and prohibited patterns for AI agents working in the **PhenomenalLayout** repository.

---

## 1. Core Domain Mission & Strategic Direction

PhenomenalLayout is a domain-specific **German Philosophical Book Translation & Neologism Orchestration Engine**.

The system pairs **Google Cloud Document Translation API (Cloud Translation - Advanced v3)** with a specialized **German Philosophical Neologism Detection Engine** to translate full-length books (50–1,000+ pages) from German to English with pixel-perfect preservation of typography, multi-column tables, diagrams, and footnotes.

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

---

## 3. Deprecated Patterns & Deny List (Strictly Prohibited)

Agents must NEVER introduce or write code that relies on the following deprecated legacy systems:

| Prohibited Component / Pattern | Reason | Required Modern Replacement |
| :--- | :--- | :--- |
| **Custom Canvas Reconstruction** (`services/pdf_document_reconstructor.py`, ReportLab canvas drawing) | Heuristic font-scaling and box expansion broke tables and figures. | Rely on Google Cloud Document Translation, which natively generates complete, layout-preserved PDFs. |
| **Dedicated GPU OCR Workers** (Modal Dolphin OCR instances, `services/dolphin_client.py`) | High operational complexity and cost. | Outsource OCR and document layout parsing directly to Google Cloud. |
| **Dynamic Programming Layout Placement** (`core/dynamic_layout_engine.py`, `core/dynamic_programming.py`) | Fragile heuristics and technical debt. | Cloud Translation handles typography scaling and line wrapping natively. |
| **Absolute Local Worktree Links** (`file:///Users/...`) | Breaks portability across machines and GitHub UI. | All markdown documentation and spec links must be repository-relative (`spec/gcp-migration/design.md`). |
| **Blocking Sync I/O in Async Paths** | Degrades throughput on multi-chapter books. | Use `asyncio` and non-blocking streaming I/O for GCS uploads and LRO polling. |
| **Hardcoded Credentials or `.env` Commits** | Security vulnerability. | Use Google Cloud Application Default Credentials (ADC) or environment variables. |

---

## 4. Documentation & Specification Hierarchy

* **Specification Organization**: All feature specifications, designs, and task plans must reside in topical subdirectories under `spec/` (e.g., `spec/gcp-migration/`, `spec/<feature-name>/`).
* **Spec Suite Structure**: Follow the 3-document sequence:
  1. `design.md`: Architectural overview, component diagrams, data flows.
  2. `requirements.md`: User Stories, Functional/Non-Functional Requirements with Gherkin BDD scenarios.
  3. `tasks.md`: Test-driven implementation plan with explicit execution tracks and TDD criteria.
* **Architecture Decision Records (ADRs)**: Major architectural shifts must be documented in `docs/adr/XXXX-<title>.md`.

---

## 5. Test-Driven Development (TDD) & Code Quality

* **Strict TDD Sequence**: All new services and bug fixes must be preceded by unit/integration tests with $\ge 90\%$ test coverage.
* **Type Annotations**: Strict Python type hints on all signatures (`from __future__ import annotations`, `typing.Optional`, `Path`, etc.).
* **Retry & Resilience**: All external GCP API interactions must implement exponential backoff retry for HTTP 429/503 errors.
