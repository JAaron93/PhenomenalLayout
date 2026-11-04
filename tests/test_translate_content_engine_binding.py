"""Handler rewiring tests: user-bound engine resolution (ADR 0004 Track B).

``core.translation_handler`` must:

1. Resolve credential-bound engines strictly through the shared BYOK vault —
   no ambient/userless translation calls (fail closed when unbound).
2. Keep the module-level patch points working: ``th.philosophy_translation_service``
   (used by legacy handler tests) and ``th.translation_service`` (statistics
   facade).
3. Thread the engine bound at submission through ``process_advanced_translation_job``
   into ``translate_content`` (job closure never re-resolves identity).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

import core.translation_handler as th
from services.gcp_sync_translation_service import GcpSyncCredentialsRequiredError

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubEngine:
    """User-bound engine stub speaking the GcpSyncTranslator surface."""

    def __init__(self, user_id: str, *, fail: type[Exception] | None = None) -> None:
        """Configure echo behavior and optional failure injection."""
        self.user_id = user_id
        self.batch_calls: list[tuple[list[str], str, str]] = []
        self._fail = fail

    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """Echo with a marker (or raise the configured failure)."""
        if self._fail is not None:
            raise self._fail(f"engine failure for {self.user_id}")
        self.batch_calls.append((list(texts), source_lang, target_lang))
        return [f"T:{t}" for t in texts]


class _StubPhilosophy:
    """Philosophy wrapper stub speaking the legacy philosophy surface."""

    def __init__(self, engine: _StubEngine) -> None:
        """Remember the bound engine (asserted by tests)."""
        self.engine = engine

    async def translate_text_with_neologism_handling_async(
        self, *, text: str, **_kwargs: Any
    ) -> dict[str, str]:
        """Echo with a marker and expose the bound engine identity."""
        return {"translated_text": f"P:{text}", "bound_user": self.engine.user_id}


def _content() -> dict[str, Any]:
    """Return a minimal pdf_advanced content dict."""
    return {
        "type": "pdf_advanced",
        "text_by_page": {"0": ["Hallo", ""]},
    }


# ---------------------------------------------------------------------------
# Fail-closed engine resolution + binding
# ---------------------------------------------------------------------------


class TestEngineBinding:
    """translate_content resolves credential-bound engines (no ambient)."""

    def test_non_philosophy_requires_bound_engine(self) -> None:
        """Neither user nor engine → typed fail-closed error (ADR 0004 D3)."""
        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(
                th.translate_content(
                    content=_content(),
                    source_language="de",
                    target_language="en",
                    philosophy_mode=False,
                    session_id=None,
                )
            )

    def test_non_philosophy_uses_injected_engine(self) -> None:
        """translate_content calls the bound engine's translate_batch."""
        engine = _StubEngine("engine-user")

        translated, _ = asyncio.run(
            th.translate_content(
                content=_content(),
                source_language="de",
                target_language="en",
                philosophy_mode=False,
                session_id=None,
                translator=engine,
            )
        )

        assert engine.batch_calls
        texts, source, target = engine.batch_calls[0]
        assert texts == ["Hallo"]
        assert (source, target) == ("de", "en")
        assert translated == {"0": ["T:Hallo", ""]}

    def test_non_philosophy_resolves_engine_for_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """user_id alone resolves the engine through the module facade."""
        engine = _StubEngine("resolve-user")

        monkeypatch.setattr(
            th.translation_service,
            "translator_for_user",
            lambda _bound_user, **_engine_kw: engine,
            raising=True,
        )

        translated, _ = asyncio.run(
            th.translate_content(
                content=_content(),
                source_language="de",
                target_language="en",
                philosophy_mode=False,
                session_id=None,
                user_id="resolve-user",
            )
        )

        assert translated == {"0": ["T:Hallo", ""]}
        assert engine.user_id == "resolve-user"

    def test_non_philosophy_credential_error_not_swallowed_by_fallback(self) -> None:
        """Engine credential failures must propagate, never silently fallback."""
        engine = _StubEngine("vault-user", fail=GcpSyncCredentialsRequiredError)

        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(
                th.translate_content(
                    content=_content(),
                    source_language="de",
                    target_language="en",
                    philosophy_mode=False,
                    session_id=None,
                    translator=engine,
                )
            )

    def test_non_philosophy_transient_engine_error_falls_back(self) -> None:
        """Legacy resilience: non-credential errors fall back to source text."""
        engine = _StubEngine("vault-user", fail=RuntimeError)

        translated, _ = asyncio.run(
            th.translate_content(
                content=_content(),
                source_language="de",
                target_language="en",
                philosophy_mode=False,
                session_id=None,
                translator=engine,
            )
        )

        assert translated == {"0": ["Hallo", ""]}

    def test_philosophy_mode_credential_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review round 1: philosophy mode must fail closed like batch mode.

        The request-bound philosophy wrapper (as ``build_philosophy_service``
        produces for an engine that rejects credentials) raises the typed
        credential error; the per-item broad catch in
        ``_translate_page_texts_concurrently`` must re-raise it instead of
        planting the source text (ADR 0004 D3).
        """

        class _CredFailPhilosophy:
            """Request-scoped wrapper whose engine reports unusable creds."""

            async def translate_text_with_neologism_handling_async(
                self, **_kwargs: Any
            ) -> dict[str, str]:
                """Simulate the user-bound engine's typed failure."""
                raise GcpSyncCredentialsRequiredError("<engine>")

        monkeypatch.setattr(
            th,
            "PhilosophyEnhancedTranslationService",
            lambda **_kwargs: _CredFailPhilosophy(),
        )

        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(
                th.translate_content(
                    content={
                        "type": "pdf_advanced",
                        "text_by_page": {"0": ["Hallo"]},
                    },
                    source_language="de",
                    target_language="en",
                    philosophy_mode=True,
                    session_id="s-cred",
                    translator=object(),  # any bound engine; wrapper raises
                )
            )

    def test_philosophy_mode_binds_user_engine_into_request_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Philosophy mode wraps the resolved engine in a request-scoped service."""
        engine = _StubEngine("philosophy-user")
        built: list[object | None] = []

        monkeypatch.setattr(
            th.translation_service,
            "translator_for_user",
            lambda _bound_user, **_engine_kw: engine,
            raising=True,
        )

        real_service_cls = th.PhilosophyEnhancedTranslationService

        def _recorder(**kwargs: Any) -> _StubPhilosophy:
            """Record constructor injection then return a stub."""
            built.append(kwargs.get("translation_service"))
            return _StubPhilosophy(engine)

        monkeypatch.setattr(th, "PhilosophyEnhancedTranslationService", _recorder)
        monkeypatch.setattr(
            th, "philosophy_translation_service", _StubPhilosophy(engine), raising=True
        )

        translated, _ = asyncio.run(
            th.translate_content(
                content=_content(),
                source_language="de",
                target_language="en",
                philosophy_mode=True,
                session_id="s-bind",
                user_id="philosophy-user",
            )
        )

        assert built and built[0] is engine
        assert translated == {"0": ["P:Hallo", ""]}
        _ = real_service_cls  # silence unused warning; kept for doc context

    def test_philosophy_mode_without_user_uses_module_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legacy patch point: module singleton serves philosophy without user."""
        stub = _StubPhilosophy(_StubEngine("module-user"))
        monkeypatch.setattr(th, "philosophy_translation_service", stub, raising=True)

        translated, _ = asyncio.run(
            th.translate_content(
                content=_content(),
                source_language="de",
                target_language="en",
                philosophy_mode=True,
                session_id="s-idle",
            )
        )

        assert translated == {"0": ["P:Hallo", ""]}


# ---------------------------------------------------------------------------
# Background job threading
# ---------------------------------------------------------------------------


class TestAdvancedJobEngineThreading:
    """process_advanced_translation_job uses the engine bound at submission."""

    def test_job_uses_bound_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Job completes through the injected engine (closure identity intact)."""
        engine = _StubEngine("job-user")
        job_id = str(uuid.uuid4())
        th.translation_jobs[job_id] = {
            "status": "started",
            "progress": 0,
            "file_path": "doc.pdf",
            "source_language": "de",
            "target_language": "en",
            "user_id": "job-user",
        }
        content: dict[str, Any] = _content()
        content["file_path"] = "doc.pdf"

        async def _fake_extract(_file_path: str) -> dict[str, Any]:
            """Return canned content; no filesystem involved."""
            return content

        monkeypatch.setattr(th.document_processor, "extract_content", _fake_extract)
        monkeypatch.setattr(
            th.document_processor,
            "create_translated_document",
            lambda *_args, **_kw: "translated_stub.pdf",
        )

        asyncio.run(
            th.process_advanced_translation_job(
                job_id, "doc.pdf", "de", "en", translator=engine
            )
        )

        job = th.translation_jobs[job_id]
        assert job["status"] == "completed"
        assert engine.batch_calls

    def test_job_records_credential_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail-closed errors surface in the job record (never silent success)."""
        engine = _StubEngine("job-user", fail=GcpSyncCredentialsRequiredError)
        job_id = str(uuid.uuid4())
        th.translation_jobs[job_id] = {
            "status": "started",
            "progress": 0,
            "file_path": "doc.pdf",
            "source_language": "de",
            "target_language": "en",
            "user_id": "job-user",
        }

        async def _fake_extract(_file_path: str) -> dict[str, Any]:
            """Return canned content; no filesystem involved."""
            return _content()

        monkeypatch.setattr(th.document_processor, "extract_content", _fake_extract)

        asyncio.run(
            th.process_advanced_translation_job(
                job_id, "doc.pdf", "de", "en", translator=engine
            )
        )

        job = th.translation_jobs[job_id]
        assert job["status"] == "failed"
        assert "GCP_CREDENTIALS_REQUIRED" in job["error"]


class TestSiblingTaskCleanupOnCredentialFailure:
    """First-failure cleanup must cancel sibling page tasks (round 2, #2)."""

    def test_credential_failure_cancels_sibling_pages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Credential error cancels tasks queued on the semaphore.

        ``asyncio.gather`` abandons its remaining children on first
        failure: with the concurrency limit at 1, the sibling page is
        parked waiting for the semaphore and would start detection and
        translation work (up to 30s of wasted GCP-bound effort) after
        the caller has already failed. The cleanup must cancel and
        drain it.
        """
        engine = _StubEngine("scale-user")  # unused; service is faked below

        class _FailThenSlowService:
            """Call 1 raises credential failure; later calls sleep long."""

            def __init__(self) -> None:
                self.calls = 0

            async def translate_text_with_neologism_handling_async(
                self, **_kwargs: Any
            ) -> dict[str, str]:
                self.calls += 1
                if self.calls == 1:
                    raise GcpSyncCredentialsRequiredError("<engine>")
                await asyncio.sleep(30)
                return {"translated_text": worker_text}  # pragma: no cover

        worker_text = "Warten auf Semaphore"
        fake = _FailThenSlowService()
        _ = engine  # presence documents the philosophy resolution shape
        monkeypatch.setattr(
            th.settings, "TRANSLATION_CONCURRENCY_LIMIT", 1, raising=True
        )

        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(GcpSyncCredentialsRequiredError):
                loop.run_until_complete(
                    th._translate_page_texts_concurrently(
                        page_texts={"0": ["Der Geist"], "1": [worker_text]},
                        source_language="de",
                        target_language="en",
                        session_id="s-scale",
                        service=fake,
                    )
                )
            leftover = [t for t in asyncio.all_tasks(loop) if not t.done()]
            assert not leftover, (
                f"{len(leftover)} sibling task(s) abandoned after credential "
                "failure; cleanup must cancel and drain them"
            )
        finally:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    def test_job_persists_progress_during_translation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review round 1: progress callback writes must reach the store.

        ``translate_batch`` probes the live job record: with the persisting
        callback, progress is > 0 while the job is still translating — and
        the final record shows completion.
        """
        seen: list[int] = []
        job_id = str(uuid.uuid4())
        engine = _StubEngine("job-user")
        original_translate_batch = engine.translate_batch

        async def _probe_and_translate(
            texts: list[str], source_lang: str, target_lang: str
        ) -> list[str]:
            """Record the persisted progress at invocation time."""
            seen.append(th.translation_jobs[job_id]["progress"])
            return await original_translate_batch(texts, source_lang, target_lang)

        engine.translate_batch = _probe_and_translate  # type: ignore[method-assign]
        th.translation_jobs[job_id] = {
            "status": "started",
            "progress": 0,
            "file_path": "doc.pdf",
            "source_language": "de",
            "target_language": "en",
            "user_id": "job-user",
        }
        content: dict[str, Any] = _content()
        content["file_path"] = "doc.pdf"

        async def _fake_extract(_file_path: str) -> dict[str, Any]:
            """Return canned content; no filesystem involved."""
            return content

        monkeypatch.setattr(th.document_processor, "extract_content", _fake_extract)
        monkeypatch.setattr(
            th.document_processor,
            "create_translated_document",
            lambda *_args, **_kw: "translated_stub.pdf",
        )

        asyncio.run(
            th.process_advanced_translation_job(
                job_id, "doc.pdf", "de", "en", translator=engine
            )
        )

        assert seen, "engine must have been called"
        assert (
            max(seen) >= 20
        ), "progress runs >= 20 while translating (scale callback persists)"
        final_job = th.translation_jobs[job_id]
        assert final_job["status"] == "completed"
        assert final_job["progress"] == 100


# ---------------------------------------------------------------------------
# Shared BYOK vault invariant (no second manager)
# ---------------------------------------------------------------------------


class TestSharedVault:
    """The handler facade must borrow the SAME manager as api.routes."""

    def test_facade_shares_routes_manager(self) -> None:
        """Facade's credentials_manager is api.routes' singleton manager."""
        from api.routes import get_byok_credentials_manager

        # Reload-aware force-fresh materialization: conftest's module-scoped
        # test_client fixture reloads api.routes and resets its singleton
        # manager; a facade cached from an earlier test phase may reference a
        # pre-reload manager without any product defect. Rebuild through the
        # documented seam and restore cache state afterwards (AGENTS §6.2).
        th._translation_facade = None
        vars(th).pop("translation_service", None)
        try:
            facade = th.get_translation_facade()
            assert facade._credentials_manager is get_byok_credentials_manager()
        finally:
            th._translation_facade = None
            vars(th).pop("translation_service", None)
