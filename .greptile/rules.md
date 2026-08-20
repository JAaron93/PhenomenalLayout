# Greptile Review Rules: PhenomenalLayout

## 1. Severity & Blocking Gates

### Blocking (Score: 1/5 or 2/5 - Must Request Changes)
1. **Security Vulnerabilities & Credential Leakage**:
   * Hardcoded GCP API keys, service account JSON files, or private credentials committed to Git.
   * Writing raw BYOK Service Account JSON keys to disk or logging them.
   * Cross-user session credential contamination.
2. **Reintroduction of Deprecated Engines**:
   * Creating new modules relying on Dolphin OCR, Modal GPU workers, or ReportLab canvas-overlay reconstruction.
3. **Broken Async / Blocking Network Calls**:
   * Running synchronous, blocking HTTP requests or blocking `time.sleep()` loops inside `async` coroutines.
4. **Invalid LRO Progress Contract**:
   * Checking invalid status fields (`SUCCESS`, `pages_completed`) instead of the official Translation v3 contract (`metadata.translated_pages`, `metadata.total_pages`, `SUCCEEDED` state).
5. **Absolute Worktree Links**:
   * Using machine-specific `file:///Users/...` links instead of repository-relative markdown paths.
6. **Missing Test Coverage**:
   * Adding new service or client logic without accompanying unit/integration tests (`tests/test_*.py`).

### Warnings (Score: 3/5 or 4/5 - Suggestions / Minor Fixes)
1. **Missing Type Annotations**:
   * Functions without explicit argument types or return annotations.
2. **Missing Retry & Backoff**:
   * External GCP API calls lacking exponential backoff handling for HTTP 429/503.
3. **Cost Estimator Precision**:
   * Failing to include both per-page rate ($0.080/page) and GCS staging buffer in quote calculations.
4. **Incomplete Docstrings**:
   * Public classes or methods missing descriptions of arguments and return types.

### Approval (Score: 5/5 - Ready to Merge)
* Zero blocking issues, clean test coverage ($\ge 90\%$), strict compliance with GCP Document Translation, BYOK, User Vocabulary Store, and Modal serverless architecture.

---

## 2. Terminology & Glossary Constraints
* TSV files generated for GCP glossaries must be strictly RFC 4180-compliant with format `source_code\ttarget_code`.
* Base terminology dictionaries ([`config/klages_terminology.json`](config/klages_terminology.json)) must not be deleted or mutated into incompatible schemas.
