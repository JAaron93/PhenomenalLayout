# ADR 0003: Python 3.12+ Floor (PEP 695 Generics) & Runtime Dependency Lock Refresh

## Status
**Accepted**

## Date
2026-11-01

## Context & Problem Statement

The runtime dependency refresh in PR #153 (compiled via `uv pip compile` against Python 3.13) updated 65 of 586 locked pins — including `fastapi` 0.143.0→0.162.0, `anyio` 4.14.2→4.15.1, `cryptography` 50.0.1→50.0.2, `cloudpathlib` 0.25.0→0.26.0, `aiohttp` 3.14.4→3.14.5 — while the lint-hardening pass in the same PR migrated all generic type parameters to PEP 695 syntax.

PEP 695 generic classes and functions (`class CacheEntry[V]:`, `def _run_coro_sync[T](...)` in `core/dynamic_programming.py`, `services/glossary_sync_manager.py`, `services/philosophy_enhanced_translation_service.py`) parse only on Python 3.12+. Documented support was internally inconsistent: the README Sections listed "3.11 or 3.12 recommended", "3.11, 3.12, or 3.13 supported", and "3.13.x" simultaneously, `pyproject.toml` declared no `requires-python` and classified Python 3.8–3.13, and CONTRIBUTING.md claimed 3.11.

The toolchain had already de facto required 3.12 before PR #153:
* ruff `target-version = "py312"`, black `target-version = ['py312']`, mypy `python_version = "3.12"`.
* CI runs `python-version: '3.13'` in all three jobs.
* ruff `select` includes the `UP` rule group, where `UP047`/`UP049` (error tier) enforce PEP 695 generic syntax — legacy `Generic[T]`/`TypeVar` patterns fail lint CI.

## Decision

1. **Python 3.12+ is the supported floor**: `requires-python = ">=3.12"` is declared in the `[project]` table of `pyproject.toml` so the floor is machine-enforced by any installer or resolver. Classifiers are trimmed to Python 3.12 and 3.13.
2. **PEP 695 generic syntax is the project standard**: new generic classes/functions must use `class Foo[T]` / `def f[T](...)` intrinsic type parameters. Legacy `Generic[T]` base classes and hand-rolled `TypeVar` declarations are prohibited (enforced by ruff `UP047`/`UP049`).
3. **The dependency lock is refreshed as a single atomic refresh** (`requirements.txt` compiled from `requirements.in`), preserving the retired-package invariants (no `reportlab`/`pillow`/`gradio`/`pdf2image`; enforced by `tests/test_deployment_config.py::test_minimum_dependency_pins_present`).

## Consequences

* **Python 3.11 is no longer importable, by design**. Modules using PEP 695 syntax raise `SyntaxError` at import on ≤ 3.11. This is the accepted trade-off for intrinsic type parameters, which require no runtime `TypeVar` plumbing and are analyzed natively by mypy.
* Historical documents that reference Python 3.11 (`.kiro/specs/gcp-migration/design.md`, archived quest notes) remain accurate as point-in-time records and are intentionally **not** rewritten.
* Downstream consumers of this repository as a package are now constrained to ≥ 3.12 by metadata rather than discovering the floor via import failure.
* Future Python minor-version bumps must coordinate ruff/black/mypy target versions, CI matrices, classifiers, and `requires-python` together — partial updates caused the inconsistency this ADR resolves.

## References
* ADR 0001: cloud migration of layout/OCR responsibilities.
* ADR 0002: bespoke frontend and GCP-only translation.
* AGENTS.md §6.10 (PEP 695 + floor invariants) and §6.11 (legacy naive-timestamp normalization, established in the same PR).
