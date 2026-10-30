# Requirements: Bespoke Frontend & GCP-Only Translation

Status: DRAFT · 2026-10-29 · Derived from `design.md` (v1). Traceability: FR/NFR → US → tasks.

## User Stories

- **US-01** — As a scholar, I upload a PDF and see an itemized GCP cost and storage quote without signing in, so I can budget before committing.
- **US-02** — As a first-time user, I follow a guided GCP onboarding walkthrough with console links and a copyable `gcloud` script so I can configure my own bucket and credentials.
- **US-03** — As a BYOK user, I set and validate my service-account credentials in the browser, and they are held only in session memory on the server.
- **US-04** — As a scholar, I pre-scan a book to see the Fraktur script-confidence badge, detected neologisms, and my saved terminology, and I can import/export that terminology.
- **US-05** — As a scholar, I upload a book, start a GCP batch translation, watch live progress, and download the translated PDF when done — with failed pages clearly surfaced and a way to re-run the translation.
- **US-06** — As a scholar, I compare the German original and English translation side by side, page by page.

## Functional Requirements

### Frontend (replaces the Gradio UI feature-for-feature)

- **FR-01 Cost estimator**: file picker accepting `.pdf` only; `POST /api/v1/cost/estimate`;
  renders itemized quote (pages, per-page rate, staging, retention, tolerance range) without
  authentication. *(US-01)*
- **FR-02 Onboarding walkthrough**: renders the six steps and copyable `gcloud` script from
  `GET /api/v1/byok/onboarding-guide` in a dismissible modal. *(US-02)*
- **FR-03 BYOK panel**: set credentials (`POST /api/v1/byok/credentials`), validate
  (`GET /api/v1/byok/validate`), clear (`DELETE /api/v1/byok/credentials`); shows dual-check
  results (translation API + storage bucket). *(US-03)*
- **FR-04 Pre-scan & terminology**: `POST /api/v1/book/pre-scan` renders script-confidence badge,
  neologism list, and pre-filled terms; vocabulary table with
  get/save/bulk/import/export via `/api/v1/vocabulary/{user_id}` routes. *(US-04)*
- **FR-05 Translation lifecycle**: `POST /api/v1/book/translate` starts a batch; progress view
  polls `GET /api/v1/book/status/{session_id}`; completion enables `GET
  /api/v1/book/download/{session_id}`; `GET /api/v1/book/jobs/{user_id}` lists resumable jobs;
  reconnection after browser close uses `GET /api/v1/book/resume/{session_id}`. *(US-05)*
- **FR-06 Failed-pages surfacing**: when the completion summary reports `failed_pages > 0`, the
  UI shows a warning banner with the count and a **Re-run translation** action. The Re-run
  submission carries a new per-attempt `book_id` (e.g. `{book_id}-r{attempt}`) so each attempt
  writes to a distinct GCS output prefix; after a re-run completes, the original session's
  download still returns the original output. No fallback-translate affordance exists anywhere
  in the UI. *(US-05)*
- **FR-07 Dual-pane viewer**: `POST /api/v1/book/dual-pane/{session_id}` renders synchronized
  German/English text pairs with page navigation; text-only (no page thumbnails). *(US-06)*
- **FR-08 Authentication & identity**: a token entry field accepts an API key or JWT, and a
  **User ID** field is captured alongside it (both persisted in `sessionStorage`). Every
  user-scoped request carries `user_id` in the shape the route requires — path
  (`/vocabulary/{user_id}`, `/book/jobs/{user_id}`), query (`/book/status`, `/book/resume`,
  `/book/download`, `/book/dual-pane`, `/byok/validate`, `DELETE /byok/credentials`), form data
  (`/book/translate`, `/book/pre-scan`), or JSON body (`POST /byok/credentials` sends `user_id`,
  `project_id`, `bucket_name`, and `sa_json`). API-key callers authenticate as administrators
  and must still send the intended `user_id` explicitly; JWT callers send the ID matching their
  token. Every `/api/v1` call attaches `Authorization: Bearer <token>` or `X-API-Key`;
  401/403 responses surface a re-authentication prompt. An authenticated request test asserts
  the required query, form, JSON, and path values per route. *(US-03–US-06)*

### Removal requirements

- **FR-09 Gradio deletion**: `ui/gradio_interface.py`, the `gr.mount_gradio_app` wiring in
  `app.py`, `test_gradio_interface.py`, `test_ui_gradio.py`, and every `gradio` import are
  removed; the app serves the SPA at `/` and no `/ui` route exists.
- **FR-10 Fallback engine deletion**: `services/fallback_translator.py`,
  `orchestrator.trigger_fallback_page_translation`, the `handle_job_completion` fallback branch,
  `CompletionSummary.can_fallback`, the `POST /api/v1/book/fallback-translate` route, and the
  fallback exports in `services/__init__.py` are removed; `docs/FALLBACK_TRANSLATION_LIMITATIONS.md`
  is deleted.
- **FR-11 Rasterization deletion**: the pdf_quality_validator tesseract OCR recovery path and
  `dual_pane_viewer._render_page_image` are removed; `pdf2image` has no remaining importers.
- **FR-12 Dependency removal**: `requirements.in`/`requirements.txt` drop `gradio` and all
  Gradio-transitive packages listed in design §4.3, plus `reportlab`, `pdf2image`, and the
  **direct** `pillow` and `audioop-lts` requirement lines; the lockfile regenerates cleanly with
  `uv pip compile`; `reportlab` moves to `requirements-dev.txt` (test fixtures only).

### Non-Functional Requirements

- **NFR-01 Security — token handling**: the frontend stores the auth token in `sessionStorage`
  only; no token or credential value is ever written to `localStorage` or persisted to disk.
- **NFR-02 Security — input filtering**: client-side file pickers filter to `.pdf`, matching the
  existing server-side `validate_pdf_extension_and_header` checks; no new server-trusting client
  behavior is introduced.
- **NFR-03 Polling hygiene**: progress polling deactivates on completion, error, or idle return —
  the frontend equivalent of the retired AGENTS.md §6.4 timer contracts; no indefinite polling.
- **NFR-04 Zero-build frontend**: no Node toolchain, bundler, or new Python dependencies for the
  frontend; static ES modules served by the existing `StaticFiles` mount.
- **NFR-05 Alert closure**: after merge, the repository has **zero open Dependabot security
  alerts** attributable to `Pillow`, and Dependabot's Pillow update resolution no longer errors.
- **NFR-06 Coverage gate**: the 70% coverage gate stays green after all removals and additions.
- **NFR-07 No runtime PIL**: `python -c "import app"` succeeds in an environment with Pillow
  uninstalled, proving no hidden importer remains.

### BDD acceptance criteria (Gherkin)

```gherkin
Feature: Bespoke frontend replaces Gradio UI
  Scenario: Cost quote without authentication (US-01, FR-01)
    Given the scholar opens the application root
    When they select a valid PDF in the cost estimator and submit it
    Then an itemized quote with the $0.080 per-page rate is displayed
    And no authentication prompt is required

  Scenario: Translation lifecycle with live progress (US-05, FR-05, NFR-03)
    Given an authenticated scholar with a configured GCS bucket
    When they upload a book PDF and start an advanced translation
    Then progress polls the status endpoint until completion
    And polling stops once the status reports done or error
    And the download control becomes available

  Scenario: Failed pages are surfaced, not silently healed (US-05, FR-06, D2)
    Given a batch translation completed with failed_pages greater than 0
    When the completion summary is displayed
    Then a warning banner shows the failed-page count
    And a "Re-run translation" action submits a fresh batch under a new per-attempt book_id
    And the original session's download still returns the original output after the re-run finishes
    And no locally synthesized fallback page is offered or generated

  Scenario: Token handling (US-03, FR-08, NFR-01)
    Given the scholar enters an API key or JWT
    When any /api/v1 call is made
    Then the request carries the corresponding Authorization or X-API-Key header
    And sessionStorage contains the token while localStorage never does

  Scenario: Gradio is gone (FR-09)
    Given the application is running after the migration
    When a client requests "/ui"
    Then the response is 404
    And no module in the repository imports "gradio"
```

## Acceptance & Verification

- Playwright browser specs cover FR-01 through FR-08 (red → green during Track A).
- Rewritten pytest suites cover the removals (FR-09 – FR-12): import guards, orchestrator
  completion without fallback, route inventory without `/book/fallback-translate`.
- `gh api .../dependabot/alerts?state=open` returns zero Pillow alerts (NFR-05).
- Manual sweep: upload → quote → BYOK validate → pre-scan → translate → download → dual-pane.
