# ADR 0004: Retire the Lingo.dev Translation Stack — GCP Document Translation as the Sole Engine (Sync + Batch Tiers)

## Status
**Proposed** — flips to **Accepted** upon completion of the execution tracks in
`.kiro/specs/lingo-dev-retirement/tasks.md`.

## Date
2026-11-03

## Context & Problem Statement

The Lingo.dev integration is the oldest surviving translation layer in
PhenomenalLayout: it predates both the Dolphin OCR era (retired under ADR 0001)
and the GCP-only doctrine (ADR 0002, Decision D2). ADR 0002 declared that
"Google Cloud Document Translation is the exclusive translation engine" and
deleted the local plaintext fallback engine — but the *content translation
path* was never migrated, and the Lingo.dev stack (REST client + MCP server
client) remained in the live production wiring.

A full audit (2026-11-03) verified the following **live** references in the
current tree:

| Surface | Location | Binding |
| :--- | :--- | :--- |
| Singleton engine | `core/translation_handler.py:62` | `TranslationService()` registers `providers["lingo"]` as its only provider (`services/translation_service.py:345-350`) |
| Document job flow | `core/translation_handler.py:501-513` | `await translation_service.translate_batch(...)` |
| Upload hint string | `core/translation_handler.py:898` | "Translation service: Lingo.dev API" |
| Philosophy wrapper | `services/philosophy_enhanced_translation_service.py:214,381,534,760,922` | Delegates `translate_text`, `translate_batch`, `translate_document` |
| API surface | `api/routes.py:29-37,61-63,160-246` | `/upload`, `/translate`, `/status`, `/download`, `/philosophy/*` (config endpoint exposes the `lingo` provider) |
| App lifecycle | `app.py:25,149` | Imports and `aclose()`s the Lingo-backed singleton on shutdown |

Additional residue:

* `services/mcp_lingo_client.py` — spawns an `npx -y lingo.dev mcp` stdio child
  process (dead-on-arrival on Modal serverless where no Node runtime is
  guaranteed), with a defensively decoupled `import mcp`.
* `services/parallel_translation_service.py` (`ParallelLingoTranslator`) and
  `services/enhanced_translation_service.py` — orphaned from production; only
  reachable from `examples/parallel_translation_demo.py`.
* Package manifest: `requirements.in:18` pins `mcp>=2.2.0,<3.0` solely for the
  Lingo MCP client.
* Configuration & docs: `.env.example:5-19` (LINGO block), `config/settings.py:393-394`,
  `pyproject.toml:8`, `scripts/run_tests_with_env.py`,
  `scripts/verify/verify_mcp_timeout_configuration.py`, README Lingo sections,
  `.kiro/steering/product.md:13`, `.kiro/steering/tech.md:82`.
* `tests/conftest.py:210` — "Set mock Lingo API key to ensure safe collection
  for **legacy** translation services."

### Violations of Existing Doctrine

1. **ADR 0002 D2 exclusivity (repo AGENTS §2.12)**: GCP v3 is doctrine'd as the
   exclusive engine, yet every non-book translation request still egresses to
   `https://api.lingo.dev/v1/translate`.
2. **BYOK billing/credential isolation (§2.3)**: the content path relies on a
   host-held `LINGO_API_KEY` — a server-side third-party API key, contradicting
   the Bring-Your-Own-Key cost model.
3. **Sole Translation Pipeline (§2.12)**: no Lingo eradication ADR ever existed;
   ADR 0001/0002 covered OCR and the plaintext fallback only.

---

## Decision

We adopt **Google Cloud Document Translation (v3) as the engine for the
content/sync tier** — the same `translate_v3.TranslationServiceClient` already
produced by `BYOKCredentialsManager.get_translation_client(user_id)` for the
book batch tier — and **permanently delete the Lingo.dev stack** (REST client,
MCP client, parallel-Lingo orphans, and all configuration/doc references).

### Architectural Decisions (D1–D7)

* **D1 — GCP Sync Tier as the Content Engine**: A new
  `services/gcp_sync_translation_service.py` provides
  `translate_text`, `translate_batch`, and `translate_document` via the v3
  client's synchronous methods (`translate_text`, `translateDocument`),
  honoring AGENTS §2.1 (sync tier = preview/sample tier; books remain on
  asynchronous `batchTranslateDocument`).
* **D2 — User-Scoped, Credential-Bound Engine Resolution**: There is **no**
  ambient, credentials-bearing global engine. Content endpoints resolve a
  per-request user-bound engine from the BYOK vault (`user_id`), following the
  identity pattern of `POST /book/translate` (`user_id` parameter +
  `get_current_user_dependency`). Every translation call requires the caller's
  own Google Cloud credentials from `BYOKCredentialsManager`.
* **D3 — Fail-Closed; Deleted, Not Disabled**: Requests without usable BYOK
  credentials fail immediately with a deterministic `GCP_CREDENTIALS_REQUIRED`
  document error (503 semantics). No silent fallback, no dormant Lingo provider
  behind a feature flag.
* **D4 — Engine Surface Parity**: The replacement preserves the duck-type
  contract consumed today — `translate_text`, `translate_batch`,
  `translate_document`, `get_available_providers`, `get_statistics`,
  `close`/`aclose` — plus the philosophy-layer `terminology_map` word-boundary
  substitution behavior, so `core/translation_handler.py`,
  `app.py:149`, and the philosophy service delegation points continue working
  without behavioral drift.
* **D5 — Eradication Inventory**: Delete
  `services/translation_service.py`, `services/mcp_lingo_client.py`,
  `services/parallel_translation_service.py`,
  `services/enhanced_translation_service.py`,
  `scripts/verify/verify_mcp_timeout_configuration.py`,
  `tests/test_lingo_translator.py`, `tests/test_translation_service.py`,
  `tests/test_parallel_translation.py`, `tests/services/test_mcp_lingo_client.py`,
  and every Lingo-specific fixture/env sticker (`.env.example`, settings,
  conftest, scripts, examples, README, steering docs).
* **D6 — Dependency Pruning**: Remove `mcp>=2.2.0,<3.0` from `requirements.in`,
  regenerate `requirements.txt`, and run the mandatory setup-script sweep
  (AGENTS §6.7) across `scripts/`, `Makefile`, `justfile`, and CI probes.
* **D7 — Governance Codification**: Extend `.greptile/rules.md` and
  `.greptile/instructions.md` with a Lingo Eradication section (mirroring the
  Dolphin section), add the deny-list row to AGENTS.md, and append the README
  migration-table row — so review agents never request restoration.

---

## Consequences

### Positive Consequences
* **True GCP-only posture**: both tiers (book batch + content sync) issue all
  translation calls through the same v3 API family and the same BYOK
  credential vault; ADR 0002 D2 becomes literally true.
* **Billing isolation restored**: no host-held third-party translation key;
  users pay for their own Google Cloud translation usage.
* **Operational simplification**: no `npx`/Node dependency, no MCP stdio
  process lifecycle, no sibling-timeout environment matrix, and the `mcp`
  SDK leaves the runtime dependency tree.
* **Full-time fail-closed behavior** replaces a legacy dual-provider registry.

### Negative Consequences & Trade-offs
* **User credentials now mandatory for content endpoints**: callers must have
  uploaded and validated BYOK credentials before `/translate` and
  `/philosophy/translate` work (setup-guide UI already exists via `/byok/*`).
* **Sync latency/quota characteristics** follow Google Cloud (rate limits,
  region latency) instead of Lingo.dev's.
* **Test-suite churn**: six legacy test files are replaced by a GCP-fake-based
  suite; coverage of deleted code disappears by construction (D6 gate stays at
  ≥ 70% per ADR 0002 D6).

---

## Implementation Tracks
* **Track A — GCP Sync Engine** (`services/gcp_sync_translation_service.py`): TDD-built engine + facade with `retry_gcp_call` backoff, terminology substitution parity, fail-closed credential gate.
* **Track B — Handler & API Rewiring**: `core/translation_handler.py` singleton → credential-bound resolution; `/translate` + `/philosophy/translate` identity params; `utils/document_errors.py` extension; `services/__init__.py` export symmetry.
* **Track C — Eradication & Pruning**: full-delete inventory (D5), dependency pruning (D6), governance docs (D7).
* **Track D — Test & Documentation Parity**: conftest fixture replacement, CI-exact serial parity run (`pytest --maxfail=1 --disable-warnings`), README/AGENTS/steering updates.

Execution order and task-level detail: `.kiro/specs/lingo-dev-retirement/tasks.md`.
