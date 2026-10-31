# ADR 0002: Bespoke Zero-Build Frontend & GCP-Only Translation (Retiring Gradio and Fallback Engine)

## Status
**Accepted**

## Date
2026-10-30

## Context & Problem Statement

PhenomenalLayout previously maintained two parallel controllers over the core service layer:
1. An interactive Gradio web interface ([`ui/gradio_interface.py`](../../ui/gradio_interface.py) [deleted under Track A]).
2. A comprehensive FastAPI REST API ([`api/routes.py`](../../api/routes.py)).

While Gradio accelerated rapid UI prototyping in early 2025, its presence in the production dependency tree created severe operational burdens:
* **41 Open Dependabot Security Alerts**: Gradio 6.x pinned `pillow<13.0`. Critical vulnerabilities in Pillow 12.3.0 were fixable only in Pillow 13.0.0. While Gradio merged the `pillow>=13.0` allowance for 7.0-dev ([gradio-app/gradio#14005](https://github.com/gradio-app/gradio/pull/14005)), the 6.x backport request ([#14018](https://github.com/gradio-app/gradio/pull/14018)) remained unmerged, blocking Dependabot from resolving security alerts and generating update PRs.
* **PEP 594 Compatibility Friction (`audioop-lts`)**: Gradio depended transitively on `pydub`, which in Python 3.13 requires the `audioop-lts` shim. Every automated lockfile regeneration stripped or conflicted with this marker, requiring recurring manual intervention (PR #125).
* **Controller Redundancy**: Gradio UI callbacks duplicated authentication verification, form submission, and polling logic already implemented and tested in the REST API.
* **Secondary Fallback Engine Complexity**: Under ADR 0001, a secondary fallback engine (`services/fallback_translator.py`) was introduced to synthesize plaintext pages when Google Cloud Document Translation encountered layout-parsing failures on complex diagram pages (`failed_pages > 0`). This required dynamic sequential 16-bit CID allocation, format 4/12 TrueType CMap parsing, composite font synthesis, and runtime `reportlab` canvas drawing, introducing substantial complexity and font-metric overhead.

---

## Decisions

We adopt a **Bespoke Zero-Build Frontend** and establish **Google Cloud Document Translation as the Sole Translation Pipeline**, permanently retiring Gradio and the local fallback engine.

### Architectural Decisions (D1–D6)

* **D1 — Zero-Build Vanilla ES Modules**:
  The new frontend is implemented as static vanilla ES modules (`public/`) served directly by FastAPI's `StaticFiles` mount at root (`/`). No Node.js build step, bundler, or npm toolchain is required.

* **D2 — GCP-Only Translation; Fallback Deleted, Not Disabled**:
  The secondary fallback engine (`services/fallback_translator.py`), route (`POST /book/fallback-translate`), and orchestrator methods are permanently deleted. Google Cloud Document Translation is the exclusive translation engine. When batch translation reports `failed_pages > 0`, the UI surfaces an explicit warning banner with a 1-click **Re-run translation** option under a per-attempt suffixed `book_id` (`{book_id}-r2`). Each attempt writes to its own isolated GCS prefix, ensuring partial outputs remain downloadable.

* **D3 — Remove pdf_quality_validator OCR Recovery Path**:
  The poppler/tesseract rasterize-and-OCR recovery path in `services/pdf_quality_validator.py` is removed, reinforcing ADR 0001'sTenet of delegating OCR and layout parsing strictly to Google Cloud while eliminating external binary dependencies.

* **D4 — ReportLab Retained Strictly as Dev-Only Fixture Dependency**:
  `reportlab` is removed from runtime `requirements.in`/`requirements.txt` and retained exclusively in `requirements-dev.txt` for generating dynamic text-bearing PDF test fixtures. Dev-only presence avoids runtime Dependabot vulnerability alerts.

* **D5 — Token Storage in `sessionStorage`, Never `localStorage`**:
  All client-side bearer tokens and API keys are stored strictly in browser `sessionStorage`, adhering to the BYOK credential isolation principle. Credentials expire automatically when the scholar closes the tab.

* **D6 — Coverage Gate Stays at 70%**:
  The CI test coverage threshold remains enforced at $\ge 70\%$ across the core domain packages (`services`, `utils`, `models`).

---

## Consequences

### Positive Consequences
* **Complete Security Alert Remediation**: Removing Gradio, runtime `reportlab`, and `pdf2image` drops `Pillow` from runtime dependencies entirely, resolving all 41 open Dependabot alerts by dependency removal.
* **Simplified Maintenance**: Eliminates `audioop-lts` workarounds, Gradio schema monkeypatches (`GRADIO_SCHEMA_PATCH`), and headless share URL overrides (`GRADIO_SHARE`).
* **Clean Single Controller Architecture**: All client actions route through standard FastAPI `/api/v1/*` endpoints, covered by OpenAPI schemas and automated test suites.
* **Streamlined Pipeline**: Removes over 1,400 lines of CID font parsing, TrueType CMap binary manipulation, and fallback splicing code.

### Negative Consequences & Trade-offs
* **Loss of Local Plaintext Splicing**: The system no longer offers local plaintext synthesis for layout-parse failures. If Google Cloud skips a complex diagram page, scholars must either re-run translation or verify the page manually using the bilingual dual-pane viewer.
