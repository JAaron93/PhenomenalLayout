# Implementation Tasks: GCP Translation Helpers Consolidation & Algorithmic Optimization

## 1. Plan Overview & Execution Strategy

This implementation plan breaks down the requirements from [`requirements.md`](.kiro/specs/gcp-translation-helpers/requirements.md) into concrete, test-driven work packages. The primary mission is to eliminate code duplication across newly added GCP translation services and legacy components while optimizing critical algorithmic hot spots for time and space complexity.

The plan is organized into five **Execution Tracks**:
* **Track 1: Foundation Utility Modules & Central Documentation** (Creation of `gcp_helpers.py`, `tsv_utils.py`, `pdf_stream.py`, and `docs/REUSABLE_HELPER_FUNCTIONS.md`)
* **Track 2: Cloud & Storage Service Integration** (Refactoring GCS batch service, glossary sync, lifecycle, BYOK, Drive exporter, and vocabulary store)
* **Track 3: Typography, Stream Management & Fallback Optimization** (Streamlining cost estimator, Fraktur classifier, TrueType font cache, and dual-pane viewer)
* **Track 4: Linguistic Analysis & Choice Conflict Optimization** (Unified German compound detection and $O(N)$ bucketed conflict detection)
* **Track 5: Verification, Benchmarking & Test Suite Validation** (Dedicated tests, full regression run, coverage $\ge 85\%$, ruff linting)

---

## 2. Track Breakdown & Parallelism Map

```
┌────────────────────────────────────────────────────────────────────────┐
│ Track 1: Foundation Utility Modules & Central Documentation            │
│ [Task 1.1: gcp_helpers] ──────┬───> [Task 1.2: tsv_utils]              │
│                               ├───> [Task 1.3: pdf_stream]             │
│                               ├───> [Task 1.4: atomic_write]           │
│                               └───> [Task 1.5: central docs]           │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│ Track 2: Cloud & Storage Sync │               │ Track 3: Typography & Streams │
│ [Task 2.1: GCS Batch Service] │               │ [Task 3.1: Cost Estimator]    │
│ [Task 2.2: Glossary Sync Mgr] │               │ [Task 3.2: Fraktur Classifier]│
│ [Task 2.3: Lifecycle Cleanup] │   PARALLEL    │ [Task 3.3: TrueType LRU Cache]│
│ [Task 2.4: BYOK & Drive Exp]  │  ◄─────────►  │ [Task 3.4: Dual-Pane Viewer]  │
│ [Task 2.5: TSV Compilers]     │               └───────────────┬───────────────┘
└───────────────┬───────────────┘                               │
                │                                               │
                └───────────────────────┬───────────────────────┘
                                        │
                                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 4: Linguistic Analysis & Choice Conflict Optimization            │
│ [Task 4.1: is_german_compound_word in language_utils]                  │
│ [Task 4.2: Delegate confidence/morphology/neologism compound checks]   │
│ [Task 4.3: Bucketed detect_choice_conflicts in user_choice_models]     │
└───────────────────────────────────────┬────────────────────────────────┘
                                        │
                                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Track 5: Verification, Benchmarking & Test Suite Validation            │
│ [Task 5.1: Dedicated Unit Tests tests/test_dry_helpers.py]             │
│ [Task 5.2: Full Regression Test Suite Run & Coverage Verification]     │
│ [Task 5.3: Ruff Linting & Static Code Quality Verification]            │
└────────────────────────────────────────────────────────────────────────┘
```

> [!TIP] PARALLEL EXECUTION
> Tracks 2 and 3 can be developed and reviewed concurrently once Track 1 foundation modules are in place. Track 4 is logically independent and can also be developed in parallel.

---

## 3. Detailed Work Packages

### Track 1: Foundation Utility Modules & Central Documentation

#### Task 1.1: Implement `utils/gcp_helpers.py` [FR-01, FR-02, US-01, US-02]
* **Dependencies**: None.
* **Goal**: Provide canonical GCS URI parser, safe blob deletion, glossary resource name formatter, and resilient exponential backoff retry.
* **Acceptance Criteria**:
  - `parse_gcs_uri(gcs_uri: str) -> tuple[str, str]` splits valid `gs://bucket/blob` URIs and raises `ValueError` on malformed inputs.
  - `delete_gcs_blob(storage_client, gcs_uri: str) -> bool` suppresses `google.api_core.exceptions.NotFound` and returns True on successful or idempotent deletion.
  - `format_gcp_glossary_name(project_id: str, location: str, glossary_id: str) -> str` returns standard GCP resource path.
  - `is_transient_gcp_error(exc: Exception) -> bool` detects HTTP 429, 503, and gRPC 8, 14.
  - `retry_gcp_call` and `@retry_gcp_operation` retry transient errors up to `max_retries` with jittered exponential backoff.
* **Status**: [STATUS: PENDING]

#### Task 1.2: Implement `utils/tsv_utils.py` [FR-03, US-03]
* **Dependencies**: None.
* **Goal**: Provide zero-copy RFC 4180 TSV field escaping and deterministic byte serialization for GCP glossary synchronization.
* **Acceptance Criteria**:
  - `escape_rfc4180_field(val: str) -> str` returns `val` immediately if no delimiter characters (`\t`, `\n`, `\r`, `"`) exist, avoiding string copying.
  - Escapes fields containing special characters with double quotes and doubled quotes (`""`).
  - `format_tsv_bytes(entries: Mapping[str, str], header: tuple[str, str] = ("de", "en")) -> bytes` returns sorted UTF-8 TSV byte payload with trailing newline.
* **Status**: [STATUS: PENDING]

#### Task 1.3: Implement `utils/pdf_stream.py` [FR-04, US-04]
* **Dependencies**: None.
* **Goal**: Provide a deterministic context manager for PDF source normalization that guarantees file descriptor cleanup (AGENTS.md §2.10) and measures file size without buffering.
* **Acceptance Criteria**:
  - `@contextmanager open_pdf_stream(source: Path | str | bytes | BinaryIO, label: str = "PDF") -> Iterator[tuple[BinaryIO, float]]`.
  - Normalizes `Path` and `str` by opening in `"rb"` mode and calculating file size via `os.path.getsize(source)`. Deterministically closes file in `finally`.
  - Normalizes `bytes` into `io.BytesIO(source)`. Closes in `finally`.
  - Normalizes seekable `BinaryIO` by rewinding to 0 and measuring size via `seek(0, 2)`. Does not close external stream in `finally`.
* **Status**: [STATUS: PENDING]

#### Task 1.4: Implement `atomic_write_json` and `atomic_write_text` in `utils/file_handler.py` [FR-09, US-09]
* **Dependencies**: None.
* **Goal**: Centralize crash-safe atomic file writes using tempfile, `os.fsync`, and atomic `os.replace`.
* **Acceptance Criteria**:
  - `atomic_write_json(target_path: Path, data: Any, indent: int = 2) -> None` writes JSON cleanly and renames atomically.
  - `atomic_write_text(target_path: Path, text: str, encoding: str = "utf-8") -> None` writes text cleanly and renames atomically.
* **Status**: [STATUS: PENDING]

#### Task 1.5: Create Centralized Documentation `docs/REUSABLE_HELPER_FUNCTIONS.md` [US-01 through US-09]
* **Dependencies**: Tasks 1.1, 1.2, 1.3, 1.4.
* **Goal**: Create codebase architectural note documenting all consolidated helper functions, signatures, complexity bounds, and canonical usage patterns as mandated by `/dry-helper-function-refactorer`.
* **Acceptance Criteria**:
  - Markdown reference document detailing modules, functions, parameters, exceptions, time/space complexity, and migration examples.
* **Status**: [STATUS: PENDING]

---

### Track 2: Cloud & Storage Service Integration

#### Task 2.1: Refactor `services/gcp_batch_translation_service.py` to use `utils/gcp_helpers.py` [FR-01, FR-02]
* **Dependencies**: Task 1.1.
* **Goal**: Eliminate redundant `_parse_gcs_uri` and inline retry loop in `GCPBatchTranslationService`.
* **Acceptance Criteria**:
  - `GCPBatchTranslationService` delegates `_parse_gcs_uri` to `utils.gcp_helpers.parse_gcs_uri`.
  - Replaces manual retry loop in `submit_batch_job` with `retry_gcp_call` or `@retry_gcp_operation`.
  - All existing tests in `tests/test_gcp_batch_translation_service.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 2.2: Refactor `services/glossary_sync_manager.py` to use `utils/gcp_helpers.py` [FR-01, FR-02]
* **Dependencies**: Task 1.1.
* **Goal**: Eliminate duplicated `_retry_with_backoff`, `_delete_gcs_blob`, and inlined GCS URI splits in `GlossarySyncManager`.
* **Acceptance Criteria**:
  - Delegates `_retry_with_backoff` to `utils.gcp_helpers.retry_gcp_call`.
  - Delegates `_delete_gcs_blob` to `utils.gcp_helpers.delete_gcs_blob`.
  - Delegates `_format_glossary_name` to `utils.gcp_helpers.format_gcp_glossary_name`.
  - All existing tests in `tests/test_glossary_sync_manager.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 2.3: Refactor `services/session_glossary_lifecycle.py` [FR-01, FR-09]
* **Dependencies**: Tasks 1.1, 1.4.
* **Goal**: Replace manual string splitting and non-atomic `write_text` in `SessionGlossaryLifecycleManager`.
* **Acceptance Criteria**:
  - Uses `parse_gcs_uri` and `delete_gcs_blob` in `cleanup_session_glossary`.
  - Replaces `meta_file.write_text(...)` in `_save_user_sessions` with `atomic_write_json`.
  - All existing tests in `tests/test_session_glossary_lifecycle.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 2.4: Refactor `services/byok_credentials_manager.py` and `services/google_drive_exporter.py` [FR-02]
* **Dependencies**: Task 1.1.
* **Goal**: Unify `_call_with_backoff` in credentials manager and Drive exporter with `utils.gcp_helpers`.
* **Acceptance Criteria**:
  - `BYOKCredentialsManager` delegates `_call_with_backoff` to `utils.gcp_helpers.retry_gcp_call`.
  - `GoogleDriveExporter` delegates `_call_with_backoff` to `utils.gcp_helpers.retry_gcp_call`.
  - Tests in `tests/test_byok_credentials_manager.py` and `tests/test_google_drive_exporter.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 2.5: Refactor `services/glossary_compiler.py` and `services/user_vocabulary_store.py` [FR-03]
* **Dependencies**: Task 1.2.
* **Goal**: Eliminate identical `_escape_rfc4180_field` and format loops.
* **Acceptance Criteria**:
  - `GlossaryCompiler` delegates `_escape_rfc4180_field` and `format_rfc4180_tsv` to `utils.tsv_utils`.
  - `UserVocabularyStore` delegates `_escape_rfc4180_field` and `export_tsv` to `utils.tsv_utils`.
  - Tests in `tests/test_glossary_compiler.py` and `tests/test_user_vocabulary_store.py` pass.
* **Status**: [STATUS: PENDING]

---

### Track 3: Typography, Stream Management & Fallback Optimization

#### Task 3.1: Refactor `services/cost_estimator.py` to use `utils/pdf_stream.py` [FR-04]
* **Dependencies**: Task 1.3.
* **Goal**: Replace custom `_open_source` with `open_pdf_stream` context manager.
* **Acceptance Criteria**:
  - `GCPCostEstimator.estimate_book_cost` uses `open_pdf_stream(source)`.
  - Preserves `_open_source` as a delegating backward-compatibility shim.
  - Tests in `tests/test_cost_estimator.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 3.2: Refactor and Optimize `services/fraktur_classifier.py` [FR-04, FR-06]
* **Dependencies**: Task 1.3.
* **Goal**: Route through `open_pdf_stream`, pre-compile `_FRAKTUR_FONT_RE`, and optimize ligature counts.
* **Acceptance Criteria**:
  - `FrakturClassifier.classify_script` uses `open_pdf_stream(source)`.
  - Replaces nested keyword loops with `_FRAKTUR_FONT_RE = re.compile(r"(?i)(" + "|".join(_FRAKTUR_FONT_KEYWORDS) + ")")`.
  - Ligature counting replaces `len(pattern.findall(text))` with string `.count("ſ")`, `.count("ﬆ")`, etc., reducing allocations to $O(1)$.
  - Tests in `tests/test_fraktur_classifier.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 3.3: Refactor and Memoize `services/fallback_translator.py` [FR-04, FR-05]
* **Dependencies**: Task 1.3.
* **Goal**: Route through `open_pdf_stream` and cache TrueType font parsing with `@functools.lru_cache`.
* **Acceptance Criteria**:
  - `FallbackPageTranslator` uses `open_pdf_stream(source)` in `translate_failed_pages`.
  - `_parse_ttf_metrics_and_cmap` is decorated with `@functools.lru_cache(maxsize=4)`.
  - Successive fallback pages reuse pre-parsed glyph metrics and cmap dictionaries in $O(1)$ time.
  - Tests in `tests/test_fallback_translator.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 3.4: Refactor `services/dual_pane_viewer.py` to use `utils/pdf_stream.py` [FR-04]
* **Dependencies**: Task 1.3.
* **Goal**: Replace duplicate `_open_source` in dual-pane viewer controller.
* **Acceptance Criteria**:
  - `DualPaneViewerController` uses `open_pdf_stream` in `_find_term_boxes_on_page` and `_render_page_image`.
  - Preserves `_open_source` as a delegating backward-compatibility shim.
  - Tests in `tests/test_dual_pane_viewer.py` pass.
* **Status**: [STATUS: PENDING]

---

### Track 4: Linguistic Analysis & Choice Conflict Optimization

#### Task 4.1: Implement `is_german_compound_word` in `utils/language_utils.py` [FR-07]
* **Dependencies**: None.
* **Goal**: Create unified, pre-compiled German compound word detector with fast-path length and uppercase checks.
* **Acceptance Criteria**:
  - `is_german_compound_word(word: str) -> bool` identifies valid philosophical compounds (`Wirklichkeitsbewusstsein`, `Lebensweltthematik`, `Bewusstseinsphilosophie`) and rejects non-compounds (`Bewusstsein`, `das`, `und`).
  - Uses module-level compiled regex objects and fast set lookups.
* **Status**: [STATUS: PENDING]

#### Task 4.2: Delegate Compound Word Checks Across Services [FR-07]
* **Dependencies**: Task 4.1.
* **Goal**: Replace duplicated `_is_compound_word` implementations in `ConfidenceScorer`, `MorphologicalAnalyzer`, and `NeologismDetector`.
* **Acceptance Criteria**:
  - `ConfidenceScorer._is_compound_word` delegates to `is_german_compound_word`.
  - `MorphologicalAnalyzer._is_compound_word` delegates to `is_german_compound_word`.
  - `NeologismDetector._is_compound_word` delegates to `is_german_compound_word`.
  - Tests in `tests/test_confidence_scorer.py`, `tests/test_neologism_detector.py`, and `tests/test_translation.py` pass.
* **Status**: [STATUS: PENDING]

#### Task 4.3: Optimize `detect_choice_conflicts` in `models/user_choice_models.py` [FR-08]
* **Dependencies**: None.
* **Goal**: Replace $O(N^2)$ all-pairs scan with term-bucketed comparison, reducing comparisons from $O(N^2)$ to $O(N + \sum K_i^2)$.
* **Acceptance Criteria**:
  - Choices are bucketed by `choice.neologism_term.lower()` before pairwise comparisons.
  - Zero comparisons are performed between choices with differing terms.
  - Returns identical conflict objects and classifications as previous implementation.
  - Tests in `tests/test_user_choice_models.py` and `tests/test_user_choice_manager.py` pass.
* **Status**: [STATUS: PENDING]

---

### Track 5: Verification, Benchmarking & Test Suite Validation

#### Task 5.1: Create Dedicated Unit Tests `tests/test_dry_helpers.py` [FR-01 through FR-09]
* **Dependencies**: Tracks 1 through 4.
* **Goal**: Comprehensive unit tests covering all new consolidated helper functions and edge cases.
* **Acceptance Criteria**:
  - Tests for `parse_gcs_uri` (valid, invalid scheme, missing blob).
  - Tests for `delete_gcs_blob` (mock storage client, NotFound suppression).
  - Tests for `retry_gcp_call` and `@retry_gcp_operation` (transient retry, max retries exhausted, non-transient re-raised).
  - Tests for `escape_rfc4180_field` and `format_tsv_bytes` (quoting, delimiter preservation, sorting).
  - Tests for `open_pdf_stream` (Path, str, bytes, seekable stream, automatic closure on exception).
  - Tests for `atomic_write_json` and `atomic_write_text`.
  - Tests for `is_german_compound_word`.
  - Tests for optimized `detect_choice_conflicts` ensuring identical behavior to the prior all-pairs scan.
* **Status**: [STATUS: PENDING]

#### Task 5.2: Execute Full Regression Test Suite & Measure Coverage [NFR-04, NFR-05]
* **Dependencies**: Task 5.1.
* **Goal**: Run complete test suite across all services to guarantee zero regressions and coverage $\ge 85\%$.
* **Acceptance Criteria**:
  - `.venv/bin/pytest tests/ --cov=services --cov=utils --cov=models --cov-fail-under=85` passes with exit code 0.
* **Status**: [STATUS: PENDING]

#### Task 5.3: Run Linter & Static Checks (`ruff check`) [NFR-05]
* **Dependencies**: Task 5.2.
* **Goal**: Verify code clean of warnings and formatting issues.
* **Acceptance Criteria**:
  - `.venv/bin/ruff check services/ utils/ models/ tests/` outputs clean with zero errors.
* **Status**: [STATUS: PENDING]
