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

Run the complete Track 1 and Track 2 GCP migration test suite (97 tests):

```bash
pytest -o addopts="" tests/test_gcp_settings.py tests/test_byok_credentials_manager.py \
  tests/test_gcp_batch_translation_service.py tests/test_lro_progress_monitor.py \
  tests/test_cost_estimator.py tests/test_google_drive_exporter.py \
  tests/test_user_vocabulary_store.py tests/test_glossary_compiler.py \
  tests/test_glossary_sync_manager.py tests/test_session_glossary_lifecycle.py -v
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
- **Neologism Detection & Morphological Analysis**: Accurate German compound decomposition and philosophical term recognition.
- **Dual-Tier Glossary Synchronization**: Ensuring RFC 4180 TSV compliance, zero-downtime Blue-Green replacement, and regional quota bounds in GCP `us-central1`.
- **Scholarly Resilience**: Fraktur OCR assessment, job recovery, and side-by-side verification.

### Integration Testing
- **External service mocking**: Mock Google Cloud Translation and Google Cloud Storage APIs using standard `unittest.mock` fixtures.
- **Quality threshold testing**: Maintain $\ge 90\%$ test coverage on all newly added services and bug fixes.

### Documentation Requirements
- **Algorithm explanations**: Document the mathematical basis for text fitting strategies
- **Quality scoring**: Explain how layout preservation quality is calculated
- **Integration patterns**: Describe how PhenomenalLayout orchestrates external services
- **Performance characteristics**: Include benchmark data for large document processing

## CI notes

- UI-related tests rely on env flags. CI sets `GRADIO_SCHEMA_PATCH=true` and `GRADIO_SHARE=true`.
- Modal deployment tests should run in mocked mode; avoid hitting external services in CI.
