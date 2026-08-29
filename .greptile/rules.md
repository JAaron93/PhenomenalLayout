# PhenomenalLayout: Greptile Reviewer Constitution & Behavioral Guardrails

## 1. Zero Contradictory / Oscillating Reviews (Anti-Oscillation Directive)
- Reviewers MUST NOT contradict previous review cycles. If a change was implemented to satisfy a Greptile review finding (e.g., enabling local workflows when `MEMORY_API_ENABLE_AUTH=false`), the reviewer MUST NOT flag the resolution from the opposite perspective in the subsequent cycle.
- Once a review thread is marked resolved and verified by test coverage, do not re-flag related defensive code unless there is a verified, critical code execution or injection exploit.

## 2. Authentication: Local Development vs. Production Multi-Tenancy
- **Local Dev Mode (`MEMORY_API_ENABLE_AUTH=false`)**: When authentication is globally disabled in configuration, the engine is operating in a trusted single-tenant local environment (or CI test suite). In this mode, do NOT flag callers passing `user_id` as a "multi-tenant security bypass."
- **Production Mode (`MEMORY_API_ENABLE_AUTH=true`)**: In production, authentication is enforced via JWT or API keys. Verify that unauthenticated callers cannot modify other users' resources.
- **Shared Namespaces**: In all modes, shared static namespaces (`default_user`, `anonymous`, `local_user`) must be rejected (`400 Bad Request` / `PermissionError`) to ensure user state isolation.

## 3. Gradio Interface Architecture
- Gradio operates as an interactive frontend where components pass values through Python function arguments (`user_id`, `auth_token`) and session state.
- Do NOT flag Gradio UI callbacks for accepting form values or helper authentication functions (`_authenticate_gradio_caller`). Gradio callbacks do not receive raw incoming HTTP `Authorization` headers directly from the browser.

## 4. Architectural Constitution (AGENTS.md & ADR 0001)
- **Zero Host PDF Storage**: All book PDFs reside in user GCS buckets or Google Drive; never request saving PDFs to host disk.
- **BYOK Credential Isolation**: Service account keys are ephemeral in memory; never suggest persisting them to SQLite or disk.
- **Regional Quotas**: Tier 2 glossaries use blue-green alternation bounded to 2 regional slots (`-a`/`-b`) in `us-central1`.
- **Unicode & CID Font Integrity**: Fallback rendering must use 16-bit sequential CIDs and format 4/12 TrueType CMaps, never lossy ASCII transliteration.
