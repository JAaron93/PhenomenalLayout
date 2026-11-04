"""Philosophy service default engine is an unbound BYOK stub (ADR 0004, T-2.2).

The philosophy-enhanced service can no longer construct the legacy
``TranslationService`` by default: without an explicitly injected engine it
receives :class:`UnboundTranslationStub`, which serves the statistics/config
surface and fails closed (``GCP_CREDENTIALS_REQUIRED``) on any translation
attempt. Request-path translations wrap a user-bound ``GcpSyncTranslator``
instead (covered by ``tests/test_translate_content_engine_binding.py``).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.gcp_sync_translation_service import GcpSyncCredentialsRequiredError
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
    UnboundTranslationStub,
)


def _light_service() -> PhilosophyEnhancedTranslationService:
    """Return a philosophy service with zero-I/O injected components."""
    return PhilosophyEnhancedTranslationService(
        translation_service=None,
        neologism_detector=MagicMock(),
        user_choice_manager=MagicMock(),
    )


class TestUnboundDefaultEngine:
    """Default construction must not bind any legacy or ambient engine."""

    def test_default_engine_is_unbound_stub(self) -> None:
        """-Generated default engine is the UnboundTranslationStub."""
        svc = _light_service()
        assert isinstance(svc.translation_service, UnboundTranslationStub)

    def test_default_engine_is_not_the_legacy_service(self) -> None:
        """No legacy TranslationService is reachable through the default."""
        svc = _light_service()
        assert (
            type(svc.translation_service).__module__ != "services.translation_service"
        )


class TestUnboundStubFailClosed:
    """Translation calls on the unbound stub fail closed (typed error)."""

    def test_translate_text_raises_typed_error(self) -> None:
        """translate_text without a bound engine raises the credential error."""
        stub = UnboundTranslationStub()

        with pytest.raises(GcpSyncCredentialsRequiredError) as excinfo:
            asyncio.run(stub.translate_text("Der Geist", "de", "en"))

        assert excinfo.value.code == "GCP_CREDENTIALS_REQUIRED"

    def test_translate_batch_raises_typed_error(self) -> None:
        """translate_batch likewise fails closed."""
        stub = UnboundTranslationStub()

        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(stub.translate_batch(["a"], "de", "en"))

    def test_translate_document_raises_typed_error(self) -> None:
        """Content-dict document translation fails closed."""
        stub = UnboundTranslationStub()
        content: dict[str, Any] = {"type": "pdf_advanced", "pages": []}

        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(stub.translate_document(content, "de", "en", "gcp", None))


class TestUnboundStubStatsSurface:
    """Statistics/provider parity for config-only consumers."""

    def test_get_available_providers_reports_gcp(self) -> None:
        """Config surfaces report the GCP provider registry."""
        stub = UnboundTranslationStub()
        assert stub.get_available_providers() == ["gcp"]

    def test_get_statistics_returns_dict(self) -> None:
        """Statistics remain a plain mapping (no engine to aggregate)."""
        stub = UnboundTranslationStub()
        stats: dict[str, Any] = stub.get_statistics()
        assert isinstance(stats, dict)

    def test_philosophy_providers_surface_through_stub(self) -> None:
        """philosophy.get_available_providers yields ['gcp'] with the stub."""
        svc = _light_service()
        assert svc.get_available_providers() == ["gcp"]


# ---------------------------------------------------------------------------
# Review round 2 — end-to-end unbound path guard (finding #1)
# ---------------------------------------------------------------------------


class TestUnboundCredentialFailureEndToEnd:
    """Unbound stub error must reach the caller unpatched (ADR 0004 D3)."""

    @pytest.mark.asyncio
    async def test_unbound_service_fails_closed_end_to_end(self) -> None:
        """Default service (no patching) raises the typed credential error.

        Exercises the real chain end-to-end: UnboundTranslationStub ->
        _translate_with_preservation_async -> outer catch re-raise. Guards
        against any future swallow in the default philosophy service.
        """
        svc = _light_service()
        assert isinstance(svc.translation_service, UnboundTranslationStub)

        with pytest.raises(GcpSyncCredentialsRequiredError):
            await svc.translate_text_with_neologism_handling_async(
                "Der Geist", "de", "en", "gcp", "s-e2e-unbound"
            )


# ---------------------------------------------------------------------------
# Review round 1 — fail-closed propagation through the philosophy fallback
# ---------------------------------------------------------------------------


class TestCredentialErrorPropagatesThroughFallback:
    """The philosophy text fallback must not swallow credential errors."""

    @pytest.mark.asyncio
    async def test_credential_error_not_swallowed_by_source_text_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A GcpSyncCredentialsRequiredError must re-raise, never mask to text.

        Regression guard for the review finding that the default philosophy
        service's broad ``except`` turned unusable credentials into silent
        source-text "translations" (ADR 0004 D3 fail-closed).
        """
        svc = _light_service()

        async def _raise_credential_error(*_args: Any, **_kwargs: Any) -> str:
            """Simulate the engine reporting unusable credentials."""
            raise GcpSyncCredentialsRequiredError("<unbound>")

        monkeypatch.setattr(
            svc, "_translate_with_preservation_async", _raise_credential_error
        )

        with pytest.raises(GcpSyncCredentialsRequiredError):
            await svc.translate_text_with_neologism_handling_async(
                "Der Geist", "de", "en", "gcp", "s-fallback"
            )
