"""A2: auth/identity contract (FR-08, NFR-01)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import fulfill_json, mock_api


def _goto(spa_page: Any, spa_base_url: str) -> None:
    spa_page.goto(f"{spa_base_url}/")


def test_token_and_user_id_persist_to_session_storage_only(
    spa_page: Any, spa_base_url: str
) -> None:
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "test-jwt-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")

    stored = spa_page.evaluate(
        "() => ({token: sessionStorage.getItem('pl.token'), user: sessionStorage.getItem('pl.userId')})"
    )
    assert stored == {"token": "test-jwt-token", "user": "scholar-01"}
    assert spa_page.evaluate("() => Object.keys(localStorage)") == []


def test_logout_clears_session_storage(spa_page: Any, spa_base_url: str) -> None:
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "test-jwt-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.click("#auth-clear")

    assert spa_page.evaluate("() => sessionStorage.getItem('pl.token')") is None
    assert spa_page.evaluate("() => sessionStorage.getItem('pl.userId')") is None


def test_401_surfaces_reauth_prompt(spa_page: Any, spa_base_url: str) -> None:
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "expired-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")

    mock_api(
        spa_page,
        [
            (
                "GET",
                "/api/v1/vocabulary/",
                lambda r: fulfill_json(r, {"detail": "expired"}, status=401),
            )
        ],
    )
    spa_page.click("#vocab-refresh")

    expect(spa_page.locator("#auth-prompt")).to_be_visible()


def test_unauthenticated_call_is_flagged_before_send(
    spa_page: Any, spa_base_url: str
) -> None:
    _goto(spa_page, spa_base_url)
    spa_page.click("#vocab-refresh")

    expect(spa_page.locator("#auth-prompt")).to_be_visible()


def test_api_key_sends_x_api_key_header(spa_page: Any, spa_base_url: str) -> None:
    captured = mock_api(
        spa_page,
        [("GET", "/api/v1/vocabulary/", lambda r: fulfill_json(r, {}))],
    )
    _goto(spa_page, spa_base_url)
    spa_page.select_option("#auth-token-type", "api-key")
    spa_page.fill("#auth-token", "my-secret-api-key")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")

    spa_page.click("#vocab-refresh")
    from tests.frontend.conftest import wait_for_request

    req = wait_for_request(captured, lambda r: "/api/v1/vocabulary/" in r.url)
    assert req.headers.get("x-api-key") == "my-secret-api-key"
    assert "authorization" not in req.headers


def test_bearer_token_sends_authorization_header(
    spa_page: Any, spa_base_url: str
) -> None:
    captured = mock_api(
        spa_page,
        [("GET", "/api/v1/vocabulary/", lambda r: fulfill_json(r, {}))],
    )
    _goto(spa_page, spa_base_url)
    spa_page.select_option("#auth-token-type", "bearer")
    spa_page.fill("#auth-token", "my-jwt-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")

    spa_page.click("#vocab-refresh")
    from tests.frontend.conftest import wait_for_request

    req = wait_for_request(captured, lambda r: "/api/v1/vocabulary/" in r.url)
    assert req.headers.get("authorization") == "Bearer my-jwt-token"
    assert "x-api-key" not in req.headers
