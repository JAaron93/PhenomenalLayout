# Tasks: Lingo.dev Retirement — GCP Sync Engine

Sequence per spec: `design.md` → `requirements.md` → this file.
Status discipline (zero-drift invariant): a task may be marked
`[STATUS: COMPLETE]` **only** when the repository artifacts (code, tests,
manifests, docs) verifiably satisfy its acceptance criteria.

## Execution Track Overview

| Track | Title | Depends on |
| :--- | :--- | :--- |
| A | GCP Sync Engine (new services) | — |
| B | Handler & API Rewiring | A |
| C | Eradication & Pruning (code/deps/governance) | B |
| D | Test & Documentation Parity + CI Gates | B (parallel-friendly with C) |

```text
Track A ──► Track B ──► Track C ──► Track D (final green + docs)
                    └──► Track D-partials (test rewrites race with C)
```

---

## Track A — GCP Sync Engine

> [!TIP]
> PARALLEL EXECUTION: T-1.1 and T-1.2 are independent test files; CI/docs repos
> (T-1.7) can proceed in parallel with engine code.

* **[STATUS: COMPLETE] T-1.1 — Failing tests: engine contract (RED)**
  - Verified: `tests/services/test_gcp_sync_translation_service.py` RED on
    collection (ModuleNotFoundError) before implementation.
  - Write `tests/services/test_gcp_sync_translation_service.py` covering:
    `translate_text`, ordered `translate_batch` chunking (batch-size aware),
    `translate_document` preview path, `get_available_providers() == ["gcp"]`,
    stable statistics keys, `close`/`aclose` no-op safety.
  - Fake `BYOKCredentialsManager` + monkeypatched `translate_v3` client facade
    (no real GCP). Tests must FAIL before implementation.
  - **Depends on:** — (first TDD step; ADR 0004 D1/D4)

* **[STATUS: COMPLETE] T-1.2 — Failing tests: fail-closed + resilience + terminology (RED)**
  - Verified: 17 tests cover the fail-closed gate, retry routing through
    `utils.gcp_helpers.retry_gcp_call`, terminology wrap/strip parity, and
    off-loop execution via `asyncio.to_thread`.
  - Missing/invalid credentials → typed `GCP_CREDENTIALS_REQUIRED` error (503 mapping surface).
  - Transient GCP errors → retry via `utils.gcp_helpers.retry_gcp_call`
    (assert backoff invoked; no bespoke loops).
  - Terminology `terminology_map` word-boundary substitution parity
    (port behavior from `services/translation_service.py:603`).
  - Async non-blocking: verify engine calls run via `asyncio.to_thread`
    (assert no direct sync call on the event loop).
  - **Depends on:** — (parallel with T-1.1)

* **[STATUS: COMPLETE] T-1.3 — Implement `GcpSyncTranslator` + `GcpSyncTranslationService` (GREEN)**
  - Verified: `services/gcp_sync_translation_service.py` implemented per
    design §3/§5; targeted run 17/17 green after red phase.
  - New `services/gcp_sync_translation_service.py` per design §3/§5:
    `projects/{project}/locations/us-central1`, batch chunking by
    `TRANSLATION_BATCH_SIZE`, `DocumentInputConfig` preview path.
  - Borrow cached `translate_v3.TranslationServiceClient` from
    `BYOKCredentialsManager.get_translation_client` — no bespoke clients.
  - Terminology port + fail-closed gate + retry routing.
  - Strict type annotations; PEP 695 syntax where generics apply (AGENTS §6.10).
  - **Depends on:** T-1.1, T-1.2

* **[STATUS: COMPLETE] T-1.4 — Package export symmetry (AGENTS §2.10, ADDITIVE)**
  - Update `services/__init__.py` **additively**: add `GcpSyncTranslationService`,
    `GcpSyncTranslator`, `GcpSyncCredentialsRequiredError` exports plus the
    `GCP_SYNC_SERVICES_AVAILABLE` availability flag and `__all__` entry.
    (Zero-drift note: removal of the legacy `TranslationService` package export
    is deferred to Track B/T-3.1 — both exports coexist until the tree no
    longer imports the legacy module.)
  - Verified: `python -c "import services…"` reports
    `GCP_SYNC_SERVICES_AVAILABLE=True` with 42 registered services.
  - **Depends on:** T-1.3

* **[STATUS: COMPLETE] T-1.5 — Engine targeted green run**
  - Verified: targeted `--no-cov` run 17/17 green; scoped `tests/services`
    37/37; full `pytest -n auto` exit 0 with coverage 70.73% (gate ≥ 70%).
  - `pytest tests/services/test_gcp_sync_translation_service.py --no-cov` (< 2s inner loop),
    then full-suite parallel run `pytest -n auto` to detect regressions early.
  - **Depends on:** T-1.3, T-1.4

---

## Track B — Handler & API Rewiring

* **[STATUS: COMPLETE] T-2.1 — Failing tests: request-path rewiring (RED)**
  - `/philosophy/translate` and `/translate` accept `user_id` + auth dependency
    (mirror `POST /book/translate` pattern at `api/routes.py:1458-1465`).
  - Missing-credentials 503 onboarding response.
  - Background job uses the engine bound at submission (`process_advanced_translation_job`
    gains an engine parameter; job closure never re-resolves identity).
  - Config endpoints unchanged: `get_available_providers`/`get_statistics`
    surface through `api/routes.py:160-203` (philosophy service intact).
  - Verified: `tests/test_translate_routes_byok.py` (10 tests: 422 without
    `user_id`, 401 unauthenticated, 503 + `GCP_CREDENTIALS_REQUIRED` fail-closed,
    engine/job binding, cross-identity 403, config-endpoint provider parity)
    and `tests/test_translate_content_engine_binding.py` (10 tests) — written
    RED first with 25 failing tests across the Track B surfaces.
  - **Depends on:** T-1.5

* **[STATUS: COMPLETE] T-2.2 — Rewire `core/translation_handler.py` (GREEN)**
  - Singleton becomes the non-translating statistics/config facade holding the
    BYOK manager reference + `translator_for_user(user_id)` registry.
  - Document job flow + upload hint string (`core/translation_handler.py:898`)
    updated to GCP v3 wording.
  - Replay `tests/test_translate_one_safety.py`,
    `tests/test_translate_content_philosophy_async.py`,
    `tests/test_translation.py` — patch points (`th.translation_service`,
    `th.` module vars) must keep working (AGENTS §6.2 module-family hygiene).
  - Verified: RED→GREEN with suite extensions —
    `tests/test_translate_content_engine_binding.py` 10/10 (fail-closed
    `GcpSyncCredentialsRequiredError` without user/engine, injected-engine
    resolution, credential-error never swallowed by the legacy fallback while
    transient errors still fall back to source text, philosophy mode wraps the
    user engine via `build_philosophy_service`, module-singleton patch point
    intact, job threading + fail-closed job error records, shared BYOK vault
    identity) and `tests/services/test_gcp_sync_translation_service.py` 23/23
    (Track A 17 + Track B compat 6: trailing `provider` positional accepted
    for `gcp`/`auto` and ValueError fail-closed otherwise, engine-level
    `get_available_providers`, legacy content-dict `translate_document`
    positional canonicalization with `progress_callback` parity).
    `tests/test_translate_one_safety.py` and
    `tests/test_translate_content_philosophy_async.py` pass unmodified except
    `test_non_philosophy_path_unchanged`, whose `th.translation_service.
    translate_batch` instance-method patch migrated to the ADR 0004 seam
    (stub engine bound via `translator=` — same assertions: only non-empty
    texts batched in order, empties and spacing preserved verbatim).
    Handler materialization: PEP 562 lazy `translation_service` attribute →
    `GcpSyncTranslationService` over `api.routes.get_byok_credentials_manager`
    (no second manager); `process_advanced_translation_job` now also re-stores
    mutated job dicts through `translation_jobs[job_id] = job` because
    `ThreadSafeTranslationJobs.__getitem__` returns shallow copies
    (`core/state_manager.py:197-216`) — fixes a pre-existing lost-update bug.
  - **Depends on:** T-2.1

* **[STATUS: COMPLETE] T-2.3 — `utils/document_errors.py` extension**
  - Add `GCP_CREDENTIALS_REQUIRED` with onboarding guidance message; wire
    through `get_error_message` consumers (`api/routes.py:66-71`).
  - Verified: engine error message carries a machine-readable
    `[GCP_CREDENTIALS_REQUIRED]` prefix, both route raise sites map to HTTP 503
    with the code prepended to the onboarding guidance; registry test updated
    to the 4-code set with an onboarding-message contract test (16/16 in
    `tests/test_document_errors.py` + `tests/services/test_philosophy_unbound_default.py`).
  - **Depends on:** T-2.1 (parallel with T-2.2)

* **[STATUS: COMPLETE] T-2.4 — Track B green run**
  - Targeted `--no-cov` inner loop, then `pytest -n auto`; fix any
    scheduling-dependent failures per AGENTS §6.3 triage (serial diff check).
  - Verified: targeted combined run 59/59 (engine + routes + doc-errors +
    unbound-default compat); legacy replay suites
    (`test_translate_one_safety`, `test_translate_content_philosophy_async`,
    `test_translate_content_philosophy_load`, `test_phase5_services`,
    `test_book_translation_orchestrator`) all green; full `pytest -n auto`
    green apart from one environmental timing flake
    (`test_rate_limiter_concurrent` — passed on serial rerun, moving-signature
    `dist=load` artifact per §6.3 triage) plus
    `test_philosophy_enhanced_integration::test_service_initialization`
    asserting the retired `"lingo"` provider — updated to the ADR 0004
    contract (`"gcp"`, single-provider registry); CI-exact serial
    `pytest --maxfail=1 --disable-warnings` exit 0 with coverage 71.52%
    (gate ≥ 70%).
  - **Depends on:** T-2.2, T-2.3

---

## Track C — Eradication & Pruning

> [!TIP]
> PARALLEL EXECUTION: C-1 (code deletion) is sequential after B; C-2 (dependency
> prune) and C-3 (governance docs) are mutually independent.

* **[STATUS: COMPLETE] T-3.1 — Delete Lingo service modules + orphans**
  - Verified: `tests/test_lingo_eradication.py` RED on collection before
    implementation (16 initial failures), then 19 passed at GREEN.
  - Verified: `examples/neologism_integration_example.py` and the dead
    delegation typing shim in `services/philosophy_enhanced_translation_service.py`
    (relative import missed by the first recon sweep) were caught by the
    extended net; `ruff` + `mypy .` + full `-n auto` replay (74.26% coverage)
    + CI-exact serial replay (74.27%) all green.
  - `services/translation_service.py`, `services/mcp_lingo_client.py`,
    `services/parallel_translation_service.py`, `services/enhanced_translation_service.py`.
  - `scripts/verify/verify_mcp_timeout_configuration.py`;
    repurpose/delete `scripts/run_tests_with_env.py` per sweep result.
  - Remove the legacy `TranslationService` package export block from
    `services/__init__.py` (deferred additive-then-remove pattern from T-1.4).
  - Delete legacy test modules: `tests/test_lingo_translator.py`,
    `tests/test_translation_service.py`, `tests/test_parallel_translation.py`,
    `tests/services/test_mcp_lingo_client.py`; rewrite Lingo sections of
    `tests/test_memory_leaks.py`/`tests/test_memory_leak_fixes.py` against the
    GCP engine; replace `tests/conftest.py` `lingo_translator` fixture +
    mock-key block (`conftest.py:184-193,210-211`).
  - Removal of examples: `examples/mcp_demo_file.txt`,
    `examples/parallel_translation_demo.py`,
    `examples/neologism_integration_example.py` (update or delete),
    `examples/README.md` Lingo sections.
  - Note: the shim sweep (`from .translation_service import`) is now covered
    by `TestPackageExportRemoved::test_philosophy_service_has_no_legacy_delegation_shim`.
  - **Depends on:** T-2.4

* **[STATUS: COMPLETE] T-3.2 — Dependency prune + manifest regen (AGENTS §6.7)**
  - Verified: §6.7 setup-script sweep clean (no `import mcp`/`import lingo`
    probes in `scripts/`, `Makefile`, `justfile`, `.github/`, `tests/conftest.py`).
  - Verified: deleted-mcp guard `TestDependencyPrune` RED (4 assertions), then
    GREEN; `python-multipart` restored as an explicit `requirements.in` dep
    (FastAPI `UploadFile`/`Form` routes need it at registration — previously
    a transitive of the removed MCP SDK only); regen diff strictly
    subtractive for the 11-pin MCP subtree, zero version bumps;
    `test_deployment_config.py::test_minimum_dependency_pins_present` green.
  - Remove `mcp>=2.2.0,<3.0` from `requirements.in:18`; run the mandatory
    setup-script sweep (`grep -rn "import mcp\|import lingo" scripts/ Makefile
    justfile .github/ tests/conftest.py`) and fix any stale probes.
  - Regenerate `requirements.txt` via `uv pip compile`; verify
    `test_deployment_config.py::test_minimum_dependency_pins_present` stays green.
  - Update `pyproject.toml:8` description + `:114` comment; keep `pillow`-free invariant (
    never reintroduce `reportlab`).
  - **Depends on:** T-3.1 (parallel with T-3.3)

* **[STATUS: COMPLETE] T-3.3 — Configuration & env eradication**
  - Verified: `TestConfigurationEradication` net (5 surfaces) RED × 6 pre-edit,
    then GREEN; README-assertion coupling handled by deleting
    `test_required_env_vars_documented_and_optionally_set` (would have failed
    the T-3.4 README sweep); `scripts/run_tests_with_env.py` repurposed per
    sweep result (was reporting "zero Lingo refs" only because the grep was
    case-sensitive); `tests/test_complete_integration.py` Lingo gate
    neutralized to `RUN_LIVE_INTEGRATION=1` (provider-string parity deferred
    to T-4.1).
  - `.env.example:1-19`: remove LINGO block (BYOK credentials are session-memory
    only per §2.3 — no env replacement needed).
  - `config/settings.py:393-394`: drop `LINGO_API_KEY` ("Only Lingo.dev" comment).
  - `app.py:4-5,181`: docwording → GCP-only.
  - **Depends on:** T-3.1 (parallel with T-3.2)

* **[STATUS: COMPLETE] T-3.4 — Governance codification (ADR 0004 D7)**
  - Verified: `.greptile/rules.md` §7 + `.greptile/instructions.md` §2.2
    mirror the Dolphin eradication sections (never request restoration;
    flag re-introductions; negative-sweep net named as the enforcement
    artifact); AGENTS.md §4 deny-list row added; README Lingo sections
    swept (~45-788 band) with the migration-table row added and the
    Lingo-era benchmark suite replaced by a historical note;
    `.kiro/steering/product.md:13` and `tech.md:82` reworded GCP-only.
  - Verified: philosophy-path docs parity —
    `docs/philosophy_enhanced_translation_api.md` now states the sync-tier
    mapping explicitly (neologism path rides GCP Translation v3's
    synchronous text API via user-bound `GcpSyncTranslator`; books use the
    async `batchTranslateDocument` pipeline), documents `provider` as a
    deprecated legacy routing argument validated by the engine — accepted
    values `None`/`"gcp"`/`"auto"` (default `"auto"`); any other value
    raises `ValueError` (4 param sites) — and replaces the multi-provider
    fallback error-handling example with fail-closed
    `GcpSyncCredentialsRequiredError` semantics;
    `docs/PHILOSOPHY_ENHANCED_TRANSLATION_ARCHITECTURE_COMPLETE.md` carries
    a historical pre-ADR-0004 banner (design history preserved, live
    contract pointers added).
  - Verified (final pre-merge sweep): full-repo case-insensitive Lingo
    sweep classified every residual hit as enforcement/history (net,
    ADRs, executed specs, `.qoder/quests/` records, "replaces the
    Lingo-era" docstrings, the `requirements.in` provenance comment) —
    except `docs/fixes/MCP_LINGO_TIMEOUT_CONFIGURATION.md`, an operational
    how-to for the T-3.1-deleted `mcp_lingo_client.py` (companion verify
    script already removed). Deleted under §6.2 dead-doc pruning; the
    negative-sweep net gained a 29th assertion for it (red-first).
  - `AGENTS.md`: §6.1 gained the verify-findings-against-live-code review
    discipline; new §6.12 (ruff-only CI gates, no black reformat passes),
    §6.13 (eradication sweep discipline incl. case-insensitive greps,
    relative imports, companion-artifact units, hit classification),
    §6.14 (deprecated-but-forwarded parameter contracts — `provider`
    precedent), §6.15 (dependency sync exactness and shared-venv
    manifest skew — corrected after review: `sync-deps.sh dev` passes
    both manifests to `pip-sync`; the observed `python-multipart` loss
    was exact-equality uninstall against pre-T-3.2 manifests, not
    dev-only resolution).
  - `.greptile/rules.md` + `.greptile/instructions.md`: Lingo Eradication
    section (mirror Dolphin section; never request restoration; flag
    re-introduction).
  - `AGENTS.md` deny-list row: "Lingo.dev translation stack
    (`translation_service.py`/`mcp_lingo_client.py`) [deleted under ADR 0004]".
  - README: migration-table row + remove Lingo sections (lines ~45-788 sweep).
  - `.kiro/steering/product.md:13`, `.kiro/steering/tech.md:82`: GCP-only wording.
  - **Depends on:** T-3.1 (parallel with T-3.2/T-3.3)

---

## Track D — Test & Documentation Parity + CI Gates

* **[STATUS: NOT STARTED] T-4.1 — Eradication regression net**
  - Grep-based test asserting no `lingo|mcp`-SDK references inside
    `services/`, `config/`, `api/` (negative sweep; mirrors Dolphin pollution tests).
  - Rewrite the legacy provider semantics in `tests/test_complete_integration.py`
    (`provider="lingo"` call sites, available-provider assertions) against the
    BYOK engine; its never-satisfiable Lingo gate is already neutralized to
    `RUN_LIVE_INTEGRATION=1` opt-in (T-3.3).
  - **Depends on:** T-3.1–T-3.4

* **[STATUS: NOT STARTED] T-4.2 — Coverage & CI parity**
  - Coverage ≥ 70% on `services`, `utils`, `models` (gate unchanged, ADR 0002 D6).
  - CI-exact serial run: `pytest --maxfail=1 --disable-warnings`;
    full parallel run `pytest -n auto` must also be green (AGENTS §6.3).
  - **Depends on:** T-4.1

* **[STATUS: NOT STARTED] T-4.3 — Flip ADR status + spec statuses (zero-drift)**
  - Flip `docs/adr/0004-retire-lingo-dev-translation-stack.md` to **Accepted**.
  - Mark completed tasks `[STATUS: COMPLETE]` **only where artifacts verify**.
  - Confirm no dead-code report drift (AGENTS §6.2 dead-doc rule).
  - **Depends on:** T-4.2

---

## Feature-Branch Doctrine

- All implementation work executes in an isolated git worktree on a feature
  branch (e.g. `feature/adr-0004-lingo-eradication`); commits on `main` are
  prohibited (global constitution §2).
- Progressive commit verification: run the targeted test suite after **every**
  commit (3-strike hard stop applies at < 90% pass after 3 attempts).
- Suggested PR granularity: (1) Track A engine, (2) Track B rewiring,
  (3) Tracks C+D eradication — each independently reviewable.
