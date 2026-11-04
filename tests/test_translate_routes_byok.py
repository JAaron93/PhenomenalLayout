"""Route-rewiring BYOK identity tests (ADR 0004 / Track B, T-2.1).

``/translate`` (content job flow) and ``/philosophy/translate`` must acquire
an explicit ``user_id`` authenticated exactly like ``POST /book/translate``
(``api/routes.py:1458-1465``) and fail closed with ``GCP_CREDENTIALS_REQUIRED``
(HTTP 503) when the caller's BYOK credentials are absent.

These tests exercise the live FastAPI app through ``TestClient`` with the
conftest-canonical auth environment. They are user-isolated (per-test unique
user ids) because the shared ``BYOKCredentialsManager`` singleton is
process-wide.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient


def _unique_user(prefix: str = "byok-solo") -> str:
    """Return a per-test-unique user id (avoids shared-vault pollution)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _encode_unique_user() -> str:
    """Return a per-test-unique user id safe for JWT sub claims."""
    return _unique_user("byok-auth")


# ---------------------------------------------------------------------------
# Plugin: monkeypatched user-bound engine stub for route-level binding tests
# ---------------------------------------------------------------------------


class _StubBoundEngine:
    """User-bound engine stub satisfying the GcpSyncTranslator call shape."""

    def __init__(self, user_id: str) -> None:
        """Bind the engine to a user id (echo callsites)."""
        self.user_id = user_id
        self.batch_calls: list[tuple[list[str], str, str]] = []

    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """Echo texts with a visible marker."""
        self.batch_calls.append((list(texts), source_lang, target_lang))
        return [f"T:{t}" for t in texts]


# ---------------------------------------------------------------------------
# /translate — identity, auth, fail-closed submission, engine binding
# ---------------------------------------------------------------------------


class TestTranslateEndpointIdentity:
    """POST /api/v1/translate gains the /book/translate identity pattern."""

    def test_translate_without_user_id_fails_validation(
        self, test_client: TestClient
    ) -> None:
        """Missing user_id is a 422 validation error (never a silent job)."""
        response = test_client.post(
            "/api/v1/translate",
            params={
                "file_path": "doc.pdf",
                "source_language": "de",
                "target_language": "en",
            },
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 422

    def test_translate_unauthenticated_returns_401(
        self, test_client: TestClient
    ) -> None:
        """No credentials in headers → 401 (auth enabled by default)."""
        response = test_client.post(
            "/api/v1/translate",
            params={
                "file_path": "doc.pdf",
                "source_language": "de",
                "target_language": "en",
            },
            data={"user_id": _unique_user()},
        )
        assert response.status_code == 401

    def test_translate_missing_credentials_fails_closed_503(
        self, test_client: TestClient
    ) -> None:
        """Valid auth but no BYOK credentials → 503 + GCP_CREDENTIALS_REQUIRED."""
        user_id = _unique_user()
        response = test_client.post(
            "/api/v1/translate",
            params={
                "file_path": "doc.pdf",
                "source_language": "de",
                "target_language": "en",
            },
            data={"user_id": user_id},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 503
        assert "GCP_CREDENTIALS_REQUIRED" in response.text

    def test_translate_submission_binds_engine_and_job_user(
        self, test_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful submission stores user_id and binds the user's engine."""
        import api.routes as routes_module

        user_id = _unique_user()
        engine = _StubBoundEngine(user_id)

        class _FakeFacade:
            """Facade stand-in resolving engines by user id."""

            def translator_for_user(self, bound_user: str, **_: Any) -> Any:
                """Always resolves the test's stub engine."""
                assert bound_user == user_id
                return engine

        monkeypatch.setattr(
            routes_module, "get_translation_facade", lambda: _FakeFacade()
        )
        # Keep the background job off real document processing.
        content: dict[str, Any] = {
            "type": "pdf_advanced",
            "text_by_page": {"0": ["Hallo", ""]},
            "file_path": "doc.pdf",
            "pages": [],
            "layouts": [],
        }

        async def _fake_extract(_file_path: str) -> dict[str, Any]:
            """Avoid disk extraction in the background job."""
            return content

        monkeypatch.setattr(
            routes_module.document_processor,
            "extract_content",
            _fake_extract,
            raising=True,
        )
        monkeypatch.setattr(
            routes_module.document_processor,
            "create_translated_document",
            lambda *_args, **_kw: "translated_stub.pdf",
            raising=True,
        )

        from api.routes import get_byok_credentials_manager

        manager = get_byok_credentials_manager()
        monkeypatch.setattr(
            manager,
            "has_credentials",
            lambda _uid: _uid == user_id,
            raising=True,
        )

        response = test_client.post(
            "/api/v1/translate",
            params={
                "file_path": "doc.pdf",
                "source_language": "de",
                "target_language": "en",
            },
            data={"user_id": user_id},
            headers={"X-API-Key": "test-admin-key"},
        )

        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]

        # Job records the owning user and runs to completion off the engine.
        job = routes_module.translation_jobs[job_id]
        assert job["user_id"] == user_id

        status_response = test_client.get(
            f"/api/v1/status/{job_id}", headers={"X-API-Key": "test-admin-key"}
        )
        assert status_response.json()["status"] == "completed"
        assert engine.batch_calls, "bound engine must be exercised by the job"
        texts, source, target = engine.batch_calls[0]
        assert texts == ["Hallo"]
        assert (source, target) == ("de", "en")


# ---------------------------------------------------------------------------
# /philosophy/translate — identity, auth, fail-closed 503, bound engine
# ---------------------------------------------------------------------------


class TestPhilosophyTranslateEndpointIdentity:
    """POST /api/v1/philosophy/translate gains the identity pattern."""

    _BODY_BASE: ClassVar[dict[str, Any]] = {
        "text": "Der Geist der Philosophie",
        "source_language": "de",
        "target_language": "en",
        "session_id": "route-test-session",
    }

    def test_philosophy_translate_without_user_id_fails_validation(
        self, test_client: TestClient
    ) -> None:
        """Missing user_id is a validation error (never unauthenticated work)."""
        response = test_client.post(
            "/api/v1/philosophy/translate",
            json=dict(self._BODY_BASE),
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 422

    def test_philosophy_translate_unauthenticated_returns_401(
        self, test_client: TestClient
    ) -> None:
        """No credentials in headers → 401."""
        response = test_client.post(
            "/api/v1/philosophy/translate",
            json={**self._BODY_BASE, "user_id": _unique_user()},
        )
        assert response.status_code == 401

    def test_philosophy_translate_missing_credentials_fails_closed_503(
        self, test_client: TestClient
    ) -> None:
        """Valid auth but no BYOK credentials → 503 + onboarding response."""
        response = test_client.post(
            "/api/v1/philosophy/translate",
            json={**self._BODY_BASE, "user_id": _unique_user()},
            headers={"X-API-Key": "test-admin-key"},
        )
        assert response.status_code == 503
        assert "GCP_CREDENTIALS_REQUIRED" in response.text

    def test_philosophy_translate_uses_user_bound_engine(
        self, test_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Request-path philosophy service wraps the user's bound engine."""
        import api.routes as routes_module

        user_id = _unique_user()
        engine = _StubBoundEngine(user_id)

        class _FakeFacade:
            """Facade stand-in resolving engines by user id."""

            def translator_for_user(self, bound_user: str, **_: Any) -> Any:
                """Always resolves the test's stub engine."""
                assert bound_user == user_id
                return engine

        monkeypatch.setattr(
            routes_module, "get_translation_facade", lambda: _FakeFacade()
        )

        class _StubPhilosophy:
            """Stand-in for the request-bound PhilosophyEnhanced wrapper."""

            def __init__(self) -> None:
                """Remember the engine the route bound for this user."""
                self.engine = engine

            async def translate_text_with_neologism_handling_async(
                self,
                text: str,
                _source_lang: str,
                _target_lang: str,
                _provider: str = "auto",
                _session_id: str | None = None,
                **_kwargs: Any,
            ) -> dict[str, str]:
                """Echo with a fixed marker and report the engine."""
                return {
                    "translated_text": "PHILOSOPHY:" + text,
                    "bound_user": self.engine.user_id,
                }

        monkeypatch.setattr(
            routes_module,
            "build_philosophy_service",
            lambda _translator: _StubPhilosophy(),
            raising=False,
        )

        from api.routes import get_byok_credentials_manager

        manager = get_byok_credentials_manager()
        monkeypatch.setattr(
            manager,
            "has_credentials",
            lambda _uid: _uid == user_id,
            raising=True,
        )

        response = test_client.post(
            "/api/v1/philosophy/translate",
            json={**self._BODY_BASE, "user_id": user_id},
            headers={"X-API-Key": "test-admin-key"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["translated_text"].startswith("PHILOSOPHY:")
        assert payload["bound_user"] == user_id

    def test_philosophy_translate_cross_user_identity_rejected(
        self, test_client: TestClient
    ) -> None:
        """A non-admin identity cannot translate on behalf of another user."""
        import api.auth

        token = api.auth.create_jwt_token(
            _encode_unique_user(), api.auth.UserRole.READ_ONLY
        )
        response = test_client.post(
            "/api/v1/philosophy/translate",
            json={**self._BODY_BASE, "user_id": _unique_user()},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Config endpoints unchanged (providers surface through the GCP facade)
# ---------------------------------------------------------------------------


class TestConfigEndpointsUnchanged:
    """GET /philosophy/config keeps working; providers report ['gcp']."""

    def test_philosophy_config_available_providers_is_gcp(
        self, test_client: TestClient
    ) -> None:
        """Provider registry surfaces exactly the GCP sync tier."""
        response = test_client.get(
            "/api/v1/philosophy/config", headers={"X-API-Key": "test-admin-key"}
        )
        assert response.status_code == 200
        assert response.json()["available_providers"] == ["gcp"]
