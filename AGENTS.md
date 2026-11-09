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
* **Non-Seekable Stream Multi-Pass Isolation**: When performing multi-pass operations (e.g., text extraction followed by raster image generation in `DualPaneViewerController`), services MUST NOT pass an original non-seekable source into multiple independent stream consumers. Instead, pass the already-normalized seekable `BinaryIO` yielded by the outer `open_pdf_stream` context manager and ensure stream position rewinding (`seek(0)`) before and after sub-operations.
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

### 2.12 GCP-Only Translation & Failed Page Re-run Invariant
* **Sole Translation Pipeline (GCP-Only, D2)**: Google Cloud Document Translation Advanced (v3) is the exclusive translation engine for PhenomenalLayout. The legacy local plaintext fallback engine (`services/fallback_translator.py`) has been permanently retired under ADR 0002.
* **Transparent Failed Page Surfacing**: When batch document translation reports partial layout parsing failures (`failed_pages > 0`), the system MUST NOT attempt local plaintext synthesis, character approximation, or composite font slicing. Instead, the completion summary carries `failed_pages` directly to the scholar.
* **Isolated Re-Run Submissions**: The frontend surfaces an explicit warning banner offering a 1-click **Re-run translation** action. Re-runs submit a fresh `POST /book/translate` request whose `book_id` is suffixed per attempt (e.g. `{book_id}-r2`, `-r3`). Each attempt writes to its own isolated GCS output prefix (`outputs/{book_id}-r2/`), ensuring partial outputs from earlier sessions remain independently downloadable.

### 2.13 Canonical Helper Routing & DRY Invariants
* **No Bespoke Infrastructure Duplication**: Code across all services MUST NOT introduce inlined or bespoke implementations of core cloud, storage, TSV, or descriptor algorithms. All components must route through the canonical modules:
  1. **GCS URI Parsing & Deletion**: Use `utils.gcp_helpers.parse_gcs_uri` and `utils.gcp_helpers.delete_gcs_blob`.
  2. **GCP Exponential Backoff & Transient Retry**: Use `utils.gcp_helpers.retry_gcp_call` or `@retry_gcp_operation`. Must apply truncated exponential backoff with $\pm 20\%$ random jitter, covering `ResourceExhausted` (429), `ServiceUnavailable` (503), `InternalServerError` (500), gRPC codes 8/14, and Drive `HttpError`.
  3. **GCP Regional Glossary Naming**: Use `utils.gcp_helpers.format_gcp_glossary_name`.
  4. **RFC 4180 TSV Escaping & Serialization**: Use `utils.tsv_utils.escape_rfc4180_field` (with early-return fast-path for unquoted tokens) and `utils.tsv_utils.format_tsv_bytes`.
  5. **Polymorphic PDF Streaming**: Use `utils.pdf_stream.open_pdf_stream` context manager to guarantee deterministic closure of internally opened file descriptors.
  6. **Crash-Safe File Persistence**: Use `utils.file_handler.atomic_write_json`, `atomic_write_text`, or `atomic_write_bytes` to stage writes via `.tmp` and `os.replace`.
* **Backward-Compatibility Shims**: When deprecating inlined service helpers, retain delegating shims where required to preserve existing public method interfaces.

### 2.14 German Morphological Compound & Derivational Suffix Invariants
* **Strict Derivational Adjective Exclusion**: When identifying German compound nouns (`is_german_compound_word`), detection algorithms MUST explicitly reject single derived words ending in adjectival/adverbial derivational suffixes (`-lich`, `-isch`, `-haft`, `-ig`, `-bar`, `-los`) and their inflectional/superlative paradigms (`-e`, `-er`, `-en`, `-es`, `-em`, `-st`, `-ste`, `-stem`, `-sten`, `-ster`, `-stes`).
* **No False Linking Morpheme Matching**: Derivational suffixes (e.g., `menschlich`, `körperlicher`, `wesentliche`, `natürlichen`) MUST NOT be classified as compound nouns by generic linking regexes (`Fugenelemente` such as `s`, `en`, `er`). Suffix-based filtering MUST precede linking element heuristics.
* **Pre-compiled Module-Level Expressions**: All linguistic regex patterns (`_PHILOSOPHICAL_PREFIX_RE`, `_STANDARD_LINKING_RE`, `_COMMON_DERIVATIONAL_SUFFIXES_RE`) MUST be compiled at the module level to eliminate per-call regex compilation overhead on high-throughput candidate streams.

---

## 3. Modal Labs Serverless Deployment Architecture
* **Framework**: Deployable as a serverless ASGI web app (architectural deployment specification under `TASK-5.3` / `modal_app.py`, `@modal.asgi_app()`).
* **Compute Tier**: Must operate efficiently within Modal Labs' $30/month free compute tier by enforcing automatic scale-to-zero when idle (`scaledown_window=300`).
* **Storage**: Persistent storage must utilize `modal.Volume` strictly for user metadata and terminology storage (`/data/`).

---

## 4. Deprecated Patterns & Deny List (Strictly Prohibited)

Agents must NEVER introduce or write code that relies on the following deprecated legacy systems:

| Prohibited Component / Pattern | Reason | Required Modern Replacement |
| :--- | :--- | :--- |
| **Custom Canvas Reconstruction** (Legacy ReportLab canvas drawing; former *services/pdf_document_reconstructor.py* [deleted under ADR 0001]) | Heuristic font-scaling and box expansion broke tables and figures. | Rely on Google Cloud Document Translation, which natively generates complete, layout-preserved PDFs. |
| **Dedicated GPU OCR Workers** (Modal Dolphin OCR instances; former *services/dolphin_client.py* [deleted under ADR 0001]) | High operational complexity and cost. | Outsource OCR and document layout parsing directly to Google Cloud. |
| **Dynamic Programming Layout Placement** (`core/dynamic_layout_engine.py` [deleted under ADR 0001]) | Fragile heuristics and technical debt. | Cloud Translation handles typography scaling and line wrapping natively. `core/dynamic_programming.py` is retained as a live dependency of the language, validation, choice, and middleware engines. |
| **Third-Party Auth Middleware** (Auth0, Clerk, Firebase) | Unnecessary SaaS dependency, cost, and complexity. | Use native client-side Google Identity Services (GIS) OAuth with `drive.file` scope. |
| **Storing Book PDFs on Host Disk** | Memory exhaustion and disk bloat on serverless instances. | Stream directly to/from user GCS bucket and Google Drive. |
| **Absolute Local Worktree Links & External URL Formatting** (`file:///` paths, absolute GitHub URLs) | Breaks portability across machines and GitHub UI; triggers reviewer link linting. | All internal documentation links must be repository-relative (`.kiro/specs/...`, `docs/adr/...`). External issues and PR references MUST be formatted as plain text tokens (e.g. `gradio-app/gradio#14005`, `#14018`), NEVER absolute hyperlinks. |
| **Blocking Sync I/O in Async Paths** | Degrades throughput on multi-chapter books. | Use `asyncio` and non-blocking streaming I/O for GCS uploads and LRO polling. |
| **Hardcoded Credentials or `.env` Commits** | Security vulnerability. | Use session-scoped BYOK vaults or Google Cloud Application Default Credentials (ADC). |
| **Premature Glossary Deletion** (Deleting working glossary before replacement is READY) | Leaves translations without a glossary during creation windows or upon creation failures. | Zero-downtime Blue-Green replacement: provision alternating slot (`-a` / `-b`), verify `READY`, then retire old slot. |
| **Unbounded UUID Overflow Slots** (`sess-{token}-{uuid}`) | Exhausts the regional 1,000 glossary quota in `us-central1` during repeated failures. | Strict 2-slot bound: identify and retire the older superseded slot via `submit_time` before provisioning replacement. |
| **Overwriting Unversioned Staged TSVs in GCS** | Overwrites known-good terminology before the replacement is verified live, breaking rollback restoration. | Versioned GCS object paths (`.../{slot}_{version}.tsv`) preserving the prior input URI until cleanup. |
| **Gradio Web Interface** (`ui/gradio_interface.py` [deleted under ADR 0002 / Track A]) | Upstream Pillow version pinning caused 41 open Dependabot alerts at deletion time; duplicated API functionality. | Bespoke zero-build vanilla ES modules SPA (`static/`) served directly by FastAPI. |
| **Local Fallback Translation Engine** (`services/fallback_translator.py` [deleted under ADR 0002 / Track B]) | High complexity TrueType font parsing, CMap unpacking, and ReportLab canvas drawing. | Google Cloud Document Translation is the sole translation pipeline; failed pages surfaced with re-run under `{book_id}-r2`. |
| **Lingo.dev Translation Stack** (`services/translation_service.py` / `services/mcp_lingo_client.py` / `services/parallel_translation_service.py` / `services/enhanced_translation_service.py` [deleted under ADR 0004 / Track C]) | Third-party API dependency, ambient `LINGO_API_KEY` env credential, MCP SDK surface, and bespoke provider orchestration duplicated the BYOK engine contract. | User-bound `GcpSyncTranslator` BYOK engines (ADR 0004 D2/D3) with fail-closed `GcpSyncCredentialsRequiredError`; `mcp` SDK pruned (`python-multipart` now explicit for FastAPI form routes). |
| **`reportlab` in any `requirements*.txt`** (removed from `requirements-dev.txt` under PR #147) | `reportlab` declares `pillow` as a hard `Requires`, reintroducing Pillow transitively even after all runtime removals. | Use `build_test_pdf(pages: list[str]) -> bytes` from `tests/conftest.py` for all PDF test fixtures. This stdlib-only helper produces valid PDF 1.4 bytes using Helvetica Type1 / WinAnsiEncoding; `pypdf.page.extract_text()` recovers the embedded strings verbatim. |
| **Legacy Generic Syntax** (`Generic[T]` base classes, manual `TypeVar` for intrinsic type parameters) | Python floor is 3.12+ (ADR 0003); ruff `UP047`/`UP049` are error-tier in the `UP` group and fail CI on legacy generics. | PEP 695 intrinsic type parameters — `class Foo[T]:` / `def f[T](...)`. See AGENTS.md §6.10. |

---

## 5. Documentation & Specification Hierarchy

* **Specification Organization**: All feature specifications, designs, and task plans must reside in topical subdirectories under `.kiro/specs/` (e.g., `.kiro/specs/gcp-migration/`, `.kiro/specs/<feature-name>/`).
* **Spec Suite Structure**: Follow the 3-document sequence:
  1. `design.md`: Architectural overview, component diagrams, data flows.
  2. `requirements.md`: User Stories, Functional/Non-Functional Requirements with Gherkin BDD scenarios.
  3. `tasks.md`: Test-driven implementation plan with explicit execution tracks and TDD criteria.
* **Architecture Decision Records (ADRs)**: Major architectural shifts must be documented in `docs/adr/XXXX-<title>.md`.
* **Live Filesystem Path Verification**: When authoring ADRs, documentation, task plans, or project rules based on design specs, agents MUST verify actual directory and file locations on the live filesystem (e.g., verifying `static/` rather than blindly adopting draft spec placeholders like `public/`).

---

## 6. Test-Driven Development (TDD) & Code Quality

* **Strict TDD Sequence**: All new services and bug fixes must be preceded by unit/integration tests with $\ge 90\%$ test coverage.
* **Type Annotations**: Strict Python type hints on all signatures (`from __future__ import annotations`, `typing.Optional`, `Path`, etc.).
* **Retry & Resilience**: All external GCP API interactions must implement exponential backoff retry for HTTP 429/503 errors.

### 6.1 Architectural Pushback & AI Review Governance
* **No Reflexive Acquiescence**: When automated AI reviewers (e.g., Greptile) flag intentional deprecations or deletions mandated by ADR 0001, agents MUST NOT restore obsolete code.
* **Defensive Decoupling**: Decouple legacy callers with `NotImplementedError` or `try...except ImportError` fallbacks, post clear architectural pushback citing the ADR/spec on the PR thread, and drive the review to completion without regressing migration goals.
* **Verify findings against live code before acting**: Greptile review status is a CI check on this repo; push-triggered re-reviews may lag (trigger one via the greptile MCP `trigger_code_review` when needed). Findings can be subtly wrong — in PR #158 a P2 claimed a wrapper `provider` parameter was a "no-op" when the downstream engine actually validates it; the correct fix was correcting the documentation wording, not the code. Either way, reply on the thread with the fix commit hash.

### 6.2 Test Fixture Reload & Submodule Hygiene (Python 3.13)
* **Safe Dynamic Reloading**: In tests that dynamically reload environment-dependent submodules via `importlib.reload(mod)`, always synchronize `sys.modules[mod.__name__] = mod` prior to calling `importlib.reload` to prevent Python 3.13 `sys.modules` identity desynchronization.
* **Reload After Environment Patches Exit**: Fixtures combining `patch.dict(os.environ)` with `importlib.reload` MUST run teardown reloads *after* the patch context exits. Reloading inside the patched context re-executes module-level `os.getenv(...)` constants (e.g., `api.rate_limit.RATE_LIMITS`) with the patched values and bakes them into the module for the remainder of the worker process, producing scheduling-dependent failures in unrelated tests (root cause fixed in PR #118).
* **Module-Family Identity Invariant**: The `sys.modules` entry, the parent-package attribute, and `from api.X import ...` bindings for the api/app family (`api`, `api.auth`, `api.routes`, `api.rate_limit`, `api.memory_routes`, `app`) MUST stay consistent. `api/__init__.py` imports no submodules, so a popped-and-re-imported `api` package object has none of the submodule attributes, and `importlib.reload(mod)` raises `ImportError: module ... not in sys.modules` whenever the entry and the package attribute reference different module objects. The conftest autouse `_module_family_identity_guard` fixture restores this identity after every test (via `tests.helpers.snapshot_module_family` / `restore_module_family`); test code that deliberately mutates module identity MUST let the guard clean up — never re-import or reload the bare `api` package, and never leave `sys.modules` surgery to persist past the test (root cause fixed for the parallel-suite flake family).
* **Usefixtures for Side-Effect Fixtures**: Test functions that require an environment setup fixture solely for setup/teardown side effects MUST use `@pytest.mark.usefixtures("<fixture_name>")` instead of unpacking unused arguments, preventing `ARG001`, `RUF059`, and `N806` linter violations.
* **Dead Documentation Pruning**: When completing dead code cleanups, all intermediate audit reports (e.g., historical unused code reports, `reports/dead_code_*.md`) that have been addressed MUST be pruned to prevent documentation drift.

### 6.3 Parallel Test Suite Execution & Inner-Loop Hygiene
* **Multi-Core Test Parallelization**: When running the full repository test suite (700+ tests), agents MUST leverage multi-core parallelism using `pytest -n auto` (or `-n <CPU_COUNT>`) via `pytest-xdist` to avoid multi-minute serial test timeouts and latency.
* **Inner-Loop Targeted Runs**: During rapid TDD red-green cycles, run targeted test files with `--no-cov` to verify individual behaviors quickly (< 1s) before triggering full multi-module coverage runs (`--cov=services --cov=utils --cov=models`).
* **Parallel-Failure Triage**: Under `-n auto` (xdist `dist=load`), worker scheduling is nondeterministic and failure sets rotate between runs. Before diagnosing a failure, rerun the failing test serially and diff the failure set against previous runs — a signature that appears once and moves between runs is environmental, not a regression. For state-leak repro, order node IDs in a single invocation (e.g., suspected polluter test first, victim test second): pytest runs node IDs in the order given.
* **Pre-Push CI-Exact Serial Parity**: CI runs serially with `pytest --maxfail=1 --disable-warnings`; order-dependent pollution that xdist masks surfaces there. Before pushing, run the CI-exact serial command once — the conftest autouse `_os_environ_quarantine` and `_auth_config_cache_reset` fixtures (established in PR #153) guard environment-variable and `AuthConfig` cache leakage between tests in serial mode; never delete, conditionally skip, or work around these fixtures, and NEVER resolve pollution by reintroducing `importlib.reload` teardowns (see §6.2).

### 6.4 Frontend Polling Hygiene & Idle Deactivation Invariant (NFR-03)
* **Bounded Polling**: Progress polling routines in the bespoke frontend (`static/js/polling.js`, `static/js/translate.js`) MUST use bounded intervals with exponential backoff on transient errors.
* **Mandatory Deactivation**: Polling MUST be dynamically cancelled and deactivated upon translation completion (`is_done == true`), unrecoverable errors, or when the user navigates back to an idle state. Polling loops MUST NEVER run indefinitely during idle or completed states.

### 6.5 Developer Tooling Scope vs. Runtime Application Architecture
> [!NOTE]
> This repository enforces a **CLI-first, stateful-MCP-sparing architecture** strictly for **Software Engineering Agents (SEAs) and developer workflows** (version control, PR management, testing, builds, containers, and environment inspection). The **runtime application itself** operates entirely through its native platform SDKs and in-process architecture (`google-cloud-translate`, `google-cloud-storage`, `pypdf`, `fastapi`, `modal`); review agents must **never** conflate developer tool routing with runtime application architecture or demand that runtime services shell out to CLI binaries.

### 6.6 API Test Authentication Bypass & Custom Router Caveat
* **Dependency Overrides Do Not Reach Memory Routes**: `/api/v1/memory/*` routes are served through custom `_IncludedRouter` wrappers whose captured auth dependency predates sibling tests' module reloads — `app.dependency_overrides` silently never engages for them (verified by instrumentation in PR #116). Tests that need unauthenticated access to these routes MUST patch `MEMORY_API_ENABLE_AUTH=false` via `patch.dict(os.environ, ...)` instead; `AuthConfig.enable_auth` re-reads the live environment on every request, so this bypasses stale module instances and router wrappers alike. Do not "fix" such fixtures by re-keying `dependency_overrides` — that approach was attempted and empirically disproven.

### 6.7 Dependency Pruning Completeness — Setup Script Sweep
When removing a runtime dependency from `requirements.in`, `pyproject.toml`, or any package manifest:
1. **Grep setup and CI scripts** for stale import probes referencing the removed package before staging the manifest change:
   ```bash
   grep -rn "import <retired_pkg>\|python -c.*import <retired_pkg>" \
     scripts/ Makefile justfile .github/workflows/ tests/conftest.py 2>/dev/null
   ```
2. For each match, replace the stale probe with the closest surviving peer from the same install tier (e.g., replace a retired UI dep with a core runtime dep such as `pypdf`).
3. This sweep is **mandatory before running `uv pip compile` or staging the pruning commit** — a broken setup-script health check is indistinguishable from a broken install.
4. Scope: `scripts/*.sh`, `Makefile`, `justfile`, `.github/workflows/*.yml`, `tests/conftest.py`, any `python -c "import <pkg>"` one-liners in CI steps.

### 6.8 Backward-Compat No-Op Deprecations — Mandatory Docstring Update
When a method's active behavior is removed but its public signature is intentionally preserved for backward compatibility (silenced via `_ = (arg1, arg2)`):
1. The **docstring MUST be updated in the same commit** that introduces the no-op silencing.
2. The updated docstring must:
   - State the new actual behavior (e.g., `"Returns text only. Image rendering has been removed under ADR 0002."`).
   - Mark each no-op argument as deprecated, for example:
     ```
     render_images (bool): Deprecated no-op. Retained for backward
         compatibility only. Has no effect; images are no longer rendered.
     dpi (int): Deprecated no-op. Retained for backward compatibility only.
     ```
3. This invariant applies to public and private methods alike. Docstring drift on a `_ = (...)` change is a Greptile P1 (misleading API contract) — verified in PR #146 review.

### 6.9 PDF Test Fixture Standard — `build_test_pdf` over `reportlab`
All test fixtures that require in-memory PDF bytes MUST use the shared helper
`build_test_pdf(pages: list[str]) -> bytes` from `tests/conftest.py`.

```python
from tests.conftest import build_test_pdf

pdf_bytes = build_test_pdf(["Page 1 text", "Page 2 text"])
```

**Rationale**: `reportlab` declares `pillow` as a hard `Requires` dependency,
reintroducing Pillow into the developer environment even after all runtime
removals. `build_test_pdf` is a stdlib-only raw PDF 1.4 writer (no imports
beyond `io`) that produces valid PDFs whose text is recoverable by
`pypdf.page.extract_text()` — the same extractor used in production services.

**Rules**:
1. Never add `reportlab` back to `requirements-dev.txt` or any
   `requirements*.txt` file. `test_deployment_config.py::test_minimum_dependency_pins_present`
   enforces this at CI level.
2. For multi-page PDFs, pass one string per page: `build_test_pdf(["p1", "p2"])`.
3. For PDFs needed as file paths (not bytes), write the result via
   `tmp_path / "name.pdf"` and call `.write_bytes(build_test_pdf([...]))`.
4. The helper encodes text as WinAnsiEncoding (Latin-1 range). All ASCII and
   standard Western European characters (including German umlauts) are
   supported. Do not pass characters outside Latin-1 without first verifying
   encoding compatibility.

Established in PR #147 — verified against 752-test suite at 70.75% coverage.

### 6.10 Python Floor & PEP 695 Generic Syntax Invariant
* **The supported floor is whatever `requires-python` declares in `pyproject.toml`** (currently the Python 3-series floor; see ADR 0003). Code that must parse below that floor is out of policy; do not "restore compatibility" by downverting PEP 695 syntax.
* **PEP 695-only generics**: new generic classes/functions MUST use intrinsic type parameters (`class CacheEntry[V]:`, `def _run_coro_sync[T](...)`). Legacy `class Foo(Generic[T])` and manual `TypeVar` declarations are prohibited — ruff `UP047`/`UP049` (error tier, `UP` group in `[tool.ruff.lint] select`) fail CI on them. Live examples: `core/dynamic_programming.py`, `services/glossary_sync_manager.py`, `services/philosophy_enhanced_translation_service.py`.
* **Coordinated version bumps only**: any Python minor-version bump must update ruff/black `target-version`, mypy `python_version`, CI `python-version`, `classifiers`, and `requires-python` together — drift between those five surfaces is what produced the ADR 0003 inconsistency. Same for README Prerequisites/Requirements and CONTRIBUTING "Development environment".

### 6.11 Persisted Timestamp Normalization Invariant (Legacy Naive Rows)
* **Legacy rows carry naive timestamps**: sessions/choices persisted before the UTC migration were written by `datetime.now()` (naive, UTC-encoding on Modal/CI hosts); post-migration writes are aware (`datetime.now(UTC).isoformat()`). Both formats coexist indefinitely in user databases.
* **Normalize before arithmetic**: any subtraction/comparison of a *persisted* timestamp against a `datetime.now(UTC)` value MUST first coerce naive values via the `_ensure_utc_aware` pattern (`tzinfo is None → replace(tzinfo=UTC)`; see `services/user_choice_manager.py`, precedent `services/parallel_translation_service.py`). Never assume fresh deployments have only aware rows.
* **Never treat comparison TypeError as a data-validity signal**: the pre-fix bug was an `except (ValueError, TypeError)` fallback that misread the aware-minus-naive `TypeError` as "invalid timestamp → expired", falsely expiring fresh ACTIVE sessions, and a `except ValueError` miss that emptied `_check_invalid_sessions` via the outer handler. Catching must be narrowed to what the operation actually raises after normalization.
* **DB-level lexical comparisons**: `ChoiceDatabase.cleanup_expired_sessions` compares ISO strings in SQL; mixed aware/naive lexical ordering is only wrong at exact sub-second boundaries (immaterial for hour-scale expiry policies). Prefer manager-level normalization over row-level SQL timestamp surgery.

Established in PR #153 — verified against the 761-test suite in both parallel (`-n auto`) and CI-exact serial modes.

### 6.12 Formatting & Type Gates — Ruff-Only CI (No Black)
* **CI gates are exactly `ruff check .` + `mypy .`** (`.github/workflows/ci.yml`); there is no black gate. Do NOT run mechanical black reformat passes: a full reformat split single-line `# noqa`-carrying fixture definitions into multi-line defs, tripping `ARG001`/`RUF100` and breaking the ruff gate (attempted and reverted in PR #158). Make surgical edits that match the surrounding style instead.
* **Pre-push gate parity**: run `ruff check .`, `mypy .` (local mypy version must match the CI pin), and the CI-exact serial pytest command (§6.3) before every push.

### 6.13 Dependency Eradication Sweep Discipline
* **Case-insensitive greps only**: env vars are uppercase (`LINGO_API_KEY`), module names lowercase (`mcp_lingo_client`); case-sensitive sweeps missed the env var twice during ADR 0004 Track C.
* **Include relative-import forms** (`from .translation_service import …`) — module-path greps alone miss intra-package delegation shims.
* **Sweep the full artifact graph, not just `services/`**: `examples/`, `scripts/` (incl. `scripts/verify/`), `docs/` (incl. `docs/fixes/`), tests, `.env.example`, steering docs, and review-agent configs. Companion artifacts are one removal unit — the MCP timeout verify script and its `docs/fixes/MCP_LINGO_TIMEOUT_CONFIGURATION.md` write-up were split across two sweeps before the doc was caught.
* **Classify residual hits instead of purging blindly**: enforcement nets (`tests/test_lingo_eradication.py`), ADRs, executed specs (`.kiro/specs/…`), historical quest records (`.qoder/quests/`), and "replaces the X-era test" docstrings legitimately mention retired stacks. Only *operational* docs describing deleted components are drift — delete them (§6.2); never rewrite history.
* **Extend the negative-sweep net red-first**: add each newly discovered artifact path to `_LEGACY_FILES` in `tests/test_lingo_eradication.py`, verify the assertion fails, then remove the artifact and verify green.

### 6.14 Deprecated-but-Forwarded Parameter Contracts
* §6.8 covers parameters silenced as true no-ops. Distinct case: a backward-compat parameter that is still **forwarded** to a downstream validator. Documentation (docstrings AND `docs/`) must state the accepted values and the failure mode — never claim "no effect".
* **Precedent**: `provider` in `services/philosophy_enhanced_translation_service.py` forwards to `GcpSyncTranslator._validate_provider` (`services/gcp_sync_translation_service.py:80,142`), which accepts only `None`/`"gcp"`/`"auto"` and raises `ValueError` on anything else (e.g. the retired `"lingo"`). The wrapper docstrings say "validated, otherwise ignored — one-provider tier"; all parameter documentation must match that contract.

### 6.15 Dependency Sync Is Exact — Compiled Closures Only
* **`pip-sync` enforces exact equality**: `scripts/sync-deps.sh dev` runs `pip-sync requirements.txt requirements-dev.txt` (both uv-compiled closures — runtime from `requirements.in`, dev from `requirements-dev.in`); `prod` syncs `requirements.txt` only. Anything installed in the venv that is not an explicit pin in that union is **uninstalled**.
* **pip-sync's desired set is explicit pins only (mechanism)**: `piptools.sync.diff` uninstalls every installed distribution whose key is not itself a pin in the synced files; only pip/pip-tools' own dependency trees are exempt. Transitive dependencies of a hand-written manifest are therefore structurally orphaned — uninstalled whenever present, and silently restored by the install step's dependency resolution (`pip install -r`, no `--no-deps`) whenever a top-level pin is missing. That oscillation's stable fixed point is a broken environment (observed: `execnet`/`coverage`/`pluggy` purged, pytest unrunnable after two syncs). Both pip 25.3 and pip 26.x exhibit it identically — the pip version is a red herring; the manifest structure is the defect.
* **Every pip-sync input must be a compiled closure**: `requirements-dev.txt` is generated by `uv pip compile requirements-dev.in --constraint requirements.txt -o requirements-dev.txt`. The constraint keeps transitive pins shared with the runtime tier on identical versions — pip-sync's `merge` raises `IncompatibleRequirements` on conflicting pins across the two files. Never hand-edit `requirements-dev.txt`; edit `requirements-dev.in` and recompile (`scripts/update-deps.sh` regenerates both tiers).
* **Shared-venv skew**: the repo venv is shared across clones/worktrees. A sync executed against manifests that predate a new explicit pin silently removes that package (verified in PR #158: `python-multipart` — required at FastAPI route-registration time — vanished after a sync run against pre-T-3.2 manifests). Run dependency syncs from the tree whose manifests you are developing against, and regenerate compiled manifests (`uv pip compile`) in that same tree after every manifest edit.
* **Verification over blanket reinstalls**: after every sync or manifest change, verify with `pip check`, the eradication net (`pytest tests/test_lingo_eradication.py`), and an app-import probe. Install ad-hoc (`uv pip install <pkg>`) only packages a probe proves missing — a standing `uv pip install -r …` reinstall step masks skew instead of fixing it.

Established in PR #158 — eradication sweep, Greptile review cycle, and venv realignment lessons from ADR 0004 Track C. Extended with the compiled-closure invariant after pip-sync's desired-set mechanism was confirmed from the `piptools/sync.py` source and double-sync stability was verified under both pip 25.3 and pip 26.x.

### 6.16 Version-Free Rules Doctrine (constraints live in manifests only)

* **Single source of constraints**: Constraint-bearing dependency versions (floors, ceilings, exact pins) MUST be stated exactly once, in the manifests (`requirements.in` → `requirements.txt`, `requirements-dev.in` → `requirements-dev.txt`, `pyproject.toml`). The advisory source of truth is the vendor's declared dependency metadata (PyPI `requires_dist` / `importlib.metadata`).
* **Prose is series-only**: Rulebooks (`AGENTS.md`, `CONTRIBUTING.md`, README claims, `.greptile/rules.md`) MUST reference version *series* only (e.g. "pytest 9.x", "the Python 3-series floor"); quoting package floors/ceilings/pins in prose is prohibited — they age into falsehood. Precedent (dated drift evidence, audited Nov 2026): CONTRIBUTING.md's asyncio guidance still spoke of a pytest-8-era floor on "pytest 8" while the dev manifest had moved two major lines ahead to the pytest 9 pin; README.md quoted the compiled closure's pins byte-for-byte, guaranteeing drift on every `./scripts/update-deps.sh` run.
* **Exceptions**: dated decision records (`docs/adr/*.md`) and executed specs (`.kiro/specs/**`, `.qoder/quests/**`) are immutable historical snapshots and may quote era-specific versions. Within living rulebooks, historical numbers may appear ONLY when explicitly labeled "dated drift evidence". `CHANGELOG*` and dated fix notes (`docs/fixes/**`) are likewise exempt.
* **PR discipline**: a diff that changes a manifest constraint MUST NOT also edit rule-prose version numbers (and vice versa); dependency PRs MUST verify resolvability (`pip install --dry-run -r requirements.txt -r requirements-dev.txt`, or `./scripts/sync-deps.sh dev`) before commit.
* **Pin mirroring with FastAPI (Version-Free invariant)**: fastapi declares its own range for `starlette` in its dependency metadata, and that declaration has moved across fastapi releases before (historical drift trail: README once carried a hardcoded literal starlette floor snapshot copied from the compiled closure at README era, while fastapi's active release declared a lower transitive floor — dated drift evidence, audited Nov 2026; never quote an era number as a standing constraint). Manifests and environments MUST keep `starlette` within the range declared by the dependency metadata of the exact fastapi release pinned in `requirements.txt` (verify that release's `requires_dist` — the PyPI stored metadata for that version, or `importlib.metadata.requires("fastapi")` on the installed distribution; the compiled closure's `# via` comments only name the parent package and carry no allowed range, so they do not substitute for dependency-metadata verification). Any PR touching a mirror package MUST resolve the full set against the manifest before commit and MUST re-sync the mirror in the same PR when fastapi's declared range moves.
