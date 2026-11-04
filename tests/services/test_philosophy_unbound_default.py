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
