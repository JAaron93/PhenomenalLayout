# Design: Bespoke Frontend & GCP-Only Translation (Gradio + Fallback Removal)

Status: DRAFT · 2026-10-29 · Supersedes the Gradio-based UI design embedded in `.kiro/specs/gcp-migration/`

## 1. Purpose and Motivation

PhenomenalLayout currently maintains two parallel controllers over the same service layer: a
Gradio UI (`ui/gradio_interface.py`) and the FastAPI API (`api/routes.py`). The Gradio layer was
adopted in early 2025 when template-driven UIs outpaced hand-built frontends. It now costs more
than it provides:

- **41 open Dependabot security alerts** against Pillow 12.3.0, all fixable only in Pillow
  13.0.0, which Gradio 6.x's `pillow<13.0` constraint blocks at install time (Gradio merged the
  allowance for 7.0-dev only, gradio-app/gradio#14005; the 6.x backport request #14018 remains
  open). Dependabot cannot generate the fix at all.
- **`pydub` → `audioop-lts`**: a PEP 594 compatibility shim that exists solely because Gradio
  depends on pydub; it triggers a recurring manual restoration ritual on every Dependabot
  regeneration (PR #125).
- **A redundant second controller** duplicating auth, form handling, and state polling that the
  API already provides with tests.

This change replaces Gradio with a bespoke zero-build frontend, removes the local fallback
translation engine (Google Cloud Document Translation becomes the sole translation engine), and
removes the remaining rasterization features — taking `gradio`, `Pillow`, `reportlab`,
`pdf2image`, `pydub`, and `audioop-lts` out of the runtime dependency tree and closing every
open Dependabot alert by removal.

## 2. In Scope / Out of Scope

**In scope**
- New static frontend served by FastAPI, replacing the `/ui` Gradio mount feature-for-feature.
- Removal of the Gradio dependency cluster and `ui/gradio_interface.py` with its tests.
- Removal of the fallback plaintext translation engine end-to-end (service, orchestrator
  branch, API route, availability-registry exports, docs).
- Removal of `pdf2image` and its two consumers (quality-validator OCR recovery path,
  dual-pane page thumbnails).
- Removal of `Pillow` and `reportlab` from the runtime tree (`requirements.txt`,
  `requirements.in`).
- Rule, ADR, and documentation updates in the same change.

**Out of scope**
- Any change to the GCP batch translation pipeline, glossary lifecycle, BYOK storage, or
  vocabulary store semantics beyond removing the fallback branch.
- The DualPaneViewer's text-extraction pairing logic (kept; only its page-image rendering goes).
- Any translation quality replacement for the removed fallback (accepted product decision —
  see §5 Trade-offs).

## 3. Architecture Overview

### 3.1 Before

```
Browser ──> FastAPI app ──┬──> /api/v1/*  (api.routes → services/core)
                          └──> /ui        (gr.mount_gradio_app → ui.gradio_interface
                                           → duplicated handler logic → same services)
Dependencies: gradio cluster + Pillow + reportlab + pdf2image + pydub/audioop-lts
```

### 3.2 After

```
Browser ──> FastAPI app ──┬──> /            (static/index.html — zero-build ES-module SPA)
                          │                  static/app.js, static/styles.css
                          └──> /api/v1/*    (single controller; Bearer token or X-API-Key)
Dependencies removed: gradio, gradio-client, hf-gradio, groovy, safehttpx, tomlkit,
                      pydub, audioop-lts, pandas, orjson, pytz, Pillow, reportlab, pdf2image
```

The SPA is served from the existing `static/` directory (already mounted via
`StaticFiles(directory="static")` in `app.py`) with `main()` rewired to serve `index.html` at
`/` and the `gr.mount_gradio_app` call deleted. No Node toolchain, no build step, no new Python
dependencies: vanilla ES modules + `fetch`.

### 3.2.1 Frontend decomposition (`static/app.js` ES modules)

| Module | Responsibility | API endpoints consumed |
| --- | --- | --- |
| `api-client.js` | `fetch` wrapper; attaches `Authorization: Bearer <token>` or `X-API-Key`; uniform error surfacing | all `/api/v1/*` |
| `auth.js` | Token **and User ID** entry, `sessionStorage` persistence (cleared on tab close; never `localStorage`), logout. `user_id` is required on every user-scoped route and injected in the shape each route demands — path, query, or form. API-key callers authenticate as administrators and must still send the intended `user_id` explicitly; JWT callers send the ID matching their token | first authenticated call validates both |
| `cost-estimator.js` | PDF upload → itemized quote | `POST /api/v1/cost/estimate` |
| `onboarding.js` | 6-step GCP walkthrough modal, copyable `gcloud` script | `GET /api/v1/byok/onboarding-guide` |
| `byok.js` | Credential set/validate/clear panel | `POST /api/v1/byok/credentials`, `GET /api/v1/byok/validate`, `DELETE /api/v1/byok/credentials` |
| `prescan.js` | Pre-scan + Fraktur badge + neologisms + saved vocabulary | `POST /api/v1/book/pre-scan`, `GET/POST /api/v1/vocabulary/{user_id}`, `POST .../bulk`, `GET .../export`, `POST .../import` |
| `translate.js` | Document upload → start → progress polling → completion → download; failed-pages warning | `POST /api/v1/book/translate`, `GET /api/v1/book/status/{session_id}`, `GET /api/v1/book/download/{session_id}`, `GET /api/v1/book/jobs/{user_id}` |
| `dualpane.js` | Side-by-side German/English text pairs (text-only; no page thumbnails) | `POST /api/v1/book/dual-pane/{session_id}` |
| `polling.js` | Shared polling primitive: interval, backoff, **mandatory deactivation on done/error/idle** | — |

## 4. Component Changes

### 4.1 Removed components
| Component | Fate |
| --- | --- |
| `ui/gradio_interface.py` | Deleted (handlers are thin wrappers over existing API/services) |
| `app.py` Gradio mount + `main()` wiring | Rewired to serve the SPA; `import gradio as gr` removed |
| `services/fallback_translator.py` | Deleted (`FallbackPageTranslator`, CID/font machinery, splice) |
| `orchestrator.trigger_fallback_page_translation` + `handle_job_completion` fallback branch | Deleted; `CompletionSummary.can_fallback` removed |
| `api/routes.py` `POST /book/fallback-translate` | Deleted |
| `services/pdf_quality_validator.py` tesseract OCR recovery path | Deleted (rasterize + OCR a page whose text pypdf cannot extract). ADR 0001 already assigns OCR to Google Cloud; the path also required poppler + tesseract binaries |
| `services/dual_pane_viewer.py` `_render_page_image` | Deleted; dual-pane returns text-only pairs |
| `services/__init__.py` fallback exports | Removed (§2.10 availability-registry symmetry upheld: the conditional `FALLBACK_TRANSLATION_AVAILABLE`-style exports go with the feature) |
| `docs/FALLBACK_TRANSLATION_LIMITATIONS.md` | Deleted (no fallback left to document) |
| Tests: `test_gradio_interface.py`, `test_ui_gradio.py`, `test_fallback_translator.py` | Deleted; replaced by Playwright specs + orchestrator/route tests rewritten |
| `.github/dependabot.yml` `gradio-majors` group | Removed (package no longer manifest-tracked) |

### 4.2 Unchanged components
`api/routes.py` (minus one route), `core/*`, `services/batch_job_recovery.py`,
`services/gcp_batch_translation_service.py`, `services/user_vocabulary_store.py`,
`services/fraktur_classifier.py` (font-characteristic based, no PIL), `services/pdf_validator.py`
+ `utils/pdf_*` (pypdf-based), `utils/*`, `database/*`, GCS/Drive flows, Modal deployment shape.

### 4.3 Dependency delta (`requirements.in` / `requirements.txt`)
| Package | Action | Reason |
| --- | --- | --- |
| `gradio`, `gradio-client`, `hf-gradio`, `groovy`, `safehttpx`, `tomlkit`, `orjson`, `pytz`, `pandas` | Remove (transitive of Gradio) | UI replaced |
| `pydub`, `audioop-lts` | Remove (audioop-lts is a direct markered requirement in `requirements.in`; pydub is transitive) | Only Gradio consumed pydub; the PEP 594 shim dies with it |
| `reportlab` | Remove from runtime and dev entirely (PR #147) | Runtime consumer was the fallback engine only; dev test fixtures migrated to `build_test_pdf()` in `tests/conftest.py` — a stdlib-only PDF 1.4 factory (no Pillow) |
| `pdf2image` | Remove | Both consumers removed (§4.1) |
| `Pillow` | Remove direct requirement (the `pillow>=12.0,<13.0` line in `requirements.in`) | No runtime importer remains once gradio, pdf2image, and reportlab are gone; all 41 open Dependabot alerts close by removal |
| `pydantic`, `numpy`, `spacy`, `psutil`, `rich`, `mcp`, `modal`, GCP stack | Unchanged | Independent consumers |

`requirements.txt` regenerated via `uv pip compile requirements.in -o requirements.txt`; the
`audioop-lts` marker line disappears entirely, ending the manual restoration ritual (PR #125
ritual retired in the same change).

### 4.4 Translation completion without fallback

`handle_job_completion` returns a summary with `failed_pages` intact but no `can_fallback` and no
local healing. The frontend surfaces a warning banner when `failed_pages > 0` offering
**Re-run translation**: a fresh `POST /book/translate` submission whose `book_id` is suffixed
per attempt (e.g. `{book_id}-r2`, `-r3`, …). Because `book_id` is client-supplied form data that
determines the GCS output prefix, each attempt writes to its own prefix — the original
session's partial output stays downloadable at its original location after the re-run completes.
GCP remains the sole translation engine; no locally synthesized pages exist at any point.

## 5. Design Decisions and Trade-offs

- **D1 — Zero-build vanilla ES modules.** No framework/bundler: the UI is one page with eight
  small modules; a build step would add toolchain without benefit at this scale. Revisit only if
  the UI grows beyond a single page.
- **D2 — GCP-only translation; fallback deleted, not disabled.** Accepted consequence: the
  "100% translated" completeness guarantee for layout-parse failures is gone; books with
  `failed_pages > 0` surface a warning and a re-run action instead of locally synthesized
  plaintext pages. Scholars lose the local safety net but gain a dependency tree with no CID/font
  synthesis machinery and no Pillow/reportlab exposure.
- **D3 — Remove the quality-validator OCR recovery path.** It duplicates what ADR 0001 assigns
  to Google Cloud (OCR/layout), required poppler + tesseract host binaries, and its only
  graceful-degradation path already assumed absence. Quality metrics that pypdf can compute
  (page counts, text presence flags) are retained.
- **D4 — reportlab fully eradicated (updated PR #147).** Initially retained as a dev-only fixture dependency, `reportlab` was subsequently removed from `requirements-dev.txt` because it declares `pillow` as a hard `Requires`, keeping Pillow alive in all developer environments. All PDF test fixtures were migrated to `build_test_pdf()` in `tests/conftest.py` — a stdlib-only raw PDF 1.4 writer using Helvetica Type1 / WinAnsiEncoding (cp1252) with text recoverable by `pypdf.page.extract_text()`.
- **D5 — Token storage in `sessionStorage`, never `localStorage`.** Matches the BYOK credential
  isolation posture: tokens die with the tab; no long-lived client-side credential surface.
- **D6 — Coverage gate stays at 70%.** Removals delete both covered and covering lines; a
  re-baseline task verifies the gate rather than retuning it (per ADR-0001-era precedent of
  "gate to reality").

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Frontend regressions vs Gradio UX (upload flows, polling, downloads) | Feature-parity checklist in requirements.md + Playwright specs for every user story; manual sweep task |
| Orchestrator completion-flow change breaks recovery tests | Rewrite orchestrator tests alongside the branch removal (Track B, TDD) |
| Hidden runtime importers of removed packages surface at import time | Import-linter task: grep + smoke `python -c "import app"` in a Pillow-free venv before lockfile regen |
| Reviewer agents flag Gradio removal as regression | `.greptile/rules.md` updated in the same change; ADR 0002 cited in PR body |

## 7. Glossary

- **BYOK** — Bring Your Own Key; user-supplied GCP credentials validated non-billing.
- **Fallback engine** — the removed `FallbackPageTranslator`: local extraction + translation +
  reportlab CID-font synthesis of pages GCP's layout-preserved translation failed to convert.
- **Dual-pane** — synchronized German/English text view for scholars (text-only after this change).
- **SPA** — single-page application served as static files by the FastAPI app itself.
