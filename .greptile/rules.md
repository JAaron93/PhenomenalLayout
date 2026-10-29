# PhenomenalLayout: Greptile Reviewer Constitution & Behavioral Guardrails

## 1. Zero Contradictory / Oscillating Reviews (Anti-Oscillation Directive)
- Reviewers MUST NOT contradict previous review cycles. If a change was implemented to satisfy a Greptile review finding (e.g., enabling local workflows when `MEMORY_API_ENABLE_AUTH=false`), the reviewer MUST NOT flag the resolution from the opposite perspective in the subsequent cycle.
- Once a review thread is marked resolved and verified by test coverage, do not re-flag related defensive code unless there is a verified, critical code execution or injection exploit.

## 2. Authentication: Local Development vs. Production Multi-Tenancy
- **Local Dev Mode (`MEMORY_API_ENABLE_AUTH=false`)**: When authentication is globally disabled in configuration, the engine is operating in a trusted single-tenant local environment (or CI test suite). In this mode, do NOT flag callers passing `user_id` as a "multi-tenant security bypass."
- **Production Mode (`MEMORY_API_ENABLE_AUTH=true`)**: In production, authentication is enforced via JWT or API keys. Verify that unauthenticated callers cannot modify other users' resources.
- **Shared Namespaces**: In all modes, shared static namespaces (`default_user`, `anonymous`, `local_user`) must be rejected (`400 Bad Request` / `PermissionError`) to ensure user state isolation.

## 3. Gradio Interface Architecture
- Gradio operates as an interactive frontend where components pass values through Python function arguments (`user_id`, `auth_token`) and session state.
- Do NOT flag Gradio UI callbacks for accepting form values or helper authentication functions (`_authenticate_gradio_caller`). Gradio callbacks do not receive raw incoming HTTP `Authorization` headers directly from the browser.

## 4. Architectural Constitution (AGENTS.md & ADR 0001)
- **Zero Host PDF Storage**: All book PDFs reside in user GCS buckets or Google Drive; never request saving PDFs to host disk.
- **BYOK Credential Isolation**: Service account keys are ephemeral in memory; never suggest persisting them to SQLite or disk.
- **Regional Quotas & Blue-Green Glossary**: Tier 2 glossaries use blue-green alternation bounded to 2 regional slots (`-a`/`-b`) in `us-central1`. Staged session TSVs in GCS use versioned names (`{slot}_{version}.tsv`) with rollback restoration on failure.
- **Unicode & CID Font Integrity**: Fallback rendering must use 16-bit sequential CIDs and format 4/12 TrueType CMaps, never lossy ASCII transliteration or surrogate code units.
- **GCS Staging Lifecycle**: Source PDFs in `inputs/` must have an unconditional 7-day auto-delete lifecycle policy verified on the user bucket, raising `RuntimeError` on verification or patching failure.
- **Zero Resource Leakage & Stream Isolation**: Deterministically close file descriptors with `try...finally` or context managers. Normalize non-seekable streams via `open_pdf_stream` context manager and rewind stream position (`seek(0)`). Optional services in availability registries must export boolean flags in `__all__`.
- **Canonical Helper Routing & DRY**: Core cloud, storage, TSV, streaming, and atomic persistence must route through `utils/` foundation modules (`utils.gcp_helpers`, `utils.tsv_utils`, `utils.pdf_stream`, `utils.file_handler`). Never introduce bespoke duplicated implementations.
- **German Morphological Compound & Derivational Suffixes**: Single derived words ending in derivational suffixes (`-lich`, `-isch`, `-haft`, `-ig`, `-bar`, `-los` and inflected paradigms) must be excluded before checking linking elements (`Fugenelemente`). Regex patterns must be pre-compiled at module level.
- **Completed Eradication (ADR 0001)**: The `dolphin_ocr/` package, `core/dynamic_layout_engine.py`, and the legacy Dolphin-era services/scripts have been fully removed. Dolphin references legitimately remain only as history in the README migration table, ADR 0001, and `.kiro/specs` / `.qoder/quests` records. Reviewers must NEVER request their restoration, and defensive-decoupling `try...except ImportError` fallbacks for them are obsolete — flag any re-introduction instead.

## 5. Evaluation, Mock Fixtures & Test Suite Invariants
- **Parallel Test Execution**: The repository test suite leverages multi-core parallelism (`pytest -n auto`). Do NOT flag test isolation patterns designed for concurrent execution.
- **Module-Family Identity Guard**: The conftest autouse `_module_family_identity_guard` restores `sys.modules` entries and parent-package attributes for the api/app family after every test. Do NOT flag it as redundant cleanup or request its removal because individual fixtures "already restore" — fixtures that pop/delete/re-import api-family modules desynchronize package attributes from `sys.modules` (api/__init__.py imports no submodules), which is the root cause of the historical parallel-suite flake family. Do not suggest bypassing it with raw `sys.modules` mutation that persists past a test.

