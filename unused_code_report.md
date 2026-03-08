# Unused Code Report for PhenomenalLayout

## Summary

This report was revised by checking the current codebase references rather than relying only on static unused-code output.

### High-level conclusion

No, the original report was **not fully correct**.

It mixed together several different categories:

1. **Actually reachable production code**
   - especially FastAPI route handlers and Gradio-connected functions
2. **Test-only or example-only usage**
   - code that is unused in the main app, but still intentionally exercised elsewhere
3. **Currently unused extension points / future-facing code**
   - helpers, registries, wrappers, and configuration surfaces that look intentionally added for expansion
4. **Likely dead or currently disconnected code**
   - items with no meaningful references outside their own defining module

The biggest false positives in the original report were the claims that many API endpoints are unused/dead. In FastAPI and Gradio, decorators and UI wiring make code reachable even when static analyzers do not see a normal call site.

## Verification Method

This rewrite is based on verifying whether each reported item is:

- **Production-used**
- **Used only by tests/examples/scripts**
- **Future-facing / extension-oriented**
- **Likely dead or currently disconnected**

### Classification legend

- **Production-used**: reachable in the running app
- **Support-used**: used by tests, examples, or scripts, but not main runtime
- **Future-facing**: intentionally exposed or structured for expansion, but not presently wired into main flow
- **Likely dead**: no meaningful usage found beyond its own definition/module

---

## Corrected Findings by Area

## API Layer (`api/`)

### `api/auth.py`

#### `is_auth_enabled()`
**Classification:** Support-used  
**Verdict:** Not dead, but not production-critical.

This function is used by tests to verify auth behavior. It is not just dead code, but it also is not a core runtime path.

#### `require_role()`
**Classification:** Likely dead  
**Verdict:** Currently unused.

The decorator exists, but current route protection uses FastAPI dependencies like `get_admin_user()` and `get_read_only_user()` instead.

---

### `api/memory_routes.py`

#### Memory endpoints
- `get_memory_statistics()`
- `force_garbage_collection_endpoint()`
- `start_memory_monitoring_endpoint()`
- `stop_memory_monitoring_endpoint()`
- `get_monitoring_status()`

**Classification:** Production-used  
**Verdict:** False positive in original report.

These are included through `memory_router`, which is included in `api_router`, which is included in the app. They are active API routes, not dead code.

---

### `api/rate_limit.py`

#### `init_rate_limiter()`
**Classification:** Likely dead  
**Verdict:** Currently unused wrapper around lazy initialization.

#### `create_rate_limit_middleware()`
**Classification:** Likely dead  
**Verdict:** Middleware factory exists, but is not wired into the app.

#### `get_rate_limit_stats()`
**Classification:** Likely dead  
**Verdict:** Utility exists but no current consumers found.

#### `reset_rate_limits()`
**Classification:** Likely dead  
**Verdict:** Same as above.

> Note: the core rate-limiting path is still active via `check_rate_limit()` and `add_rate_limit_headers()` in memory routes. So this module is **partially used**, but these specific helper surfaces are not.

---

### `api/routes.py`

#### `philosophy_interface()`
**Classification:** Production-used  
**Verdict:** False positive.

This is a routed FastAPI endpoint mounted at `/philosophy`.

#### `get_detected_neologisms()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `get_philosophy_progress()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `export_user_choices()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `import_user_choices()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `get_terminology()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `get_job_status()`
**Classification:** Production-used  
**Verdict:** False positive.

#### `download_result()`
**Classification:** Production-used  
**Verdict:** False positive.

All of the above are FastAPI route handlers and are reachable through router registration.

---

## Configuration Layer (`config/`)

### `config/main.py`

#### `Config.validate_config()`
**Classification:** Likely dead  
**Verdict:** Currently unused in the main app.

`config.main.Config` appears to be an older or alternate configuration surface. The running application uses `config.settings.Settings` instead.

This whole module looks more like a disconnected configuration implementation than an active production dependency.

---

### `config/settings.py`

#### `HOST`
**Classification:** Likely dead  
**Verdict:** The app reads `HOST` directly from environment in `app.py`, not via `Settings.HOST`.

#### `LOG_LEVEL`
**Classification:** Support-used  
**Verdict:** Not dead. It is consumed by `dolphin_ocr.logging_config`.

#### `LOG_FILE`
**Classification:** Support-used  
**Verdict:** Not dead. Also consumed by `dolphin_ocr.logging_config`.

#### `CLEANUP_INTERVAL_HOURS`
**Classification:** Likely dead  
**Verdict:** Declared but no usage found.

#### `MAX_FILE_AGE_HOURS`
**Classification:** Likely dead  
**Verdict:** Declared but no usage found.

#### `get_available_translators()`
**Classification:** Likely dead  
**Verdict:** No active consumers found.

#### `validate_configuration()`
**Classification:** Likely dead  
**Verdict:** No active consumers found.

---

## Core Layer (`core/`)

### `core/dynamic_choice_engine.py`

#### Conflict enum members / fields reported as unused
- `SCOPE_CONFLICT`
- `CONFIDENCE_DISAGREEMENT`
- `CONTEXT_OVERLAP`
- `TEMPORAL_CONFLICT`
- `auto_resolve`
- `explanation`
- `user_preferences`
- `session_context`

**Classification:** Future-facing  
**Verdict:** Mostly intentional expansion surface.

This module is actively used through `OptimizedUserChoiceManager` in production and examples. The reported unused members are inside an otherwise active subsystem and look like reserved modeling/detail fields rather than dead code.

---

### `core/dynamic_language_engine.py`

#### `update_confidence_threshold()`
**Classification:** Likely dead  
**Verdict:** No usage found.

#### `_get_language_detector()`
**Classification:** Likely dead  
**Verdict:** No meaningful usage found; current `OptimizedLanguageDetector` instantiates directly.

---

### `core/dynamic_layout_engine.py`

#### `scale_calculation`, `lines_calculation`, `fallback_strategy`
**Classification:** Future-facing  
**Verdict:** Builder metadata/shape fields that are currently not heavily used but fit the abstraction.

#### `determine_strategy_with_context()`
**Classification:** Likely dead  
**Verdict:** No runtime consumers found.

#### `analyze_pattern_coverage()`
**Classification:** Likely dead  
**Verdict:** Analysis helper with no current consumers.

#### `benchmark_performance()`
**Classification:** Support-used  
**Verdict:** Exposed through the wrapper and useful for benchmarking/tests, but not main runtime.

> Important nuance: the module itself is definitely **not dead**. `DynamicLayoutEngine` and `OptimizedLayoutPreservationEngine` are used by tests and integration paths. Only some auxiliary methods look unused.

---

### `core/dynamic_programming.py`

#### `TTL`
**Classification:** False positive  
**Verdict:** This is an enum value in `CachePolicy`, not dead code in the normal sense.

#### `last_accessed`
**Classification:** Future-facing  
**Verdict:** Stored metadata that supports cache bookkeeping and potential diagnostics.

#### `insertion_order`
**Classification:** False positive / implementation detail  
**Verdict:** Used as an LFU heap tie-breaker.

#### `get_registered_keys()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `add_child()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `strategy_count`
**Classification:** Likely dead  
**Verdict:** Public convenience property; no consumer found.

#### `DynamicFactory`
**Classification:** Likely dead  
**Verdict:** Generic infrastructure with no current consumers found.

#### `get_registered_types()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `clear_all_registries()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

---

### `core/dynamic_validation_engine.py`

#### `cached`
#### `dependencies_satisfied`
**Classification:** Future-facing  
**Verdict:** Data-model/reporting fields, not evidence of dead logic by themselves.

#### `validate_batch()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `get_validation_summary()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `benchmark_vs_sequential()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `get_registered_validators()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `register_validation_engine()`
**Classification:** Likely dead  
**Verdict:** Extension point, but presently unused.

#### `get_validation_engine()`
**Classification:** Likely dead  
**Verdict:** Same as above.

> But the module itself is active: `OptimizedFileValidator` is used by `core.translation_handler`.

---

### `core/state_manager.py`

#### `backup_path`
**Classification:** Future-facing  
**Verdict:** State field reserved for additional file/state backup handling.

#### Job management helpers
- `get_job()`
- `update_job()`
- `remove_job()`
- `get_all_jobs()`

**Classification:** Likely dead  
**Verdict:** The runtime mainly uses mapping-style access on `translation_jobs`, not these helpers.

#### `force_cleanup()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `session_state()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `get_request_state()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

---

### `core/translation_handler.py`

#### `process_file_upload_sync()`
**Classification:** Production-used  
**Verdict:** False positive.

Used by the Gradio UI.

#### `start_translation_sync()`
**Classification:** Production-used  
**Verdict:** False positive.

Used by the Gradio UI.

#### `update_translation_progress()`
**Classification:** Likely dead  
**Verdict:** No active consumer found.

#### `get_translation_status()`
**Classification:** Production-used  
**Verdict:** False positive.

Used by the Gradio UI.

#### `download_translated_file()`
**Classification:** Production-used  
**Verdict:** False positive.

Used by the Gradio UI.

---

## Services Layer (`services/`)

### `services/__init__.py`

#### Availability flags and exported service summary
- `NEOLOGISM_DETECTOR_AVAILABLE`
- `TRANSLATION_SERVICE_AVAILABLE`
- `LANGUAGE_DETECTOR_AVAILABLE`
- `ENHANCED_DOCUMENT_PROCESSOR_AVAILABLE`
- `AVAILABLE_SERVICES`

**Classification:** Likely dead  
**Verdict:** Export bookkeeping with no meaningful consumers found.

These do not appear harmful, but they also do not seem active in the app.

---

### `services/confidence_scorer.py`

#### Methods reported unused
- `update_corpus_frequencies()`
- `calculate_final_confidence()`
- `get_confidence_breakdown()`
- `adjust_confidence_threshold()`
- `validate_confidence_factors()`
- `update_patterns()`
- `update_philosophical_indicators()`

**Classification:** Future-facing  
**Verdict:** Mostly extension/configuration/inspection methods on an otherwise active component.

`ConfidenceScorer` itself is used by `services.neologism_detector`, so these are not isolated dead code in a dead module. They look like API surface added for tuning and diagnostics.

---

### `services/dolphin_client.py`

#### `DEFAULT_LOCAL_ENDPOINT`
**Classification:** Future-facing  
**Verdict:** Reasonable fallback/alternate deployment constant.

The client currently defaults to `DEFAULT_MODAL_ENDPOINT`, but keeping a local endpoint constant appears intentional, not dead.

---

### `services/dolphin_modal_service.py`

#### `initialize_model()`
**Classification:** Production-used in deployment context  
**Verdict:** False positive if Modal deployment is in scope.

This is a lifecycle hook for the Modal class.

#### `dolphin_ocr_endpoint()`
**Classification:** Production-used in deployment context  
**Verdict:** False positive if this deployment target is still intended.

#### `add_security_headers()`
**Classification:** Production-used in deployment context  
**Verdict:** Nested middleware inside the Modal ASGI app.

#### `health()`
**Classification:** Production-used in deployment context / support-used elsewhere  
**Verdict:** Not dead.

#### `landing()`
**Classification:** Production-used in deployment context  
**Verdict:** Not dead.

> These items may be unused by the main local app, but they are part of a deployable service surface, so they should not be labeled dead code.

---

### `services/dolphin_ocr_service.py`

#### `last_duration_ms`
**Classification:** Future-facing / telemetry-used  
**Verdict:** Not dead.

This is written during request metric recording and is part of internal observability state.

---

### `services/enhanced_document_processor.py`

#### `_generate_text_preview()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `convert_format()`
**Classification:** Likely dead  
**Verdict:** No current consumers found.

#### `generate_preview()`
**Classification:** Likely dead  
**Verdict:** No current consumers found.

> The processor itself is active in production. These appear to be unused helper methods on an otherwise used class.

---

### `services/enhanced_translation_service.py`

#### `_translate_batch_parallel()`
**Classification:** Future-facing  
**Verdict:** Internal capability for parallel path; currently not externally exercised directly.

#### `translate_document_enhanced()`
**Classification:** Future-facing / support-used  
**Verdict:** This service is referenced by examples/tests and by philosophy-enhanced components, but not main app flow.

#### `reset_performance_stats()`
**Classification:** Likely dead  
**Verdict:** No consumer found.

#### `create_enhanced_translation_service()`
**Classification:** Support-used / future-facing  
**Verdict:** Convenience constructor used outside core app runtime.

---

### `services/neologism_detector.py`

#### `chunk_idx`
**Classification:** False positive  
**Verdict:** Loop variable used during chunk processing.

#### `merge_neologism_analyses()`
**Classification:** Future-facing  
**Verdict:** Thin convenience wrapper; no active consumers found.

---

### `services/parallel_translation_service.py`

#### `rate_limit_window`
**Classification:** Future-facing  
**Verdict:** Config surface present but not strongly wired into the active limiter logic.

#### `failed_tasks`
**Classification:** Production-used / model field  
**Verdict:** Not dead; this is part of `BatchProgress` state.

The original report overcalled this one.

---

### `services/pdf_document_reconstructor.py`

#### `layout_strategy`
**Classification:** Production-used as data field  
**Verdict:** False positive.

This is a field on `TranslatedElement`, part of the data model for reconstruction/pipeline interoperability.

---

### `services/pdf_quality_validator.py`

#### `DEFAULT_OCR_TIMEOUT_S`
**Classification:** Likely dead  
**Verdict:** Declared, but current code does not appear to use it.

#### `validate_pdf_reconstruction_quality()`
**Classification:** Future-facing / support-used  
**Verdict:** Useful validation helper, but no active consumer found.

---

### `services/philosophical_context_analyzer.py`

#### `update_terminology_map()`
**Classification:** Future-facing  
**Verdict:** No current consumers found, but clearly intended as runtime mutator for analyzer state.

---

### `services/philosophy_enhanced_translation_service.py`

#### `update_configuration()`
**Classification:** Future-facing  
**Verdict:** No active consumers found.

#### `translate_with_philosophy_awareness()`
**Classification:** Future-facing / support-used  
**Verdict:** Public convenience API, but not in the main application path.

---

## Models Layer (`models/`)

### `models/neologism_models.py`

#### `filter_neologisms_by_confidence()`
**Classification:** Likely dead  
**Verdict:** No consumers found.

#### `sort_neologisms_by_confidence()`
**Classification:** Likely dead  
**Verdict:** No consumers found.

---

### `models/user_choice_models.py`

#### `USER_PROMPT`
**Classification:** Future-facing  
**Verdict:** Enum member for conflict resolution strategy; not dead in the normal sense.

#### `SUSPENDED`
**Classification:** Future-facing  
**Verdict:** Enum member for session lifecycle; not dead in the normal sense.

#### `TranslationPreference`
**Classification:** Likely dead  
**Verdict:** No current consumers found.

#### Preference methods
- `update_language_preference()`
- `update_domain_preference()`
- `get_language_preference()`
- `get_domain_preference()`

**Classification:** Likely dead  
**Verdict:** No current consumers found.

---

## Major Corrections from the Original Report

## Items incorrectly labeled as unused/dead

These are **active production paths** and should not be considered dead code:

- All memory API route handlers in `api/memory_routes.py`
- Most route handlers in `api/routes.py`
- `core.translation_handler.process_file_upload_sync()`
- `core.translation_handler.start_translation_sync()`
- `core.translation_handler.get_translation_status()`
- `core.translation_handler.download_translated_file()`

These are reachable through:
- FastAPI router registration
- Gradio event wiring
- app startup/mounting

## Items that are not dead, but mostly support/deployment/future-facing

- `api.auth.is_auth_enabled()`
- `services.dolphin_modal_service` deployment endpoints/helpers
- `services.dolphin_client.DEFAULT_LOCAL_ENDPOINT`
- many tuning/inspection helpers in `services.confidence_scorer.py`
- `services.philosophy_enhanced_translation_service.translate_with_philosophy_awareness()`

## Items likely truly unused right now

The strongest candidates for actual cleanup later are:

- `api.auth.require_role()`
- `api.rate_limit.init_rate_limiter()`
- `api.rate_limit.create_rate_limit_middleware()`
- `api.rate_limit.get_rate_limit_stats()`
- `api.rate_limit.reset_rate_limits()`
- `config.main.Config.validate_config()` and likely much of `config/main.py`
- `config.settings.get_available_translators()`
- `config.settings.validate_configuration()`
- `core.dynamic_language_engine.update_confidence_threshold()`
- `core.dynamic_language_engine._get_language_detector()`
- `core.dynamic_programming.DynamicFactory`
- `core.dynamic_programming.get_registered_keys()`
- `core.dynamic_programming.get_registered_types()`
- `core.dynamic_programming.clear_all_registries()`
- `core.dynamic_validation_engine.validate_batch()`
- `core.dynamic_validation_engine.get_validation_summary()`
- `core.dynamic_validation_engine.benchmark_vs_sequential()`
- `core.state_manager` helper methods around jobs/session state
- `core.translation_handler.update_translation_progress()`
- `services.enhanced_document_processor._generate_text_preview()`
- `services.enhanced_document_processor.convert_format()`
- `services.enhanced_document_processor.generate_preview()`
- `models.neologism_models.filter_neologisms_by_confidence()`
- `models.neologism_models.sort_neologisms_by_confidence()`
- `models.user_choice_models.TranslationPreference` and its preference methods

---

## Recommended Cleanup Strategy

When you move on to actual cleanup, these groups should be treated differently:

### Safe to review for removal first
- isolated helpers with no consumers
- alternate config surfaces not used by runtime
- unused registries/factories/convenience wrappers

### Keep unless product direction changes
- FastAPI route handlers
- Gradio-connected translation helpers
- Modal deployment service code
- extension-oriented abstractions in active subsystems

### Keep but document as future-facing
- mutator/configuration helpers in philosophy/neologism subsystems
- benchmarking/reporting APIs
- registry-based extension points

## Phased Cleanup Plan (Safest Removals First)

### [x] Phase 1 — Lowest-risk removals 
These are the safest first-pass candidates because they appear isolated, have no meaningful consumers, and do not sit on important runtime paths.

#### API helpers
- `api.auth.require_role()`
- `api.rate_limit.init_rate_limiter()`
- `api.rate_limit.create_rate_limit_middleware()`
- `api.rate_limit.get_rate_limit_stats()`
- `api.rate_limit.reset_rate_limits()`

#### Small standalone helpers
- `core.translation_handler.update_translation_progress()`
- `models.neologism_models.filter_neologisms_by_confidence()`
- `models.neologism_models.sort_neologisms_by_confidence()`

#### Unused convenience/introspection helpers
- `core.dynamic_programming.get_registered_keys()`
- `core.dynamic_programming.get_registered_types()`
- `core.dynamic_programming.clear_all_registries()`
- `core.dynamic_programming.strategy_count`
- `core.dynamic_programming.add_child()`

**Why this phase is safest:** these removals are narrow, isolated, and least likely to affect active runtime behavior.

---

### [x] Phase 2 — Dead configuration and disconnected config surface
These appear unused in the current app wiring and should be reviewed next.

#### Likely disconnected config surface
- `config.main.Config.validate_config()`
- likely much of `config/main.py` if no broader consumer exists

#### Unused settings members/methods
- `config.settings.HOST`
- `config.settings.CLEANUP_INTERVAL_HOURS`
- `config.settings.MAX_FILE_AGE_HOURS`
- `config.settings.get_available_translators()`
- `config.settings.validate_configuration()`

**Important note:** keep `config.settings.LOG_LEVEL` and `config.settings.LOG_FILE`, since they are still indirectly useful through logging configuration.

---

### [ ] Phase 3 — Unused helper methods on otherwise active classes
These live in production-used modules/classes, so removal risk is slightly higher even though the individual methods appear unused.

#### `services.enhanced_document_processor.py`
- `_generate_text_preview()`
- `convert_format()`
- `generate_preview()`

#### `core.dynamic_language_engine.py`
- `update_confidence_threshold()`
- `_get_language_detector()`

#### `core.dynamic_validation_engine.py`
- `validate_batch()`
- `get_validation_summary()`
- `benchmark_vs_sequential()`
- `get_registered_validators()`
- `register_validation_engine()`
- `get_validation_engine()`

#### `core.state_manager.py`
- `get_job()`
- `update_job()`
- `remove_job()`
- `get_all_jobs()`
- `force_cleanup()`
- `session_state()`
- `get_request_state()`

**Why this is not Phase 1:** these functions are unused, but they live inside classes/modules that are otherwise active, so removal should be done more carefully and ideally with targeted test coverage.

---

### [ ]Phase 4 — Broader abstraction cleanup
These items are likely unused, but they are part of generic infrastructure and may have been added intentionally for future extension.

#### Generic infrastructure
- `core.dynamic_programming.DynamicFactory`

#### Preference surface
- `models.user_choice_models.TranslationPreference`
- `update_language_preference()`
- `update_domain_preference()`
- `get_language_preference()`
- `get_domain_preference()`

#### Export bookkeeping
- `services.__init__.py` exported availability flags and service summary values if you confirm nothing imports them externally

**Why later:** these are not high-risk from a runtime standpoint, but they are higher-risk from an architecture/intent standpoint.

---

### [ ]Phase 5 — Future-facing but currently disconnected APIs
These should only be removed if you explicitly decide they are no longer part of the product direction.

- `services.philosophical_context_analyzer.update_terminology_map()`
- `services.philosophy_enhanced_translation_service.update_configuration()`
- `services.philosophy_enhanced_translation_service.translate_with_philosophy_awareness()`
- `services.neologism_detector.merge_neologism_analyses()`
- `services.pdf_quality_validator.validate_pdf_reconstruction_quality()`
- `services.dolphin_client.DEFAULT_LOCAL_ENDPOINT`
- tuning/inspection methods in `services.confidence_scorer.py`

**Why last:** these read like intentional extension hooks, convenience APIs, deployment flexibility, or tuning surfaces rather than accidental leftovers.

---

## Practical Removal Order

If the goal is maximum safety with steady progress, remove in this order:

1. `api.auth.require_role()`
2. unused helper surfaces in `api.rate_limit.py`
3. `core.translation_handler.update_translation_progress()`
4. unused neologism model helpers
5. low-value dynamic programming introspection helpers
6. dead/disconnected config members and `config/main.py`
7. unused methods on active classes
8. generic extension infrastructure
9. future-facing convenience APIs only after product-direction confirmation

---

## What Not To Remove Yet

Do **not** start by removing these:

- FastAPI route handlers in `api/routes.py`
- memory endpoints in `api/memory_routes.py`
- Gradio-connected functions in `core.translation_handler.py`
- Modal deployment service endpoints/hooks in `services/dolphin_modal_service.py`
- enum members like `USER_PROMPT`, `SUSPENDED`, or `TTL`
- bookkeeping/data fields like `last_duration_ms`, `failed_tasks`, `layout_strategy`, `last_accessed`

These may look unused to static analysis, but they are either reachable, structural, or part of active runtime/deployment behavior.

---

## Suggested Execution Approach

For the actual cleanup work, the safest pattern is:

1. Remove only **Phase 1** items first
2. Run tests and import checks
3. Then remove **Phase 2**
4. Re-run tests
5. Continue phase-by-phase, stopping whenever a removal starts affecting architecture assumptions or examples/scripts you still care about

This phased approach minimizes the chance of deleting code that is inactive today but still part of a near-term feature path.

---

## Final Conclusion

The original report was **too aggressive** in calling code unused.

### What is actually true

- Some code is **genuinely unused today**
- Some code is **future-facing or extension-oriented**
- Some code is **support-only** for tests/examples/scripts
- A meaningful chunk of the originally reported API/UI code is **actively used in production**

### Bottom line

This codebase does **not** consist entirely of dead code in the reported areas.  
There is a mix of:

- **real false positives**
- **future-facing implementation**
- **support/deployment surfaces**
- **actual dead or disconnected helpers**

So the right next step is **selective cleanup**, not wholesale deletion.