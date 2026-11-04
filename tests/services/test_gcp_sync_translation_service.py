"""Unit tests for the GCP synchronous translation engine (ADR 0004, Track A).

Covers the engine contract (T-1.1) and fail-closed / resilience / terminology
behaviors (T-1.2). All GCP interaction is simulated with an in-memory fake
credentials manager and a fake ``translate_v3`` client — tests require no real
Google Cloud access and assert the BYOK-only posture: the engine must never
hold or read host credentials.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core import exceptions as gcp_exceptions

from services.byok_credentials_manager import CredentialNotFoundError
from services.gcp_sync_translation_service import (
    GCP_SYNC_REGION,
    STATS_KEYS,
    GcpSyncCredentialsRequiredError,
    GcpSyncTranslationService,
    GcpSyncTranslator,
)

# ---------------------------------------------------------------------------
# Fakes: translate_v3 client + BYOK credentials manager (no real GCP access)
# ---------------------------------------------------------------------------


class _FakeTranslateClient:
    """Minimal stand-in for ``translate_v3.TranslationServiceClient``."""

    def __init__(
        self,
        *,
        echo_prefix: str = "EN:",
        transform: Callable[[str], str] | None = None,
        fail_times: int = 0,
        error_factory: Callable[[], Exception] | None = None,
    ) -> None:
        """Configure echo behavior, failure injection, and error type."""
        self.echo_prefix = echo_prefix
        self.transform = transform
        self.fail_times = fail_times
        self.error_factory = error_factory or (
            lambda: gcp_exceptions.ResourceExhausted(
                "RESOURCE_EXHAUSTED (429): quota exceeded"
            )
        )
        self.closed = False
        self.failure_count = 0
        self.text_requests: list[Any] = []
        self.doc_requests: list[Any] = []

    def _maybe_fail(self) -> None:
        """Raise the injected error while the failure budget allows."""
        if self.failure_count < self.fail_times:
            self.failure_count += 1
            raise self.error_factory()

    def translate_text(self, request: Any) -> SimpleNamespace:
        """Echo each content string, honoring the failure budget."""
        self._maybe_fail()
        self.text_requests.append(request)
        contents = list(request.contents)
        translations = [
            SimpleNamespace(
                translated_text=(
                    f"{self.echo_prefix}{c}"
                    if self.transform is None
                    else self.transform(c)
                )
            )
            for c in contents
        ]
        return SimpleNamespace(translations=translations)

    def translate_document(self, request: Any) -> SimpleNamespace:
        """Echo the document bytes back, honoring the failure budget."""
        self._maybe_fail()
        self.doc_requests.append(request)
        data = request.document_input_config.content
        if not isinstance(data, bytes):
            data = bytes(data)
        out = b"TRANSLATED[" + data + b"]"
        return SimpleNamespace(
            document_translation=SimpleNamespace(byte_stream_outputs=[out])
        )

    def close(self) -> None:
        """Mark the gRPC client closed (BYOK client contract)."""
        self.closed = True


class _FakeCredentialsManager:
    """In-memory BYOK manager stub vending fake translation clients."""

    def __init__(self) -> None:
        """Start empty (no credentialed users)."""
        self.credentialed_users: set[str] = set()
        self.clients: list[_FakeTranslateClient] = []
        self.pending_clients: list[_FakeTranslateClient] = []
        self.client_requests: list[str] = []
        self.raise_on_client = False

    def grant(self, user_id: str) -> None:
        """Store credentials for *user_id*."""
        self.credentialed_users.add(user_id)

    def has_credentials(self, user_id: str) -> bool:
        """Return whether *user_id* has stored credentials."""
        return user_id in self.credentialed_users

    def get_translation_client(self, user_id: str) -> _FakeTranslateClient:
        """Vend a fresh fake client (mirrors fresh-per-call BYOK contract)."""
        self.client_requests.append(user_id)
        if self.raise_on_client or user_id not in self.credentialed_users:
            raise CredentialNotFoundError(
                f"no credentials stored for user_id={user_id}"
            )
        if self.pending_clients:
            client = self.pending_clients.pop(0)
            self.clients.append(client)
            return client
        client = _FakeTranslateClient()
        self.clients.append(client)
        return client

    def get_project_id(self, user_id: str) -> str:
        """Return a deterministic fake project id."""
        return f"proj-{user_id}"


def _make_translator(
    manager: _FakeCredentialsManager,
    user_id: str = "scholar-1",
    **kwargs: Any,
) -> GcpSyncTranslator:
    """Build a translator against the fake manager (fast retries for tests)."""
    kwargs.setdefault("retry_base_delay", 0.001)
    kwargs.setdefault("retry_max_delay", 0.003)
    return GcpSyncTranslator(manager, user_id, **kwargs)


# ---------------------------------------------------------------------------
# T-1.1 — Engine contract (surface parity)
# ---------------------------------------------------------------------------


class TestEngineContract:
    """Contract tests for GcpSyncTranslator + GcpSyncTranslationService."""

    def test_translate_text_returns_translated_string(self) -> None:
        """translate_text delegates to v3 translateText and returns a string."""
        manager = _FakeCredentialsManager()
        manager.grant("scholar-1")
        translator = _make_translator(manager)

        result = asyncio.run(translator.translate_text("Der Geist", "DE", "EN"))

        assert result == "EN:Der Geist"
        client = manager.clients[-1]
        request = client.text_requests[-1]
        assert request.contents == ["Der Geist"]
        assert request.mime_type == "text/plain"
        assert request.source_language_code == "de"
        assert request.target_language_code == "en"
        assert request.parent == (
            f"projects/proj-scholar-1/locations/{GCP_SYNC_REGION}"
        )

    def test_translate_batch_preserves_order_and_chunks(self, monkeypatch) -> None:
        """translate_batch chunks by TRANSLATION_BATCH_SIZE with stable order."""
        monkeypatch.setenv("TRANSLATION_BATCH_SIZE", "2")
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        texts = ["a", "b", "c", "d", "e"]
        result = asyncio.run(translator.translate_batch(texts, "de", "en"))

        assert result == ["EN:a", "EN:b", "EN:c", "EN:d", "EN:e"]
        client = manager.clients[-1]
        chunk_sizes = [len(r.contents) for r in client.text_requests]
        assert chunk_sizes == [2, 2, 1]

    def test_translate_batch_empty_items_bypass_remote(self) -> None:
        """Blank strings are preserved locally and never sent to the API."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        result = asyncio.run(translator.translate_batch(["a", "   ", "c"], "de", "en"))

        assert result == ["EN:a", "", "EN:c"]
        request = manager.clients[-1].text_requests[-1]
        assert request.contents == ["a", "c"]

    def test_translate_document_preview_returns_byte_stream(self) -> None:
        """translate_document uses the sync preview tier and returns BytesIO."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")
        source = io.BytesIO(b"%PDF-1.4 sample")

        out = asyncio.run(
            translator.translate_document(source, "application/pdf", "de", "en")
        )

        assert isinstance(out, io.BytesIO)
        assert out.read() == b"TRANSLATED[%PDF-1.4 sample]"
        request = manager.clients[-1].doc_requests[-1]
        assert request.document_input_config.mime_type == "application/pdf"
        assert request.document_output_config.mime_type == "application/pdf"

    def test_get_available_providers_returns_gcp(self) -> None:
        """The facade reports exactly one provider: gcp."""
        service = GcpSyncTranslationService(_FakeCredentialsManager())
        assert service.get_available_providers() == ["gcp"]

    def test_statistics_keys_stable(self) -> None:
        """Statistics expose a stable key set across engine and facade."""
        expected = {
            "total_calls",
            "translated_texts",
            "translated_documents",
            "errors",
        }
        assert set(STATS_KEYS) == expected
        service = GcpSyncTranslationService(_FakeCredentialsManager())
        assert expected.issubset(service.get_statistics().keys())

    def test_translator_for_user_cached_per_user(self) -> None:
        """translator_for_user caches one bound engine per user id."""
        manager = _FakeCredentialsManager()
        service = GcpSyncTranslationService(manager)

        first = service.translator_for_user("scholar-1")
        second = service.translator_for_user("scholar-1")
        other = service.translator_for_user("scholar-2")

        assert first is second
        assert first is not other
        assert set(service.providers.keys()) == {"scholar-1", "scholar-2"}

    def test_close_and_aclose_are_safe_noops(self) -> None:
        """Lifecycle methods are no-ops; BYOK owns the client lifecycle."""
        manager = _FakeCredentialsManager()
        translator = _make_translator(manager)
        service = GcpSyncTranslationService(manager)

        translator.close()
        asyncio.run(translator.aclose())
        service.close()
        asyncio.run(service.aclose())

        assert manager.clients == []

    def test_engine_exports_no_host_credential_surface(self) -> None:
        """The engine carries no legacy host-held key attributes (BYOK-only)."""
        manager = _FakeCredentialsManager()
        translator = _make_translator(manager)

        assert not hasattr(translator, "api_key")
        assert not hasattr(translator, "base_url")
        assert translator.PROVIDER_NAME == "gcp"


# ---------------------------------------------------------------------------
# T-1.2 — Fail-closed gate, resilience, terminology parity
# ---------------------------------------------------------------------------


class TestFailClosedGate:
    """BYOK fail-closed behavior (ADR 0004 D3)."""

    def test_missing_credentials_raises_typed_error(self) -> None:
        """Translation without credentials fails closed with onboarding hint."""
        manager = _FakeCredentialsManager()
        translator = _make_translator(manager)

        with pytest.raises(GcpSyncCredentialsRequiredError) as excinfo:
            asyncio.run(translator.translate_text("Halb", "de", "en"))

        assert excinfo.value.code == "GCP_CREDENTIALS_REQUIRED"
        assert "/api/v1/byok/onboarding-guide" in str(excinfo.value)

    def test_credential_vanished_midflight_maps_to_typed_error(self) -> None:
        """A race where credentials disappear mid-call maps to the same code."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        manager.raise_on_client = True
        translator = _make_translator(manager, user_id="u")

        with pytest.raises(GcpSyncCredentialsRequiredError) as excinfo:
            asyncio.run(translator.translate_text("Halb", "de", "en"))

        assert excinfo.value.code == "GCP_CREDENTIALS_REQUIRED"

    def test_constructor_requires_byok_manager(self) -> None:
        """Ambient/host-held credentials are structurally impossible."""
        with pytest.raises(ValueError, match="BYOKCredentialsManager"):
            GcpSyncTranslator(None, "scholar-1")
        manager = _FakeCredentialsManager()
        with pytest.raises(ValueError, match="user_id"):
            GcpSyncTranslator(manager, "   ")
        with pytest.raises(ValueError, match="BYOKCredentialsManager"):
            GcpSyncTranslationService(None)


class TestResilience:
    """Transient retry routing through utils.gcp_helpers (ADR 0004 D2.13)."""

    def test_transient_gcp_error_retried_then_succeeds(self) -> None:
        """ResourceExhausted (429) is retried and succeeds on the next call."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        client = _FakeTranslateClient(fail_times=1)  # transient, by default
        manager.pending_clients.append(client)

        result = asyncio.run(translator.translate_text("Gast", "de", "en"))

        assert result == "EN:Gast"
        assert client.failure_count == 1
        assert len(client.text_requests) == 1

    def test_non_transient_error_raises_without_retry(self) -> None:
        """Program errors fail fast on first occurrence (no retry burn)."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        def _fail_with_value_error() -> None:
            msg = "programming error"
            raise ValueError(msg)

        client = _FakeTranslateClient(
            fail_times=1, error_factory=_fail_with_value_error
        )
        manager.pending_clients.append(client)

        with pytest.raises(ValueError, match="programming error"):
            asyncio.run(translator.translate_text("X", "de", "en"))

        assert client.failure_count == 1
        assert len(client.text_requests) == 0


class TestTerminologyParity:
    """Word-boundary terminology preservation (parity with TranslationService)."""

    def test_terms_wrapped_before_request_and_stripped_after(self) -> None:
        """Source terms are notranslate-wrapped pre-request and stripped post."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(
            manager,
            user_id="u",
            terminology_map={"Geist": "spirit"},
        )

        result = asyncio.run(
            translator.translate_text("Der Geist liest Geisterstadt", "de", "en")
        )

        request = manager.clients[-1].text_requests[-1]
        sent = request.contents[0]
        assert '<span translate="no">Geist</span>' in sent
        assert 'translate="no">Geister' not in sent  # boundary safety
        assert result == "EN:Der Geist liest Geisterstadt"
        assert "<span" not in result


# ---------------------------------------------------------------------------
# NFR-1 — Non-blocking I/O: remote calls off the event loop
# ---------------------------------------------------------------------------


class TestNonBlockingIO:
    """Remote calls execute via asyncio.to_thread (never on the event loop)."""

    def test_remote_calls_run_off_event_loop(self, monkeypatch) -> None:
        """asyncio.to_thread is used for the synchronous gRPC invocation."""
        import services.gcp_sync_translation_service as gmod

        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        original = asyncio.to_thread
        seen: list[str] = []

        def spy_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            """Record the first-positional function name then delegate."""
            seen.append(getattr(fn, "__name__", "?"))
            return original(fn, *args, **kwargs)

        monkeypatch.setattr(gmod.asyncio, "to_thread", spy_thread)

        result = asyncio.run(translator.translate_text("Welt", "de", "en"))

        assert result == "EN:Welt"
        assert any("worker" in name or "sync" in name for name in seen)


# ---------------------------------------------------------------------------
# Track B — legacy caller parity: provider param + content-dict documents
# ---------------------------------------------------------------------------


class TestProviderArgCompat:
    """Trailing ``provider`` positional accepted (legacy call parity)."""

    def test_translate_text_accepts_provider_gcp_and_auto(self) -> None:
        """Explicit provider values for the GCP tier are accepted verbatim."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        result = asyncio.run(translator.translate_text("Der Geist", "de", "en", "gcp"))

        assert result == "EN:Der Geist"

        auto_result = asyncio.run(
            translator.translate_text("Der Geist", "de", "en", "auto")
        )

        assert auto_result == "EN:Der Geist"

    def test_translate_text_rejects_unknown_provider(self) -> None:
        """Unknown providers fail closed (no silent substitution, ADR D3)."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        with pytest.raises(ValueError, match="Unsupported provider"):
            asyncio.run(translator.translate_text("X", "de", "en", "lingo"))

    def test_translate_batch_accepts_provider_positional(self) -> None:
        """Batch calls keep accepting the trailing provider argument."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        result = asyncio.run(translator.translate_batch(["a", "b"], "de", "en", "gcp"))

        assert result == ["EN:a", "EN:b"]

    def test_engine_get_available_providers_is_gcp(self) -> None:
        """Engine-level provider registry is stable for philosophy adapters."""
        manager = _FakeCredentialsManager()
        translator = _make_translator(manager)

        assert translator.get_available_providers() == ["gcp"]


class TestContentDictDocumentContract:
    """Legacy content-dict translate_document contract (philosophy fallback)."""

    def _content(self) -> dict[str, Any]:
        """Minimal extracted-content dict with text elements."""
        return {
            "type": "pdf_advanced",
            "pages": [
                {
                    "page_num": 0,
                    "text_elements": [
                        {"id": "e1", "text": "Der Geist"},
                        {"id": "e2", "text": ""},
                        {"id": "e3", "text": "Kraft und Not"},
                    ],
                }
            ],
        }

    def test_content_dict_translated_positionally(self) -> None:
        """(content, source, target, provider, callback) positional legacy shape."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")

        percents: list[int] = []
        result = asyncio.run(
            translator.translate_document(
                self._content(), "de", "en", "gcp", percents.append
            )
        )

        element = result["pages"][0]["text_elements"]
        assert element[0]["text"] == "EN:Der Geist"
        assert element[1]["text"] == ""
        assert element[2]["text"] == "EN:Kraft und Not"
        assert percents[0] == 0
        assert percents[-1] == 100
        assert percents == sorted(percents)

    def test_content_dict_requires_credentials(self) -> None:
        """Missing credentials raise the typed fail-closed error."""
        manager = _FakeCredentialsManager()
        translator = _make_translator(manager)

        with pytest.raises(GcpSyncCredentialsRequiredError):
            asyncio.run(
                translator.translate_document(self._content(), "de", "en", "gcp", None)
            )

    def test_stream_contract_still_supported(self) -> None:
        """The Track A BinaryIO preview contract remains intact."""
        manager = _FakeCredentialsManager()
        manager.grant("u")
        translator = _make_translator(manager, user_id="u")
        source = io.BytesIO(b"%PDF-1.4 sample")

        out = asyncio.run(
            translator.translate_document(source, "application/pdf", "de", "en")
        )

        assert out.read() == b"TRANSLATED[%PDF-1.4 sample]"
