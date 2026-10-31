# Tasks: Bespoke Frontend & GCP-Only Translation

Status: DRAFT · 2026-10-29 · Traceability: FR/NFR/US IDs from `requirements.md`; decisions D1–D6 from `design.md`.
Every task ends with its `- [ ]` verification boxes checked only when the repository state matches the description (zero-drift invariant).

## Execution overview

```
Track A (frontend, sequential)  ──> Track D (integration & publication)
Track B (fallback removal)      ──┘
Track C (raster + deps removal) ──┘   (C3 requires B1, C1, C2, A1)
```

> [!TIP] PARALLEL EXECUTION
> Tracks B and C start immediately after T0 and proceed in parallel with Track A.
> Only C3 (dependency/lockfile) is a join point: it requires the Gradio deletion (A1),
> fallback deletion (B1–B3), and raster-path deletion (C1–C2) to be complete first.

---

## Track A — Bespoke frontend (FR-01…FR-08, NFR-01…NFR-04)

### T0. Branch and harness
**Depends on:** nothing.
- [x] Create feature branch `feat/bespoke-frontend-gcp-only` from `origin/main` in an isolated worktree.
- [x] Create a Pillow-free baseline proof: `python -c "import app"` currently FAILS (documents the pre-change coupling; flipped by C3).
- [x] Add `pytest-playwright` to `requirements-dev.txt` and install Chromium for the sandbox (`playwright install chromium`).

### A1. App rewiring (FR-09 first half)
**Depends on:** T0.
- [x] TDD red: rewrite the mount test to assert `/` serves the SPA shell and `/ui` returns 404.
- [x] Remove `import gradio as gr`, `create_gradio_interface`, and the `/ui` mount from `app.py`; `main()` serves `static/index.html` at `/` via the existing `StaticFiles` mount (`html=True`).
- [x] Green: mount test passes; repository-wide grep shows zero `gradio` imports outside deleted files.

### A2. Frontend skeleton + auth (FR-08, NFR-01)
**Depends on:** A1.
- [x] TDD red: Playwright spec asserting token **and User ID** entry persist to `sessionStorage`, never `localStorage`; that an unauthenticated `/api/v1/vocabulary/{id}` call surfaces the 401 prompt; and that authenticated requests inject `user_id` in the shape each route requires (path for `/vocabulary/{id}` and `/book/jobs/{id}`, query for `/book/status`/`/book/resume`/`/book/download`/`/book/dual-pane`/`/byok/validate`/`DELETE /byok/credentials`, form data for `/book/translate`/`/book/pre-scan`, JSON body for `POST /byok/credentials`).
- [x] Implement `static/index.html`, `static/styles.css`, `static/app.js` entry, `static/js/api-client.js`, `static/js/auth.js` (D1, D5).
- [x] Green: Playwright auth spec passes; `api-client` attaches `Authorization: Bearer` / `X-API-Key` and the required `user_id` on every call.

### A3. Cost estimator + onboarding (FR-01, FR-02, US-01, US-02)
**Depends on:** A2.
- [x] TDD red: Playwright spec uploads a fixture PDF and asserts the itemized quote (per-page rate, staging, retention, tolerance) renders without authentication; onboarding modal renders six steps with a copyable `gcloud` script.
- [x] Implement `static/js/cost-estimator.js` and `static/js/onboarding.js`.
- [x] Green: both specs pass; client-side `.pdf` filter present (NFR-02).

### A4. BYOK panel (FR-03, US-03)
**Depends on:** A2.
- [x] TDD red: Playwright spec sets credentials, observes dual-validation result, clears credentials, and asserts no credential value persists in browser storage (NFR-01).
- [x] Implement `static/js/byok.js`.
- [x] Green: spec passes; cross-user 403 responses surface the re-auth/denied prompt (FR-08).

### A5. Pre-scan & terminology (FR-04, US-04)
**Depends on:** A2.
- [x] TDD red: Playwright spec runs a pre-scan on a fixture PDF, asserts the Fraktur badge, neologism list, and pre-filled terms render; asserts vocabulary save/bulk/import/export round-trips against the mocked store.
- [x] Implement `static/js/prescan.js`.
- [x] Green: spec passes.

### A6. Translation lifecycle (FR-05, FR-06, NFR-03, US-05)
**Depends on:** A2, B1 (summary shape without `can_fallback`).
- [x] TDD red: Playwright spec (Gherkin "Translation lifecycle" + "Failed pages are surfaced" scenarios) against mocked `/api/v1/book/*` endpoints: start → progress → completion → download enabled; `failed_pages > 0` renders the warning banner with a working Re-run action; the Re-run submission posts a fresh per-attempt `book_id` (e.g. `{book_id}-r2`) while the original session's download mock continues resolving its original output; polling provably stops on done and on error.
- [x] Implement `static/js/translate.js` and `static/js/polling.js` (D1; reconnection via `resume`).
- [x] Green: spec passes; no polling interval remains active after terminal states (NFR-03).

### A7. Dual-pane viewer (FR-07, US-06)
**Depends on:** A2, C2 (text-only pairs).
- [x] TDD red: Playwright spec renders German/English pairs with page navigation from the dual-pane route.
- [x] Implement `static/js/dualpane.js`.
- [x] Green: spec passes; no image/thumbnail affordance exists.

### A8. Delete Gradio UI code
**Depends on:** A2–A7 all green (feature parity established).
- [x] Delete `ui/gradio_interface.py`, `tests/test_gradio_interface.py`, `tests/test_ui_gradio.py`; update `pyproject.toml` package discovery if it references `ui*`.
- [x] Repository grep: zero `gradio` imports; `/ui` route test asserted 404 (from A1).

---

> Track A validation record (2026-10-30): default suite `pytest -n auto` — 777 passed, 13 skipped, coverage 70.90% (gate green) — across three consecutive runs after fixing a latent stale-`api.routes` binding in `tests/test_memory_api_integration.py` (added `api.routes` to its reload set; stale router bindings served default rate-limit constants instead of the patched ones). Browser specs run via `pytest -m frontend tests/frontend` (green twice) and are excluded from default runs via the `frontend` marker because pytest-playwright and pytest-asyncio cannot share one process.

## Track B — Fallback engine removal (FR-10, D2)

### B1. Orchestrator completion flow
**Depends on:** T0.
- [ ] TDD red: rewrite `handle_job_completion` tests — summary carries `failed_pages`, no `can_fallback` attribute (assert `not hasattr`); delete fallback-workflow tests.
- [ ] Remove the fallback branch from `services/book_translation_orchestrator.py`, `trigger_fallback_page_translation`, and the `FallbackPageTranslator` construction/parameter.
- [ ] Green: orchestrator suite passes without any fallback symbol.

### B2. API route + registry
**Depends on:** B1.
- [ ] TDD red: route-inventory test asserts `POST /api/v1/book/fallback-translate` returns 404; `services/__init__.py` exports assert the fallback symbols are gone.
- [ ] Delete the route handler, `FallbackResult` import usage in `api/routes.py`, and the availability-registry exports in `services/__init__.py` (§2.10 symmetry upheld by removal).
- [ ] Green: app imports cleanly; route inventory and registry tests pass.

### B3. Fallback service + docs
**Depends on:** B1.
- [ ] Delete `services/fallback_translator.py` and `tests/test_fallback_translator.py`; delete `docs/FALLBACK_TRANSLATION_LIMITATIONS.md`.
- [x] Update `pyproject.toml` discovery excludes if needed.
- [ ] Grep: zero references to `fallback_translator`/`FallbackPageTranslator` outside this spec.

### B4. Rules, ADR, and AGENTS.md (same-change rule curation)
**Depends on:** B1–B3.
- [ ] Add `docs/adr/0002-bespoke-frontend-gcp-only-translation.md` recording D1–D6 with the #14018/#14005 upstream context.
- [ ] Rewrite AGENTS.md §2.12 → "GCP-Only Translation" (no local fallback; failed pages surfaced with re-run); delete the Unicode CID invariant rows that only governed the fallback; remove §6.4 Gradio timer contracts and add the frontend polling-hygiene equivalent (NFR-03); add Gradio to the §4 deny list as a prohibited reintroduction.
- [ ] Rewrite `.greptile/rules.md` §3 (Gradio section) and add "do not request Gradio/fallback restoration" guardrails; update the README migration table and remove the UI screenshots/sections describing `/ui`.

---

## Track C — Rasterization & dependency removal (FR-11, FR-12)

### C1. pdf_quality_validator OCR recovery path
**Depends on:** T0.
- [ ] TDD red: update pdf_quality_validator tests — pages lacking extractable text yield an explicit `text_missing` result/warning instead of invoking OCR; no `pdf2image`/`tesseract` references remain in the module.
- [ ] Remove the poppler/tesseract rasterize-and-OCR path (D3); keep pypdf-computable metrics.
- [ ] Green: suite passes; module imports without `pdf2image`.

### C2. Dual-pane page thumbnails
**Depends on:** T0.
- [ ] TDD red: `BilingualPagePair` tests assert text-only fields (no image payload).
- [ ] Remove `_render_page_image` and its call sites from `services/dual_pane_viewer.py`.
- [ ] Green: dual-pane suite passes.

### C3. Dependency and lockfile removal (FR-12)
**Depends on:** A1, A8, B1–B3, C1, C2 (join point).
- [ ] Update `requirements.in`: remove the direct requirement lines for `gradio`, `pdf2image`, `reportlab`, **`pillow`, and `audioop-lts`**; keep everything else; regenerate `requirements.txt` with `uv pip compile requirements.in -o requirements.txt` (Python 3.13).
- [ ] Verify `audioop-lts`, `pydub`, `pillow`, and the Gradio cluster are absent from the regenerated lockfile; `uv pip check` clean; resolver succeeds on `--python-platform x86_64-unknown-linux-gnu` too.
- [ ] Move `reportlab>=5.0.1,<6.0` into `requirements-dev.txt` (already present — confirm) and delete the duplicate runtime line.
- [ ] Hermetic install + `python -c "import app"` succeeds with Pillow absent (NFR-07, flips T0's red baseline to green).
- [ ] Remove the `gradio-majors` group from `.github/dependabot.yml`.

### C4. Coverage re-baseline (NFR-06, D6)
**Depends on:** C3.
- [ ] Run the full suite with the 70% gate; if removals shift measured coverage, document the delta in the PR and adjust test placement — never weaken the gate silently.

---

## Track D — Integration, publication (NFR-05, NFR-06, NFR-07)

### D1. Full validation
**Depends on:** A8, B4, C3, C4.
- [ ] Full parallel suite (`pytest -n auto --timeout=30`, coverage gate) green, twice consecutively.
- [ ] Manual browser sweep (10.2 checklist in requirements.md): upload → quote → BYOK validate → pre-scan → translate → download → dual-pane → reconnection.
- [ ] Playwright specs green in a single run.

### D2. Dependabot alert closure (NFR-05)
**Depends on:** D1 (post-merge).
- [ ] After merge: `gh api repos/JAaron93/PhenomenalLayout/dependabot/alerts?state=open` reports zero Pillow alerts; total open alerts drop accordingly.
- [ ] Confirm a Dependabot config graph update succeeds without the Pillow resolution failure signature.

### D3. Publication
**Depends on:** D1.
- [ ] PR body: links this spec, ADR 0002, the alert-count evidence (41 → 0), and the empirical Gradio-6.30 + Pillow-13 validation record.
- [ ] Human merges; housekeeping (worktree/branch removal) follows.

---

## Traceability matrix (abridged)

| Requirement | Tasks |
| --- | --- |
| FR-01/FR-02 | A3 |
| FR-03 | A4 |
| FR-04 | A5 |
| FR-05/FR-06 | A6, B1 |
| FR-07 | A7, C2 |
| FR-08 | A2 |
| FR-09 | A1, A8 |
| FR-10 | B1–B4 |
| FR-11 | C1, C2 |
| FR-12 | C3 |
| NFR-01/02/03/04 | A2, A3, A6 |
| NFR-05 | C3, D2 |
| NFR-06 | C4, D1 |
| NFR-07 | C3 |
| US-01–US-06 | A3–A7 |
