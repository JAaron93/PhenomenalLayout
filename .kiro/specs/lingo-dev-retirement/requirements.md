# Requirements: Lingo.dev Retirement — GCP Sync Engine

Derived from: `.kiro/specs/lingo-dev-retirement/design.md` and
`docs/adr/0004-retire-lingo-dev-translation-stack.md`.

## Glossary

| Term | Definition |
| :--- | :--- |
| **Sync Tier** | Synchronous GCP content translation (`translate_text`/`translateDocument`) — per-book sample pages and `/philosophy/*` text flows |
| **Batch Tier** | Asynchronous `batchTranslateDocument` book pipeline (ADR 0001) — unchanged by this spec |
| **User-Bound Engine** | A `GcpSyncTranslator` constructed against one `user_id`'s BYOK credentials |
| **Fail-Closed** | Missing credentials produce an explicit typed error; no silent provider substitution |

## User Stories

### US-1 — Scholar translating sample text
As a scholar, I want the philosophy-aware content endpoints to translate through
my own Google Cloud credentials, so that my verification snippets and choice
previews are billed to my account under my project's regional quotas.

### US-2 — Scholar without configured credentials
As a scholar who has not uploaded GCP credentials, I want a clear,
actionable error message on content translation, so that I am directed to the
existing BYOK onboarding guide rather than receiving a silent translation from a
hidden provider.

### US-3 — Operator / maintainer
As a maintainer, I want the Lingo.dev stack (REST + MCP) and its `mcp` SDK
dependency permanently removed, so that the runtime has no third-party
translation egress, no npx/Node dependency, and review agents can never request
restoration.

### US-4 — Reviewer (governance)
As a reviewer, I want README/steering/AGENTS documentation to match the
repository, so that no doc surface advertises a translation provider that no
longer exists.

---

## Functional Requirements

### FR-1 — GCP Sync Engine (US-1, ADR D1)
Shall provide `translate_text`, `translate_batch`, and `translate_document`
through `translate_v3` synchronous methods under `projects/{project}/locations/us-central1`.

1. WHEN `translate_text` is called with valid text THEN the engine SHALL issue a
   v3 `translateText` request and return the translated string.
2. WHEN `translate_batch` receives N strings THEN the engine SHALL chunk them by
   the configured batch size and preserve output ordering.
3. WHEN `translate_document` receives document bytes THEN the engine SHALL use
   `translateDocuments` with `DocumentInputConfig` (sync preview tier only).
4. IF a `terminology_map` is configured THEN the engine SHALL apply
   word-boundary-safe terminology substitution before remote calls.

### FR-2 — Credential-Bound Resolution (US-1/US-2, ADR D2)
1. WHEN a content translation request arrives THEN the system SHALL resolve a
   user-bound engine via `BYOKCredentialsManager` (no ambient engine).
2. WHEN `/translate` or `/philosophy/translate` is invoked THEN the endpoint
   SHALL require `user_id` and the standard auth dependency (mirroring
   `POST /book/translate`).
3. WHEN a background job translates document text THEN the job SHALL use the
   engine bound at submission time.

### FR-3 — Fail-Closed Gate (US-2, ADR D3)
1. WHEN `has_credentials(user)` is false THEN the system SHALL raise
   `GCP_CREDENTIALS_REQUIRED` mapped to HTTP 503 with onboarding guidance.
2. WHEN credentials exist but are stale THEN the system SHALL surface the
   validation error instead of silently substituting a provider.

```gherkin
Scenario: Content translation without credentials is refused explicitly
  Given a scholar identity "scholar-1" with no credentials in the BYOK vault
  When the scholar requests text translation on "/philosophy/translate"
  Then the response status is 503
  And the error code is "GCP_CREDENTIALS_REQUIRED"
  And the onboarding guide link "/api/v1/byok/onboarding-guide" is referenced
  And no request is made to any non-GCP translation service

Scenario: Content translation succeeds with user credentials
  Given a scholar identity "scholar-1" with validated credentials in the BYOK vault
  When the scholar requests text translation on "/philosophy/translate"
  Then the translation is executed through a cached "translate_v3" client
  And the returned text matches the translated output
  And no outbound request reaches "api.lingo.dev"
```

### FR-4 — Worldwide Lingo Eradication (US-3, ADR D5/D6)
1. WHEN Track C completes THEN the following SHALL not exist in the working
   tree: `services/translation_service.py`, `services/mcp_lingo_client.py`,
   `services/parallel_translation_service.py`,
   `services/enhanced_translation_service.py`,
   `scripts/verify/verify_mcp_timeout_configuration.py`, and the four legacy
   Lingo test modules.
2. WHEN dependencies are pruned THEN `mcp` SHALL be removed from
   `requirements.in`, `requirements.txt` regenerated, and the AGENTS §6.7
   setup-script sweep SHALL have run (`scripts/`, `Makefile`, `justfile`, CI probes).
3. WHEN any module in `services/`, `config/`, or `api/` is scanned THEN it
   SHALL contain no reference to Lingo, `lingo.dev`, or the `mcp` SDK import.

### FR-5 — Surface Parity (US-1, ADR D4)
Shall preserve the engine contract consumed by `core/translation_handler.py`,
`app.py:149`, `api/routes.py` config endpoints, and the philosophy delegation
points: `translate_text`, `translate_batch`, `translate_document`,
`get_available_providers` (`["gcp"]`), `get_statistics` (stable keys),
`close`/`aclose`, and `update_configuration` semantics.

### FR-6 — Governance Codification (US-4, ADR D7)
Shall update `.greptile/rules.md`, `.greptile/instructions.md`, AGENTS.md
(deny-list row), README (migration table + Lingo section removal), and
`.kiro/steering/*.md` so documentation matches the deleted tree.

---

## Non-Functional Requirements

### NFR-1 — Non-Blocking I/O (US-1)
Synchronous `google-cloud-translate` calls SHALL be dispatched via
`asyncio.to_thread` inside async engine methods (AGENTS deny row: blocking sync
I/O in async paths).

### NFR-2 — Canonical Helper Routing (US-1)
All GCP transient-error handling SHALL route through `utils.gcp_helpers`
(`retry_gcp_call`, `is_transient_gcp_error`) with truncated exponential backoff
and jitter; no bespoke retry loops.

### NFR-3 — Bounded PKG Concurrency (US-1)
Concurrent engine calls SHALL remain bounded by the existing
`TRANSLATION_CONCURRENCY_LIMIT`; no unbounded task spawning.

### NFR-4 — Test Isolation & Coverage (US-3)
1. CI SHALL require no real Google Cloud access for engine tests (fake BYOK
   manager + `translate_v3` facade).
2. The coverage gate SHALL remain ≥ 70% (`services`, `utils`, `models`) after
   deletions.
3. Green candidate SHALL pass both `pytest -n auto` and the CI-exact serial
   command `pytest --maxfail=1 --disable-warnings` before merge.

### NFR-5 — Dependency Hygiene (US-3)
`requirements.txt` SHALL be regenerated by `uv pip compile` and the setup script
health checks SHALL remain green (`§6.7` sweep — a broken setup script is
indistinguishable from a broken install).

---

## Traceability Matrix

| Req | Design § | ADR | Test Track |
| :--- | :--- | :--- | :--- |
| FR-1 | §3, §5, §7 | D1 | Track A |
| FR-2 | §4, §2 | D2 | Track A + B |
| FR-3 | §7 | D3 | Track A + B |
| FR-4 | §2, FR-4 | D5, D6 | Track C (eradication guards) |
| FR-5 | §3 | D4 | Track A + B |
| FR-6 | — | D7 | Track C + D |
| NFR-1 | §6 | D1 | Track A |
| NFR-2 | §5, §7 | D2.13-invariant | Track A |
| NFR-3 | §6 | 2.13-invariant | Track A |
| NFR-4 | §8 | D6-gated | Track A–D |
| NFR-5 | FR-4.2 | §6.7 | Track C |
