ARG001 Unused function argument: `request`
   --> api/auth.py:255:5
    |
254 | async def get_current_user(
255 |     request: Request,
    |     ^^^^^^^
256 |     api_key: str | None = None,
257 |     credentials: HTTPAuthorizationCredentials | None = None
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes.py:162:5
    |
160 |     request: Request,
161 |     response: Response,
162 |     current_user: dict = Depends(get_admin_user)
    |     ^^^^^^^^^^^^
163 | ) -> dict[str, Any]:
164 |     """Force garbage collection and return results."""
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes.py:196:5
    |
194 |     request: Request,
195 |     response: Response,
196 |     current_user: dict = Depends(get_admin_user),
    |     ^^^^^^^^^^^^
197 |     check_interval: float = 60.0,
198 |     alert_threshold_mb: float = 100.0
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes.py:235:5
    |
233 |     request: Request,
234 |     response: Response,
235 |     current_user: dict = Depends(get_admin_user)
    |     ^^^^^^^^^^^^
236 | ) -> dict[str, Any]:
237 |     """Stop memory monitoring."""
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes_backup.py:195:5
    |
193 |     request: Request,
194 |     response: Response,
195 |     current_user: dict = Depends(get_admin_user)
    |     ^^^^^^^^^^^^
196 | ) -> dict[str, Any]:
197 |     """Force garbage collection and return results."""
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes_backup.py:234:5
    |
232 |     request: Request,
233 |     response: Response,
234 |     current_user: dict = Depends(get_admin_user),
    |     ^^^^^^^^^^^^
235 |     check_interval: float = Query(
236 |         60.0,
    |

ARG001 Unused function argument: `current_user`
   --> api/memory_routes_backup.py:285:5
    |
283 |     request: Request,
284 |     response: Response,
285 |     current_user: dict = Depends(get_admin_user)
    |     ^^^^^^^^^^^^
286 | ) -> dict[str, Any]:
287 |     """Stop memory monitoring."""
    |

ARG001 Unused function argument: `args`
   --> core/dynamic_choice_engine.py:312:26
    |
310 |         """Handle arbitrary method calls safely."""
311 |
312 |         def stub_method(*args, **kwargs):
    |                          ^^^^
313 |             logging.warning(
314 |                 f"UserChoiceManager method '{name}' called on stub. "
    |

ARG001 Unused function argument: `kwargs`
   --> core/dynamic_choice_engine.py:312:34
    |
310 |         """Handle arbitrary method calls safely."""
311 |
312 |         def stub_method(*args, **kwargs):
    |                                  ^^^^^^
313 |             logging.warning(
314 |                 f"UserChoiceManager method '{name}' called on stub. "
    |

F841 Local variable `priority` is assigned to but never used
   --> core/dynamic_layout_engine.py:319:9
    |
318 |         # Register strategies in priority order
319 |         priority = 100
    |         ^^^^^^^^
320 |         for conditions in itertools.product([True, False], repeat=4):
321 |             can_fit, can_scale, can_wrap, sufficient_lines = conditions
    |
help: Remove assignment to unused variable `priority`

ARG002 Unused method argument: `kwargs`
   --> core/dynamic_layout_engine.py:513:34
    |
511 |         )
512 |
513 |     def analyze_text_fit(self, **kwargs):
    |                                  ^^^^^^
514 |         """Stub method that raises clear error when used."""
515 |         raise RuntimeError(
    |

ARG002 Unused method argument: `analysis`
   --> core/dynamic_layout_engine.py:521:39
    |
519 |         )
520 |
521 |     def calculate_quality_score(self, analysis, decision):
    |                                       ^^^^^^^^
522 |         """Stub method that raises clear error when used."""
523 |         raise RuntimeError(
    |

ARG002 Unused method argument: `decision`
   --> core/dynamic_layout_engine.py:521:49
    |
519 |         )
520 |
521 |     def calculate_quality_score(self, analysis, decision):
    |                                                 ^^^^^^^^
522 |         """Stub method that raises clear error when used."""
523 |         raise RuntimeError(
    |

ARG002 Unused method argument: `kwargs`
   --> core/dynamic_layout_engine.py:529:42
    |
527 |         )
528 |
529 |     def apply_layout_adjustments(self, **kwargs):
    |                                          ^^^^^^
530 |         """Stub method that raises clear error when used."""
531 |         raise RuntimeError(
    |

ARG002 Unused method argument: `operation`
   --> core/dynamic_middleware.py:150:15
    |
149 |     def _calculate_improvement(
150 |         self, operation: str, metrics: MiddlewareMetrics
    |               ^^^^^^^^^
151 |     ) -> float:
152 |         """Calculate estimated performance improvement."""
    |

ARG001 Unused function argument: `cache_name`
   --> core/dynamic_middleware.py:360:5
    |
358 | def performance_tracking(
359 |     operation_name: str | None = None,
360 |     cache_name: str | None = None,
    |     ^^^^^^^^^^
361 |     monitor: DynamicProgrammingMonitor | None = None,
362 | ) -> Callable[[F], F]:
    |

F841 Local variable `current_time` is assigned to but never used
   --> core/dynamic_validation_engine.py:608:9
    |
606 |     ) -> bool:
607 |         """Check if cached results are still fresh based on TTL."""
608 |         current_time = time.time()
    |         ^^^^^^^^^^^^
609 |
610 |         for outcome in cached_results.values():
    |
help: Remove assignment to unused variable `current_time`

F841 Local variable `detectors` is assigned to but never used
   --> examples/lazy_loading_performance_example.py:226:5
    |
225 |     start_time = time.time()
226 |     detectors: list[NeologismDetector] = [NeologismDetector() for _ in range(10)]
    |     ^^^^^^^^^
227 |
228 |     multi_init_time: float = time.time() - start_time
    |
help: Remove assignment to unused variable `detectors`

ARG002 Unused method argument: `target_lang`
   --> examples/neologism_integration_example.py:279:45
    |
278 |     def _generate_contextual_suggestions(
279 |         self, neologism: DetectedNeologism, target_lang: str
    |                                             ^^^^^^^^^^^
280 |     ) -> list[str]:
281 |         """Generate contextual translation suggestions."""
    |

ARG001 Unused function argument: `args`
  --> services/mcp_lingo_client.py:18:23
   |
16 |     StdioServerParameters = object  # type: ignore
17 |
18 |     def stdio_client(*args, **kwargs):  # type: ignore
   |                       ^^^^
19 |         raise RuntimeError("mcp package is not installed")
   |

ARG001 Unused function argument: `kwargs`
  --> services/mcp_lingo_client.py:18:31
   |
16 |     StdioServerParameters = object  # type: ignore
17 |
18 |     def stdio_client(*args, **kwargs):  # type: ignore
   |                               ^^^^^^
19 |         raise RuntimeError("mcp package is not installed")
   |

F841 Local variable `last_err` is assigned to but never used
   --> services/mcp_lingo_client.py:286:17
    |
284 |                 return self._extract_text(result, fallback=text)
285 |             except Exception as e:
286 |                 last_err = e
    |                 ^^^^^^^^
287 |                 if attempt < 2:
288 |                     await asyncio.sleep(0.5 * (attempt + 1))
    |
help: Remove assignment to unused variable `last_err`

ARG002 Unused method argument: `term`
   --> services/neologism_detector.py:934:40
    |
932 |         return self.philosophical_context_analyzer.extract_philosophical_keywords(text)
933 |
934 |     def _identify_semantic_field(self, term: str, context: str) -> str:
    |                                        ^^^^
935 |         """Identify semantic field of a term."""
936 |         return self.philosophical_context_analyzer._identify_semantic_field(context)
    |

ARG002 Unused method argument: `philosophy_mode`
   --> services/philosophy_enhanced_document_processor.py:245:9
    |
243 |         user_id: str | None = None,
244 |         session_id: str | None = None,
245 |         philosophy_mode: bool = True,
    |         ^^^^^^^^^^^^^^^
246 |         progress_callback: Callable[[PhilosophyProcessingProgress], None] | None = None,
247 |     ) -> PhilosophyDocumentResult:
    |

ARG002 Unused method argument: `progress`
   --> services/philosophy_enhanced_translation_service.py:792:9
    |
790 |         translated_text: str,
791 |         preservation_data: PreservationData,
792 |         progress: PhilosophyTranslationProgress,
    |         ^^^^^^^^
793 |         progress_callback: Callable[[PhilosophyTranslationProgress], None]
794 |         | None = None,
    |

ARG002 Unused method argument: `progress_callback`
   --> services/philosophy_enhanced_translation_service.py:793:9
    |
791 |         preservation_data: PreservationData,
792 |         progress: PhilosophyTranslationProgress,
793 |         progress_callback: Callable[[PhilosophyTranslationProgress], None]
    |         ^^^^^^^^^^^^^^^^^
794 |         | None = None,
795 |     ) -> str:
    |

ARG002 Unused method argument: `session_id`
   --> services/user_choice_manager.py:224:45
    |
223 |     def get_choice_for_neologism(
224 |         self, neologism: DetectedNeologism, session_id: str | None = None
    |                                             ^^^^^^^^^^
225 |     ) -> UserChoice | None:
226 |         """Get the best matching choice for a detected neologism.
    |

ARG001 Unused function argument: `test_client`
  --> tests/conftest.py:95:16
   |
94 | @pytest.fixture
95 | def read_token(test_client):
   |                ^^^^^^^^^^^
96 |     """Pytest fixture providing a read-only token."""
97 |     import api.auth
   |

ARG001 Unused function argument: `test_client`
   --> tests/conftest.py:102:17
    |
101 | @pytest.fixture
102 | def admin_token(test_client):
    |                 ^^^^^^^^^^^
103 |     """Pytest fixture providing an admin token."""
104 |     import api.auth
    |

ARG001 Unused function argument: `caplog`
  --> tests/services/test_mcp_lingo_client.py:93:63
   |
92 | @pytest.mark.asyncio
93 | async def test_both_text_and_texts_prefers_batch(make_client, caplog):
   |                                                               ^^^^^^
94 |     client = make_client(
95 |         succeed_on_call=2
   |

ARG002 Unused method argument: `pdf_path`
  --> tests/test_async_document_processor.py:29:15
   |
28 |     def convert(
29 |         self, pdf_path: str, dpi: int, fmt: str, poppler: str | None
   |               ^^^^^^^^
30 |     ) -> list[bytes]:
31 |         return [b"img"] * self.pages
   |

ARG002 Unused method argument: `dpi`
  --> tests/test_async_document_processor.py:29:30
   |
28 |     def convert(
29 |         self, pdf_path: str, dpi: int, fmt: str, poppler: str | None
   |                              ^^^
30 |     ) -> list[bytes]:
31 |         return [b"img"] * self.pages
   |

ARG002 Unused method argument: `fmt`
  --> tests/test_async_document_processor.py:29:40
   |
28 |     def convert(
29 |         self, pdf_path: str, dpi: int, fmt: str, poppler: str | None
   |                                        ^^^
30 |     ) -> list[bytes]:
31 |         return [b"img"] * self.pages
   |

ARG002 Unused method argument: `poppler`
  --> tests/test_async_document_processor.py:29:50
   |
28 |     def convert(
29 |         self, pdf_path: str, dpi: int, fmt: str, poppler: str | None
   |                                                  ^^^^^^^
30 |     ) -> list[bytes]:
31 |         return [b"img"] * self.pages
   |

ARG002 Unused method argument: `fmt`
  --> tests/test_async_document_processor.py:33:36
   |
31 |         return [b"img"] * self.pages
32 |
33 |     def optimize(self, img: bytes, fmt: str) -> bytes:
   |                                    ^^^
34 |         return img
   |

ARG002 Unused method argument: `source_lang`
  --> tests/test_async_document_processor.py:69:48
   |
68 |     def translate_document_batch(
69 |         self, *, text_blocks: list[TextBlock], source_lang: str, target_lang: str
   |                                                ^^^^^^^^^^^
70 |     ) -> list[TranslationResult]:
71 |         self.calls.append(len(text_blocks))
   |

ARG002 Unused method argument: `target_lang`
  --> tests/test_async_document_processor.py:69:66
   |
68 |     def translate_document_batch(
69 |         self, *, text_blocks: list[TextBlock], source_lang: str, target_lang: str
   |                                                                  ^^^^^^^^^^^
70 |     ) -> list[TranslationResult]:
71 |         self.calls.append(len(text_blocks))
   |

ARG002 Unused method argument: `translated_layout`
  --> tests/test_async_document_processor.py:94:18
   |
92 | class DummyReconstructor:
93 |     def reconstruct_pdf_document(
94 |         self, *, translated_layout, original_file_path: str, output_path: str
   |                  ^^^^^^^^^^^^^^^^^
95 |     ) -> None:
96 |         return None
   |

ARG002 Unused method argument: `original_file_path`
  --> tests/test_async_document_processor.py:94:37
   |
92 | class DummyReconstructor:
93 |     def reconstruct_pdf_document(
94 |         self, *, translated_layout, original_file_path: str, output_path: str
   |                                     ^^^^^^^^^^^^^^^^^^
95 |     ) -> None:
96 |         return None
   |

ARG002 Unused method argument: `output_path`
  --> tests/test_async_document_processor.py:94:62
   |
92 | class DummyReconstructor:
93 |     def reconstruct_pdf_document(
94 |         self, *, translated_layout, original_file_path: str, output_path: str
   |                                                              ^^^^^^^^^^^
95 |     ) -> None:
96 |         return None
   |

ARG001 Unused function argument: `self`
   --> tests/test_async_document_processor.py:158:28
    |
156 |     calls = {"count": 0}
157 |
158 |     async def fake_acquire(self) -> None:  # type: ignore[override]
    |                            ^^^^
159 |         calls["count"] += 1
160 |         await asyncio.sleep(0)
    |

ARG001 Unused function argument: `auth_env`
  --> tests/test_auth_optional_dependency.py:24:53
   |
23 | @pytest.mark.asyncio
24 | async def test_get_current_user_optional_dependency(auth_env):
   |                                                     ^^^^^^^^
25 |     """Test the optional dependency function directly."""
26 |     # Import after environment is set
   |

ARG001 Unused function argument: `auth_env`
  --> tests/test_auth_optional_dependency.py:49:49
   |
49 | def test_optional_dependency_via_fastapi_client(auth_env):
   |                                                 ^^^^^^^^
50 |     """Test optional dependency through FastAPI client."""
51 |     # Import after environment is set
   |

ARG001 Unused function argument: `auth_env`
  --> tests/test_auth_optional_dependency.py:75:39
   |
75 | def test_optional_dependency_no_token(auth_env):
   |                                       ^^^^^^^^
76 |     """Test optional dependency with no authentication token."""
77 |     from app import create_app
   |

ARG001 Unused function argument: `auth_env`
  --> tests/test_auth_optional_dependency.py:91:50
   |
90 | @pytest.mark.asyncio
91 | async def test_optional_dependency_invalid_token(auth_env):
   |                                                  ^^^^^^^^
92 |     """Test optional dependency with invalid authentication token."""
93 |     from api.auth import get_current_user_optional_dependency
   |

F841 Local variable `original_session` is assigned to but never used
   --> tests/test_memory_leaks.py:189:9
    |
187 |         # Verify session exists
188 |         assert lingo_translator.session is not None
189 |         original_session = lingo_translator.session
    |         ^^^^^^^^^^^^^^^^
190 |
191 |         # Close the translator
    |
help: Remove assignment to unused variable `original_session`

F841 Local variable `m` is assigned to but never used
   --> tests/test_memory_leaks.py:202:48
    |
200 |         """Test translation service cleanup logging."""
201 |         # Mock logger to capture log messages
202 |         with pytest.MonkeyPatch().context() as m:
    |                                                ^
203 |             log_messages = []
    |
help: Remove assignment to unused variable `m`

F841 Local variable `m` is assigned to but never used
   --> tests/test_memory_leaks.py:233:48
    |
231 |     async def test_translation_service_async_cleanup_logging(self, translation_service):
232 |         """Test translation service async cleanup logging."""
233 |         with pytest.MonkeyPatch().context() as m:
    |                                                ^
234 |             log_messages = []
    |
help: Remove assignment to unused variable `m`

F841 Local variable `initial_counts` is assigned to but never used
   --> tests/test_memory_leaks.py:436:9
    |
434 |         """Test garbage collection effectiveness."""
435 |         # Create objects and measure before/after GC
436 |         initial_counts = gc.get_count() if hasattr(gc, 'get_count') else (0, 0, 0)
    |         ^^^^^^^^^^^^^^
437 |
438 |         # Create some cyclic references
    |
help: Remove assignment to unused variable `initial_counts`

ARG001 Unused function argument: `source_lang`
   --> tests/test_translate_content_philosophy_async.py:226:27
    |
225 |     async def _fake_batch(
226 |         texts: list[str], source_lang: str, target_lang: str
    |                           ^^^^^^^^^^^
227 |     ) -> list[str]:
228 |         # record what we actually receive
    |

ARG001 Unused function argument: `target_lang`
   --> tests/test_translate_content_philosophy_async.py:226:45
    |
225 |     async def _fake_batch(
226 |         texts: list[str], source_lang: str, target_lang: str
    |                                             ^^^^^^^^^^^
227 |     ) -> list[str]:
228 |         # record what we actually receive
    |

ARG002 Unused method argument: `source_lang`
  --> tests/test_translate_one_safety.py:23:9
   |
21 |         *,
22 |         text: str,
23 |         source_lang: str,
   |         ^^^^^^^^^^^
24 |         target_lang: str,
25 |         provider: str,
   |

ARG002 Unused method argument: `target_lang`
  --> tests/test_translate_one_safety.py:24:9
   |
22 |         text: str,
23 |         source_lang: str,
24 |         target_lang: str,
   |         ^^^^^^^^^^^
25 |         provider: str,
26 |         session_id: str,
   |

ARG002 Unused method argument: `provider`
  --> tests/test_translate_one_safety.py:25:9
   |
23 |         source_lang: str,
24 |         target_lang: str,
25 |         provider: str,
   |         ^^^^^^^^
26 |         session_id: str,
27 |     ) -> dict[str, str]:
   |

ARG002 Unused method argument: `session_id`
  --> tests/test_translate_one_safety.py:26:9
   |
24 |         target_lang: str,
25 |         provider: str,
26 |         session_id: str,
   |         ^^^^^^^^^^
27 |     ) -> dict[str, str]:
28 |         action = self.behavior.get(text)
   |

ARG001 Unused function argument: `args`
  --> tests/test_translation_service.py:26:24
   |
25 |     # Minimal callable placeholder
26 |     def _stdio_client(*args, **kwargs):
   |                        ^^^^
27 |         return None
   |

ARG001 Unused function argument: `kwargs`
  --> tests/test_translation_service.py:26:32
   |
25 |     # Minimal callable placeholder
26 |     def _stdio_client(*args, **kwargs):
   |                                ^^^^^^
27 |         return None
   |

Found 57 errors.
No fixes available (8 hidden fixes can be enabled with the `--unsafe-fixes` option).
