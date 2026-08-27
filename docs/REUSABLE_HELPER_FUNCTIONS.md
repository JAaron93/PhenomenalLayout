# Centralized Codebase Guide: Reusable Helper Functions & Algorithmic Optimizations

This reference document catalogs all centralized, reusable helper functions across PhenomenalLayout following the Google Cloud Document Translation API migration. It serves as the single source of truth for standard utility patterns, computational complexity guarantees, and usage conventions.

---

## 1. Cloud & Storage Utilities (`utils/gcp_helpers.py`)

### 1.1 `parse_gcs_uri`
* **Location**: [`utils/gcp_helpers.py`](../utils/gcp_helpers.py)
* **Signature**: `parse_gcs_uri(gcs_uri: str) -> tuple[str, str]`
* **Purpose**: Deconstructs and validates fully qualified `gs://<bucket>/<blob>` Google Cloud Storage URIs into discrete `(bucket_name, blob_name)` components.
* **Complexity**: Time: $O(1)$, Space: $O(1)$.
* **Exceptions**: Raises `ValueError` if the URI does not begin with `"gs://"` or if the blob path is absent or empty.
* **Canonical Usage**:
  ```python
  from utils.gcp_helpers import parse_gcs_uri

  bucket_name, blob_name = parse_gcs_uri("gs://my-bucket/inputs/manuscript.pdf")
  ```

### 1.2 `delete_gcs_blob`
* **Location**: [`utils/gcp_helpers.py`](../utils/gcp_helpers.py)
* **Signature**: `delete_gcs_blob(storage_client: StorageClient, gcs_uri: str) -> bool`
* **Purpose**: Safely deletes a GCS blob referenced by its `gs://` URI. Automatically catches and suppresses `google.api_core.exceptions.NotFound` for idempotent teardown, logging any other unexpected failures.
* **Complexity**: Time: $O(1)$ network I/O, Space: $O(1)$.
* **Canonical Usage**:
  ```python
  from utils.gcp_helpers import delete_gcs_blob

  deleted = delete_gcs_blob(storage_client, "gs://my-bucket/staged/session-123.tsv")
  ```

### 1.3 `format_gcp_glossary_name`
* **Location**: [`utils/gcp_helpers.py`](../utils/gcp_helpers.py)
* **Signature**: `format_gcp_glossary_name(project_id: str, location: str, glossary_id: str) -> str`
* **Purpose**: Generates standard Google Cloud Translation v3 resource paths (`projects/{project_id}/locations/{location}/glossaries/{glossary_id}`). Automatically normalizes inputs that already carry a `projects/` prefix.
* **Complexity**: Time: $O(1)$, Space: $O(1)$.

### 1.4 `retry_gcp_call` and `@retry_gcp_operation`
* **Location**: [`utils/gcp_helpers.py`](../utils/gcp_helpers.py)
* **Signature**:
  - `retry_gcp_call(fn: Callable[..., T], *args, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0, **kwargs) -> T`
  - `@retry_gcp_operation(max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0)`
* **Purpose**: Retries callables upon encountering transient Google Cloud exceptions (`ResourceExhausted` / HTTP 429, `ServiceUnavailable` / HTTP 503, gRPC status 8 and 14) using truncated exponential backoff with $\pm 20\%$ random jitter to eliminate thundering herd behavior.
* **Complexity**: Time: $O(\text{attempts})$, Space: $O(1)$.
* **Canonical Usage**:
  ```python
  from utils.gcp_helpers import retry_gcp_call, retry_gcp_operation

  # Higher-order wrapper
  response = retry_gcp_call(translation_client.batch_translate_document, request=req)

  # Decorator
  @retry_gcp_operation(max_retries=3)
  def sync_glossary(name: str): ...
  ```

---

## 2. TSV Compilation Utilities (`utils/tsv_utils.py`)

### 2.1 `escape_rfc4180_field`
* **Location**: [`utils/tsv_utils.py`](../utils/tsv_utils.py)
* **Signature**: `escape_rfc4180_field(val: str) -> str`
* **Purpose**: Sanitizes strings for RFC 4180 TSV formatting. If the string contains tabs, newlines, carriage returns, or quotes, it wraps the token in quotes and doubles internal quotation marks (`""`). Features an **early return fast path** for tokens without delimiter characters, preventing unnecessary string memory allocation.
* **Complexity**: Time: $O(M)$, Space: $O(1)$ for tokens requiring no escaping.
* **Canonical Usage**:
  ```python
  from utils.tsv_utils import escape_rfc4180_field

  safe_field = escape_rfc4180_field('Geist\t"Mind"')  # -> '"Geist\t""Mind"""'
  ```

### 2.2 `format_tsv_bytes`
* **Location**: [`utils/tsv_utils.py`](../utils/tsv_utils.py)
* **Signature**: `format_tsv_bytes(entries: Mapping[str, str], header: tuple[str, str] = ("de", "en")) -> bytes`
* **Purpose**: Converts a mapping of `{term: translation}` into RFC 4180 compliant TSV byte streams sorted deterministically by key with a standard header row.
* **Complexity**: Time: $O(N \log N + M)$, Space: $O(M)$ output buffer.

---

## 3. PDF Stream Management (`utils/pdf_stream.py`)

### 3.1 `open_pdf_stream`
* **Location**: [`utils/pdf_stream.py`](../utils/pdf_stream.py)
* **Signature**: `@contextmanager open_pdf_stream(source: Path | str | bytes | BinaryIO, label: str = "PDF") -> Iterator[tuple[BinaryIO, float]]`
* **Purpose**: Universal input normalizer and file descriptor manager. Converts file paths, raw byte payloads, or open binary streams into a readable binary stream and accurate file size in MB.
* **Guarantees**:
  - **Deterministic Cleanup**: Files opened internally are deterministically closed on context exit, preventing file descriptor leaks in serverless runtimes (AGENTS.md §2.10).
  - **Automatic Rewind**: Existing seekable streams are rewound to position 0 and left open for external caller reuse.
  - **Zero Buffering for Paths**: Measures disk size via `os.path.getsize(path)` without reading entire files into memory.
* **Complexity**: Time: $O(1)$, Space: $O(1)$ memory.
* **Canonical Usage**:
  ```python
  from utils.pdf_stream import open_pdf_stream

  with open_pdf_stream(source) as (stream, file_size_mb):
      reader = pypdf.PdfReader(stream)
      page_count = len(reader.pages)
  ```

---

## 4. Crash-Safe File Persistence (`utils/file_handler.py`)

### 4.1 `atomic_write_json` and `atomic_write_text`
* **Location**: [`utils/file_handler.py`](../utils/file_handler.py)
* **Signatures**:
  - `atomic_write_json(target_path: Path, data: Any, indent: int = 2) -> None`
  - `atomic_write_text(target_path: Path, text: str, encoding: str = "utf-8") -> None`
* **Purpose**: Atomically persists data to disk by writing to a temporary file in the target parent directory, executing `flush()` and `os.fsync()`, and performing an atomic rename via `os.replace()`. Prevents file corruption if the Modal container scales down mid-write.
* **Complexity**: Time: $O(M)$, Space: $O(M)$ disk temporary allocation.

---

## 5. Linguistic & Morphological Utilities (`utils/language_utils.py`)

### 5.1 `is_german_compound_word`
* **Location**: [`utils/language_utils.py`](../utils/language_utils.py)
* **Signature**: `is_german_compound_word(word: str) -> bool`
* **Purpose**: Consolidated German philosophical compound word identifier. Employs pre-compiled module-level regular expressions, minimum-length guards, uppercase noun checks, and set lookups for philosophical endings (`bewusstsein`, `wirklichkeit`, `erkenntnis`, `wahrnehmung`).
* **Complexity**: Time: $O(\text{len}(word))$, Space: $O(1)$. Replaces in-loop `re.compile()` calls across confidence scorers and morphological analyzers.

---

## 6. Choice Conflict Optimization (`models/user_choice_models.py`)

### 6.1 `detect_choice_conflicts`
* **Location**: [`models/user_choice_models.py`](../models/user_choice_models.py)
* **Signature**: `detect_choice_conflicts(choices: list[UserChoice], similarity_threshold: float = 0.8) -> list[ChoiceConflict]`
* **Optimization**: Replaces the unindexed $O(N^2)$ nested loop with a two-phase hash-bucket grouping:
  1. Phase 1: Group choices into `defaultdict(list)` by `choice.neologism_term.lower()` in $O(N)$ time.
  2. Phase 2: Iterate only over buckets containing $>1$ choice, performing comparisons strictly between choices with matching terms.
* **Complexity**: Time: $O(N + \sum K_i^2)$ where $K_i$ is the count of choices for term $i$. For $N=1,000$, comparisons drop from $\sim 500,000$ to $<100$ ($>99.9\%$ latency reduction).

---

## 7. TrueType Font Metrics Caching (`services/fallback_translator.py`)

### 7.1 `_parse_ttf_metrics_and_cmap`
* **Location**: [`services/fallback_translator.py`](../services/fallback_translator.py)
* **Optimization**: Decorated with `@functools.lru_cache(maxsize=4)`.
* **Purpose**: Prevents repeatedly unpacking 65 KB TrueType binary tables (`head`, `hhea`, `hmtx`, `cmap` format 4 & 12) for each failed layout page.
* **Complexity**: First call: $O(\text{TTF\_size})$. Subsequent calls: $O(1)$ memory lookup, amortizing table parsing across all pages.
