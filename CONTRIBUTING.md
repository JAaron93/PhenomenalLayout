# Contributing to PhenomenalLayout

Welcome to PhenomenalLayout, a domain-specific **German Philosophical Book Translation & Neologism Orchestration Engine**. PhenomenalLayout pairs **Google Cloud Document Translation Advanced (v3)** with a specialized **German Philosophical Neologism Detection Engine** to translate full-length treatises and books with pixel-perfect typography, layout preservation, and consistent terminology.

## Project Context

PhenomenalLayout's core architecture incorporates:
- **Asynchronous GCS Batch Translation**: Serverless book-scale translation (`batchTranslateDocument`) via Google Cloud Storage with zero host PDF storage
- **Bring Your Own Key (BYOK) Security**: In-memory credential vault with non-billable dual validation and 7-day auto-delete staging lifecycle enforcement
- **Dual-Tier Glossary Synchronization**: Persistent base philosophical glossaries paired with dynamic per-book user choice dictionaries
- **German Philosophical Neologism Detector**: Morphological analysis and contextual compound decomposition with interactive review
- **Zero-Credential Cost Estimator**: Unauthenticated offline PDF pricing calculation ($\pm \$5.00$ tolerance)
- **1-Click Google Drive Export**: Streamed multipart export via client-side Google Identity Services (GIS) OAuth (`drive.file` scope)
- **Fraktur OCR Script Assessment**: Historical ligature analysis and calibrated confidence scoring ($C \in [0.0, 1.0]$)
- **Atomic LRO Session Resumption**: Sub-second (< 1.0s) job recovery across browser closes and serverless scale-downs
- **Scholarly Fallback Plaintext Translation**: Dynamic sequential 16-bit CID allocation and format 4/12 TrueType `cmap` parsing guaranteeing 100% translation completeness
- **Synchronized Dual-Pane Viewer**: Synchronized bilingual page retrieval with word-level bounding box coordinate extraction

This project uses pinned dev tooling and automation to keep CI stable and reproducible.

## Tooling and configs

- Pytest is configured in `pytest.ini`:
  - `asyncio_mode = auto` for `pytest-asyncio>=0.23` on pytest 8.
  - Markers: `slow`, `load`. Run only non-slow and non-load tests with `pytest -q -m "not slow and not load"`.
  - Coverage gates ($\ge 85\%$) are applied by default; set `FOCUSED=1` to disable locally for focused test runs.
- Ruff and mypy live in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]` so local and CI share rules.
- Runtime deps: `requirements.txt` (compiled from `requirements.in`). Dev-only pins: `requirements-dev.txt`.

## Development environment

Prerequisite: Python 3.11 or 3.12 (match CI). Verify with: `python3 --version`

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
```

### Manual Quality Checks

Run the complete multi-track GCP migration test suite (235 tests across Tracks 1–4):

```bash
pytest -o addopts="" tests/test_dry_helpers.py tests/test_gcp_settings.py \
  tests/test_byok_credentials_manager.py tests/test_gcp_batch_translation_service.py \
  tests/test_lro_progress_monitor.py tests/test_cost_estimator.py \
  tests/test_google_drive_exporter.py tests/test_user_vocabulary_store.py \
  tests/test_glossary_compiler.py tests/test_glossary_sync_manager.py \
  tests/test_session_glossary_lifecycle.py tests/test_fraktur_classifier.py \
  tests/test_batch_job_recovery.py tests/test_fallback_translator.py \
  tests/test_dual_pane_viewer.py tests/test_dynamic_programming.py \
  tests/test_enum_hash.py tests/test_memory_api_security.py \
  tests/test_memory_api_integration.py tests/test_memory_gc_endpoint.py \
  tests/test_problem_case_fixed.py -v
```

Lint and type-check:

```bash
ruff check .
mypy .
```

## Automated dependency updates

Dependabot is enabled via `.github/dependabot.yml`:

- Weekly checks for pip dependencies, with a group for dev tools (pytest, mypy, ruff, plugins).
- Weekly checks for GitHub Actions.

Please triage Dependabot PRs promptly. Prefer green CI before merging. If a tool update requires code changes, include them in the same PR.

## Async tests guidance

With `pytest-asyncio>=0.23` and pytest 8, the asyncio mode must be declared. We default to `auto`. If a test requires explicit mode, use `@pytest.mark.asyncio`.

## Commit style

- Keep edits small and focused; include a clear rationale in the message.
- Ensure `ruff`, `mypy`, and tests pass locally before opening a PR.

## Layout Preservation Development Guidelines

> [!NOTE]
> Under [ADR 0001](docs/adr/0001-migrate-to-google-cloud-document-translation.md), full-length PDF document translation and pixel-perfect layout preservation are handled natively by **Google Cloud Document Translation Advanced (v3)**. Custom canvas painting, ReportLab box placement, and dynamic programming text scaling are deprecated.

When contributing to PhenomenalLayout, focus on:
- **Consolidated Helper Utilities**: When interacting with Google Cloud Storage, Cloud Translation APIs, RFC 4180 TSV data, or persistent file writes, always utilize the canonical utilities in `utils/gcp_helpers.py`, `utils/tsv_utils.py`, `utils/pdf_stream.py`, and `utils/file_handler.py`. Refer to [REUSABLE_HELPER_FUNCTIONS.md](docs/REUSABLE_HELPER_FUNCTIONS.md) for usage patterns and complexity guarantees.
- **Neologism Detection & Morphological Analysis**: Accurate German compound decomposition and philosophical term recognition.
- **Dual-Tier Glossary Synchronization**: Ensuring RFC 4180 TSV compliance, zero-downtime Blue-Green replacement, and regional quota bounds in GCP `us-central1`.
- **Scholarly Resilience**: Fraktur OCR assessment, job recovery, and side-by-side verification.

### Integration Testing
- **External service mocking**: Mock Google Cloud Translation and Google Cloud Storage APIs using standard `unittest.mock` fixtures.
- **Quality threshold testing**: Maintain $\ge 90\%$ test coverage on all newly added services and bug fixes.

### Documentation Requirements
- **Integration patterns**: Describe how PhenomenalLayout orchestrates Google Cloud Translation and GCS
- **Terminology & Glossary structures**: Document RFC 4180 TSV formatting and glossary quota handling
- **Scholarly resilience behavior**: Document Fraktur detection confidence scales and fallback TrueType font mappings
- **Performance characteristics**: Include throughput and ETA benchmarks for large document processing

## CI notes

- UI-related tests rely on env flags. CI sets `GRADIO_SCHEMA_PATCH=true` and `GRADIO_SHARE=true`.
- Modal deployment tests should run in mocked mode; avoid hitting external services in CI.
