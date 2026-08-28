# Requirements Specification: GCP Translation Helpers Consolidation & Algorithmic Optimization

## 1. Overview & Scope

This specification defines the functional, non-functional, behavioral (BDD), and test-driven (TDD) requirements for consolidating redundant logic, eliminating duplicate helper algorithms, and optimizing computational complexity across the PhenomenalLayout codebase following the Google Cloud Document Translation API migration.

The core objectives are:
1. Extract duplicate cloud operations (GCS URI parsing, blob deletion, resource naming, exponential retry) into `utils/gcp_helpers.py`.
2. Extract duplicate RFC 4180 TSV escaping and formatting into `utils/tsv_utils.py`.
3. Provide a leak-proof, deterministic PDF source context manager in `utils/pdf_stream.py` ensuring compliance with AGENTS.md §2.10.
4. Eliminate redundant TrueType binary parsing in `FallbackPageTranslator` via LRU caching.
5. Accelerate `FrakturClassifier` font and ligature scanning from quadratic nested loops to compiled DFA searches and allocation-free counts.
6. Unify 3 redundant `_is_compound_word` implementations into a single pre-compiled helper in `utils/language_utils.py`.
7. Reduce `detect_choice_conflicts` from $O(N^2)$ to $O(N + \sum K_i^2)$ via hash-bucket grouping.
8. Standardize crash-safe atomic file writes in `utils/file_handler.py`.
9. Maintain 100% backward compatibility for all existing unit and integration tests.

---

## 2. User Stories (US)

### US-01: Reusable GCS URI & Cloud Storage Helper Operations
> **As a** platform developer integrating cloud translation services,  
> **I want** a unified utility to parse, validate, and manipulate GCS URIs and safely delete staged blobs,  
> **So that** I don't write ad-hoc string split operations and error handling in multiple services.

### US-02: Unified Exponential Backoff & Transient Error Handling
> **As a** batch translation pipeline maintainer,  
> **I want** a single, standardized retry mechanism with jittered exponential backoff for transient GCP HTTP 429/503 and gRPC errors,  
> **So that** transient network or quota spikes are handled consistently across all cloud interactions without thundering herd effects.

### US-03: Standardized RFC 4180 TSV Escaping and Zero-Copy Serialization
> **As a** glossary compiler developer,  
> **I want** a shared RFC 4180 TSV formatting and escaping module,  
> **So that** both `GlossaryCompiler` and `UserVocabularyStore` generate identical, compliant TSV bytes without code duplication or unnecessary string copying.

### US-04: Deterministic PDF Stream Normalization and Leak-Free Cleanup
> **As a** serverless deployment engineer on Modal Labs,  
> **I want** an atomic context manager that accepts file paths, raw bytes, or pre-opened binary streams and deterministically manages file descriptors,  
> **So that** file handle exhaustion is impossible even during high-concurrency document processing.

### US-05: TrueType Font Parsing Amortization in Fallback Engine
> **As a** user translating complex manuscripts where layout errors trigger the plaintext fallback engine,  
> **I want** TrueType font metrics and cmap tables to be cached across pages,  
> **So that** multi-page fallback synthesis does not incur heavy binary parsing latency on every page.

### US-06: High-Performance Fraktur Script Assessment
> **As a** scholar submitting historical German treatises,  
> **I want** font and ligature OCR script confidence scanning to execute rapidly without high memory allocations,  
> **So that** script classification for a 300-page book completes in sub-second time.

### US-07: Consolidated German Compound Word Detection
> **As an** NLP pipeline component,  
> **I want** a single, pre-compiled German compound word detection function,  
> **So that** confidence scoring, morphological analysis, and neologism detection share identical linguistic heuristics without recompiling regexes per word.

### US-08: Near-Linear-Time Choice Conflict Detection
> **As a** translator managing thousands of neologism choices across multiple books,  
> **I want** conflict detection to group choices by term before comparing similarity,  
> **So that** checking conflicts on large dictionaries executes in milliseconds rather than stalling on quadratic all-pairs loops.

### US-09: Crash-Safe Atomic Persistence for Modal Container Scale-Down
> **As a** system architect running stateful metadata managers on Modal Volumes,  
> **I want** session state and recovery data written atomically via temporary files and fsync,  
> **So that** sudden container scale-down cannot corrupt JSON state files.

---

## 3. Functional Requirements & BDD Scenarios

### FR-01: GCS URI Parsing and Manipulation (`utils/gcp_helpers.py`)
- **FR-01.1**: The system SHALL provide `parse_gcs_uri(gcs_uri: str) -> tuple[str, str]` that splits valid `gs://<bucket>/<blob>` URIs into `(bucket_name, blob_name)`.
- **FR-01.2**: The system SHALL raise `ValueError` if the URI does not start with `gs://` or is missing the blob component.
- **FR-01.3**: The system SHALL provide `delete_gcs_blob(storage_client, gcs_uri: str) -> bool` that safely deletes blobs, suppresses `NotFound`, and logs errors.
- **FR-01.4**: The system SHALL provide `format_gcp_glossary_name(project_id: str, location: str, glossary_id: str) -> str`.

#### BDD Scenario: Parse Valid and Invalid GCS URIs
```gherkin
Feature: GCS URI Parsing
  Scenario: Parse valid GCS URI
    Given a GCS URI "gs://user-bucket/inputs/book_101.pdf"
    When parse_gcs_uri is called
    Then the bucket name should be "user-bucket"
    And the blob path should be "inputs/book_101.pdf"

  Scenario: Reject invalid URI scheme
    Given an invalid URI "https://storage.googleapis.com/user-bucket/book.pdf"
    When parse_gcs_uri is called
    Then a ValueError should be raised with message containing "Invalid GCS URI"

  Scenario: Reject URI missing blob path
    Given an invalid URI "gs://user-bucket/"
    When parse_gcs_uri is called
    Then a ValueError should be raised with message containing "could not extract blob path"
```

### FR-02: Unified Exponential Backoff Retry (`utils/gcp_helpers.py`)
- **FR-02.1**: The system SHALL identify transient GCP errors including `ResourceExhausted` (429), `ServiceUnavailable` (503), and gRPC codes 8 and 14.
- **FR-02.2**: The system SHALL apply truncated exponential backoff with $\pm 20\%$ jitter up to `max_retries` (default 5).
- **FR-02.3**: The system SHALL provide both callable wrapper `retry_gcp_call` and decorator `@retry_gcp_operation`.

#### BDD Scenario: Transient Retry Resilience
```gherkin
Feature: GCP Retry with Exponential Backoff
  Scenario: Retry transient 429 error and succeed
    Given an API callable that raises ResourceExhausted twice before succeeding
    When retry_gcp_call is executed
    Then the function should be retried 2 times
    And the final successful result should be returned

  Scenario: Re-raise non-transient error immediately
    Given an API callable that raises PermissionDenied
    When retry_gcp_call is executed
    Then the PermissionDenied exception should be re-raised immediately without retries
```

### FR-03: RFC 4180 TSV Formatting (`utils/tsv_utils.py`)
- **FR-03.1**: The system SHALL escape fields containing `\t`, `\n`, `\r`, or `"` by wrapping in double quotes and doubling internal quotes (`""`).
- **FR-03.2**: The system SHALL return the original string untouched with zero allocation if no escaping character is present.
- **FR-03.3**: The system SHALL format a dictionary of term mappings into UTF-8 TSV bytes sorted alphabetically by key with header `de\ten\n`.

#### BDD Scenario: TSV Field Escaping
```gherkin
Feature: RFC 4180 TSV Serialization
  Scenario: Plain terms require no quotes
    Given term "Dasein" and translation "Being"
    When escape_rfc4180_field is called
    Then "Dasein" should be returned without quotes

  Scenario: Terms with quotes and tabs are escaped
    Given term 'Geist\t"Spirit"' and translation 'Spirit'
    When escape_rfc4180_field is called
    Then the escaped term should be '"Geist\t""Spirit"""'
```

### FR-04: Deterministic PDF Stream Normalization (`utils/pdf_stream.py`)
- **FR-04.1**: `open_pdf_stream` SHALL accept `Path`, `str`, `bytes`, and `BinaryIO`.
- **FR-04.2**: When given a `Path` or `str`, `open_pdf_stream` SHALL open the file, measure size via `os.path.getsize`, yield `(stream, size_mb)`, and close the file upon context exit.
- **FR-04.3**: When given seekable `BinaryIO`, `open_pdf_stream` SHALL rewind to position 0, measure size via `seek(0, 2)` then rewind to 0, yield `(stream, size_mb)`, and leave the external stream open upon context exit.
- **FR-04.4**: `open_pdf_stream` SHALL guarantee file descriptor release even when an exception is raised inside the context block.

#### BDD Scenario: Deterministic Stream Lifecycle
```gherkin
Feature: PDF Stream Normalization
  Scenario: Open file path and ensure closed
    Given a valid PDF file on disk
    When open_pdf_stream is entered as a context manager
    Then the yielded stream should be open and readable
    When the context block exits
    Then the stream file descriptor must be closed

  Scenario: Handle pre-opened seekable stream
    Given a BytesIO stream at position 50
    When open_pdf_stream is entered
    Then the stream position should be rewound to 0
    When the context block exits
    Then the stream should remain open for caller reuse
```

### FR-05: TrueType Font Parsing Memoization (`services/fallback_translator.py`)
- **FR-05.1**: `FallbackPageTranslator._parse_ttf_metrics_and_cmap` SHALL be wrapped with `@functools.lru_cache(maxsize=4)`.
- **FR-05.2**: Consecutive calls with identical font bytes SHALL return identical parsed metrics without re-parsing binary tables.

#### BDD Scenario: TrueType Font Caching
```gherkin
Feature: Font Parsing Memoization
  Scenario: Multiple fallback pages reuse parsed font tables
    Given font bytes for Vera.ttf
    When _parse_ttf_metrics_and_cmap is called for page 1
    And _parse_ttf_metrics_and_cmap is called for page 2
    Then the second call should return cached data in O(1) time
```

### FR-06: Fraktur Classifier Optimization (`services/fraktur_classifier.py`)
- **FR-06.1**: Font keyword matching SHALL use a single module-level pre-compiled regex `_FRAKTUR_FONT_RE`.
- **FR-06.2**: Single-character ligature counting SHALL use string `.count()` rather than `re.findall`.
- **FR-06.3**: `FrakturClassifier.classify_script` SHALL route PDF opening through `open_pdf_stream`.

### FR-07: Consolidated German Compound Detection (`utils/language_utils.py`)
- **FR-07.1**: `is_german_compound_word(word: str) -> bool` SHALL identify noun compounds, linking morphemes, and philosophical endings using module-level pre-compiled regexes.
- **FR-07.2**: `ConfidenceScorer`, `MorphologicalAnalyzer`, and `NeologismDetector` SHALL delegate their internal `_is_compound_word` methods to `is_german_compound_word`.

### FR-08: Choice Conflict Detection Optimization (`models/user_choice_models.py`)
- **FR-08.1**: `detect_choice_conflicts` SHALL bucket choices by `neologism_term.lower()` before executing pairwise similarity checks.
- **FR-08.2**: Pairs of choices with different terms SHALL NOT be evaluated for context similarity.
- **FR-08.3**: For a dataset of 1,000 choices with 10 actual conflicts, conflict detection SHALL complete in $< 50\text{ms}$.

### FR-09: Crash-Safe Atomic Persistence (`utils/file_handler.py`)
- **FR-09.1**: `atomic_write_json(target_path: Path, data: Any, indent: int = 2) -> None` SHALL write to a temporary file in `target_path.parent`, flush, `os.fsync`, and atomically rename via `os.replace`.
- **FR-09.2**: `SessionGlossaryLifecycleManager._save_user_sessions` and `BatchJobRecoveryManager` SHALL use this atomic helper.

---

## 4. Non-Functional Requirements (NFR)

- **NFR-01: Time Complexity**:
  - `detect_choice_conflicts` time complexity SHALL be $O(N + \sum K_i^2)$ where $K_i$ is terms per bucket, replacing $O(N^2)$.
  - `is_german_compound_word` SHALL execute in $O(\text{len}(word))$ with zero runtime regex compilation.
  - `_parse_ttf_metrics_and_cmap` SHALL execute in $O(1)$ on cache hits.
- **NFR-02: Space Complexity & Allocations**:
  - `FrakturClassifier` ligature counting SHALL allocate $O(1)$ memory instead of allocating 7 regex match lists per page.
  - `escape_rfc4180_field` SHALL return the input string unmodified without string copying when no escaping is needed.
- **NFR-03: Descriptor Safety**:
  - Zero open file descriptor leaks when opening PDF documents across all helper-using services (AGENTS.md §2.10).
- **NFR-04: Backward Compatibility**:
  - All existing public and private service methods (`_open_source`, `_parse_gcs_uri`, `_escape_rfc4180_field`, `_is_compound_word`) SHALL remain accessible as delegating shims so existing tests pass without modification.
- **NFR-05: Test Coverage & Verification**:
  - Total repository test coverage SHALL remain $\ge 85\%$ (pytest-cov fail-under threshold).
  - All code SHALL pass `ruff check` with zero warnings.

---

## 5. Traceability Matrix

| Requirement | User Story | Affected Files / Modules | Optimized Complexity |
| :--- | :--- | :--- | :--- |
| **FR-01** | US-01 | `utils/gcp_helpers.py`, `services/gcp_batch_translation_service.py`, `services/glossary_sync_manager.py`, `services/session_glossary_lifecycle.py` | Time: $O(1)$, Space: $O(1)$ |
| **FR-02** | US-02 | `utils/gcp_helpers.py`, `services/byok_credentials_manager.py`, `services/google_drive_exporter.py` | Time: $O(1)$ per retry, Space: $O(1)$ |
| **FR-03** | US-03 | `utils/tsv_utils.py`, `services/glossary_compiler.py`, `services/user_vocabulary_store.py` | Time: $O(M)$ early exit, Space: $O(1)$ unescaped |
| **FR-04** | US-04 | `utils/pdf_stream.py`, `services/cost_estimator.py`, `services/fraktur_classifier.py`, `services/fallback_translator.py`, `services/dual_pane_viewer.py` | Time: $O(1)$, Space: $O(1)$ FD-safe |
| **FR-05** | US-05 | `services/fallback_translator.py` | Time: $O(1)$ cache hit, Space: $O(G)$ single cache |
| **FR-06** | US-06 | `services/fraktur_classifier.py` | Time: $O(M)$ DFA, Space: $O(1)$ count |
| **FR-07** | US-07 | `utils/language_utils.py`, `services/confidence_scorer.py`, `services/morphological_analyzer.py`, `services/neologism_detector.py` | Time: $O(L)$ precompiled, Space: $O(1)$ |
| **FR-08** | US-08 | `models/user_choice_models.py`, `services/user_choice_manager.py` | Time: $O(N + \sum K_i^2)$, Space: $O(N)$ bucket |
| **FR-09** | US-09 | `utils/file_handler.py`, `services/session_glossary_lifecycle.py`, `services/batch_job_recovery.py` | Time: $O(N)$ fsync, Space: $O(N)$ temp file |
