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
* **Glossary Lifecycle & Quota Management**: Temporary book session glossaries must have automated cleanup handlers upon job completion to respect the regional 1,000 glossary quota.

### 2.3 Bring Your Own Key (BYOK) & Billing Isolation
* **User-Billed Cloud Compute**: All Google Cloud Document Translation charges ($0.08/page) and GCS bucket storage are billed directly to each user's personal GCP billing account. The host maintains zero translation API or cloud storage costs.
* **Credential Isolation**: User-provided Service Account JSON keys must be held strictly in session memory and never written to disk, logged, or shared across user sessions.
* **Zero-Cost Validation**: Credentials must be validated upon entry using non-billable API calls (`projects.locations.glossaries.list`).
* **Onboarding Walkthrough Modal**: The BYOK setup panel must include an interactive 6-step guided walkthrough modal with direct GCP console links and a copyable `gcloud` setup script.

### 2.4 Pre-Auth Zero-Credential Cost & Storage Estimator
* The web interface must provide an unauthenticated PDF cost quote calculation on Modal CPU without requiring user sign-in or GCP credentials.
* Pricing estimates must include per-page translation rates ($0.080/page), GCS 5 GB Always Free tier checks, and monthly/annual storage retention schedules with variance within $\pm \$5.00$.

### 2.5 Persistent User Neologism Vocabulary Store
* User translation choices (translated equivalents, untranslated directives, notes) must be persisted per `user_id` on the Modal Volume (`modal.Volume.from_name("phenomenal-user-data")` mounted at `/data`).
* When pre-scanning subsequent books, the engine must automatically recall and pre-fill saved user vocabulary.

### 2.6 Zero Host PDF Storage Invariant
* Modal Labs backend instances and volumes must store **zero** book PDF files. The source PDF and translated outputs reside strictly in the user's GCS bucket or personal Google Drive.
* Modal Volume storage (`/data/`) is reserved strictly for lightweight user vocabulary databases ($\le 5\text{MB}$).

### 2.7 Seamless Google Drive Export (Zero-SaaS GIS)
* The application must support 1-click export to the user's personal Google Drive using native client-side **Google Identity Services (GIS)** OAuth.
* Must request restricted `https://www.googleapis.com/auth/drive.file` scope (zero access to unrelated user Drive files).
* Prohibits heavy third-party authentication middleware (no Auth0, no Clerk).

### 2.8 Scholarly Resilience & Production Invariants
* **Fraktur OCR Assessment**: Must evaluate font characteristics and emit an OCR script confidence rating for pre-1945 German editions.
* **Job Resumption**: Active LRO state must be persisted to allow seamless reconnection after browser closing or Modal container scale-down.
* **Fallback Plaintext Translation**: If complex diagram pages fail layout parsing (`failed_pages > 0`), the engine must offer 1-click plaintext extraction and translation to guarantee a 98% layout-preserved, 100% translated book.
* **Side-by-Side Dual-Pane Viewer**: Must support synchronized bilingual reading for scholars verifying translations against the German original.

### 2.9 GCS Staging Lifecycle & Cost Isolation Invariant
* **Strict Fail-Fast Staging Cleanup**: When source PDFs are uploaded or submitted under the staging prefix (`inputs/`), the system MUST verify that an unconditional 7-day auto-delete lifecycle policy exists on the user's bucket.
* **No Silent Bypass**: If lifecycle verification or bucket patching fails, the upload/submission MUST raise a `RuntimeError` immediately rather than proceeding silently and accruing unbounded user storage costs.
* **Unconditional Rule Matching**: When matching existing lifecycle rules, the rule MUST match exact `age == 7`, apply to live objects (`isLive is not False`), and contain NO restrictive conditions (e.g., `matchesStorageClass`, `createdBefore`, `customTimeBefore`, `daysSinceCustomTime`, `numNewerVersions`). If restrictive conditions exist, an unconditional rule MUST be appended.

### 2.10 Zero Resource Leakage & Descriptor Safety
* **Deterministic File Handle Cleanup**: Any service accepting `Path | bytes | BinaryIO` for offline processing (e.g. `GCPCostEstimator`) MUST deterministically close internally opened file descriptors using `try...finally` blocks or context managers, preventing file descriptor exhaustion in serverless environments.
* **Package Export Symmetry**: All optional or conditional services recorded in internal availability registries MUST explicitly define and export their corresponding boolean availability flag (e.g., `GCP_BATCH_SERVICES_AVAILABLE`) in the top-level package `__all__`.

### 2.11 Zero-Downtime Blue-Green Glossary & Quota Bounding Invariants
* **Zero Creation Window Outages (Blue-Green Replacement)**: When updating or resynchronizing Tier 2 session glossaries, the system MUST provision the replacement glossary under an alternating slot (`-a` / `-b`) and verify it is fully `READY` before retiring superseded resources. Active working glossaries must NEVER be deleted prior to replacement verification.
* **Strict Two-Slot Bound (No Unbounded UUID Slots)**: A session MUST NEVER allocate arbitrary UUID overflow slots. Total active regional slots per session must be strictly bounded to at most 2 (`-a` and `-b`). If both slots remain active due to an earlier interrupted retirement:
  1. Determine the older superseded slot by comparing `submit_time` timestamps.
  2. Stage the replacement TSV to GCS first.
  3. Retire the older superseded slot to free its slot identifier.
  4. Provision the replacement in that freed slot while the newer working slot continues serving traffic.
* **Versioned GCS Staging & Rollback Preservation**: Staged session TSVs in GCS MUST use versioned object names (`.../{slot}_{version}.tsv`) so that uploading replacement terminology NEVER overwrites the older known-good TSV in GCS. If replacement creation fails, the system MUST execute automated rollback restoration using the preserved previous GCS input URI.
* **Cryptographic Token Session Isolation**: Session prefix matching MUST incorporate a deterministic 16-character SHA-256 token (`sess-{slug}-{token}-a`) to prevent false prefix matches between sibling sessions (e.g., preventing `book-101` from deleting `book-101-extra`).

### 2.12 Fallback Plaintext Translation & Unicode Typography Invariants
* **100% Content Completeness (Plaintext Scope)**: When Google Cloud Document Translation encounters layout parsing failures (`failed_pages > 0`), the secondary fallback engine (`FallbackPageTranslator`) is invoked strictly to guarantee 100% translation completeness so the scholar misses no translated text. The fallback page MUST be synthesized as clean, readable plaintext. It is explicitly exempted from attempting complex multi-column geometric replication or vector diagram reconstruction, which was deprecated under §4.
* **Strict 1-to-1 Physical Page Alignment**: Each failed source page MUST be replaced by exactly one synthesized fallback page. Dynamic page height expansion MUST be used if needed to accommodate large text blocks with proper leading ($\ge 11.0\text{pt}$), ensuring physical page numbering matches the original German edition for synchronized side-by-side verification in `DualPaneViewerController`.
* **Zero Transliteration / Substitution (Unicode Fidelity)**: Fallback rendering MUST preserve all Unicode characters (Greek, Cyrillic, Hebrew, Arabic, German umlauts, Fraktur ligatures, mathematical symbols, and CJK ideographs) verbatim. Transliterating non-Latin text into ASCII approximations (e.g. `бытие` $\rightarrow$ `bytie`) or placeholder tokens (`[CJK UNIFIED IDEOGRAPH...]`) is strictly prohibited.
* **Dynamic Sequential 16-Bit CID Allocation & Format 12 TrueType CMap Parsing**: When generating PDF composite Type 0 fonts (`/CIDFontType2`) via `pypdf`:
  1. The engine MUST parse both format 4 (BMP) and format 12 (32-bit supplementary planes) `cmap` subtables from embedded font programs.
  2. The engine MUST dynamically allocate unique 16-bit sequential CIDs ($1 \dots N$) to all unique characters on the page. Emitting raw UTF-16 code units directly into `/Identity-H` content streams is strictly prohibited because it fragments supplementary Unicode characters ($> \text{U+FFFF}$) into two separate surrogate CIDs.
  3. The engine MUST generate dynamic big-endian `/CIDToGIDMap` stream objects mapping each dynamic CID to its TrueType glyph ID, and `/W` arrays with exact advance widths.
* **Fallback Limitations Documentation**: Any modification to the fallback translation engine MUST keep `docs/FALLBACK_TRANSLATION_LIMITATIONS.md` up to date, documenting font glyph coverage limits, lack of vector diagram reproduction, and table line-wrapping behaviors.

---

## 3. Modal Labs Serverless Deployment Architecture
* **Framework**: Deployable as a serverless ASGI web app (`modal_app.py`, `@modal.asgi_app()`).
* **Compute Tier**: Must operate efficiently within Modal Labs' $30/month free compute tier by enforcing automatic scale-to-zero when idle (`scaledown_window=300`).
* **Storage**: Persistent storage must utilize `modal.Volume` strictly for user metadata and terminology storage (`/data/`).

---

## 4. Deprecated Patterns & Deny List (Strictly Prohibited)

Agents must NEVER introduce or write code that relies on the following deprecated legacy systems:

| Prohibited Component / Pattern | Reason | Required Modern Replacement |
| :--- | :--- | :--- |
| **Custom Canvas Reconstruction** (`services/pdf_document_reconstructor.py`, ReportLab canvas drawing) | Heuristic font-scaling and box expansion broke tables and figures. | Rely on Google Cloud Document Translation, which natively generates complete, layout-preserved PDFs. |
| **Dedicated GPU OCR Workers** (Modal Dolphin OCR instances, `services/dolphin_client.py`) | High operational complexity and cost. | Outsource OCR and document layout parsing directly to Google Cloud. |
| **Dynamic Programming Layout Placement** (`core/dynamic_layout_engine.py`, `core/dynamic_programming.py`) | Fragile heuristics and technical debt. | Cloud Translation handles typography scaling and line wrapping natively. |
| **Third-Party Auth Middleware** (Auth0, Clerk, Firebase) | Unnecessary SaaS dependency, cost, and complexity. | Use native client-side Google Identity Services (GIS) OAuth with `drive.file` scope. |
| **Storing Book PDFs on Host Disk** | Memory exhaustion and disk bloat on serverless instances. | Stream directly to/from user GCS bucket and Google Drive. |
| **Absolute Local Worktree Links** (`file:///Users/...`) | Breaks portability across machines and GitHub UI. | All markdown documentation and spec links must be repository-relative (`.kiro/specs/gcp-migration/design.md`). |
| **Blocking Sync I/O in Async Paths** | Degrades throughput on multi-chapter books. | Use `asyncio` and non-blocking streaming I/O for GCS uploads and LRO polling. |
| **Hardcoded Credentials or `.env` Commits** | Security vulnerability. | Use session-scoped BYOK vaults or Google Cloud Application Default Credentials (ADC). |
| **Premature Glossary Deletion** (Deleting working glossary before replacement is READY) | Leaves translations without a glossary during creation windows or upon creation failures. | Zero-downtime Blue-Green replacement: provision alternating slot (`-a` / `-b`), verify `READY`, then retire old slot. |
| **Unbounded UUID Overflow Slots** (`sess-{token}-{uuid}`) | Exhausts the regional 1,000 glossary quota in `us-central1` during repeated failures. | Strict 2-slot bound: identify and retire the older superseded slot via `submit_time` before provisioning replacement. |
| **Overwriting Unversioned Staged TSVs in GCS** | Overwrites known-good terminology before the replacement is verified live, breaking rollback restoration. | Versioned GCS object paths (`.../{slot}_{version}.tsv`) preserving the prior input URI until cleanup. |
| **Lossy Transliteration of Non-Latin Characters in Fallbacks** | Alters translated text and misrepresents scholarly and philosophical terminology. | Dynamic 16-bit CID allocation with embedded TrueType font programs and `/ToUnicode` CMaps. |
| **Raw UTF-16BE Content Streams with `/Identity` CIDToGIDMap** | Treats Unicode code points as glyph IDs and splits supplementary plane characters ($> \text{U+FFFF}$) into unrenderable surrogate CIDs. | Dynamic sequential CID allocation with format 4/12 `cmap` parsing and dynamic `/CIDToGIDMap` stream objects. |

---

## 5. Documentation & Specification Hierarchy

* **Specification Organization**: All feature specifications, designs, and task plans must reside in topical subdirectories under `.kiro/specs/` (e.g., `.kiro/specs/gcp-migration/`, `.kiro/specs/<feature-name>/`).
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
