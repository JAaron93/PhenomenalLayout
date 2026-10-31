"""A4: BYOK panel (FR-03) + request-shape contract for BYOK routes (FR-08)."""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import fulfill_json, mock_api


def _goto(spa_page: Any, spa_base_url: str) -> None:
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")


def test_credentials_post_sends_json_body(spa_page: Any, spa_base_url: str) -> None:
    captured = mock_api(
        spa_page,
        [
            (
                "POST",
                "/api/v1/byok/credentials",
                lambda r: fulfill_json(
                    r,
                    {
                        "is_valid": True,
                        "translation_api_ok": True,
                        "storage_bucket_ok": True,
                    },
                ),
            ),
        ],
    )
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.fill("#byok-project", "my-project")
    spa_page.fill("#byok-bucket", "my-bucket")
    spa_page.fill("#byok-sa", '{"type": "service_account"}')
    spa_page.click("#byok-save")

    expect(spa_page.locator("#byok-result")).to_contain_text("Translation API: OK")
    assert len(captured) == 1
    request = captured[0]
    assert request.headers.get("authorization") == "Bearer test-token"
    body = json.loads(request.post_data or "{}")
    assert body == {
        "user_id": "scholar-01",
        "project_id": "my-project",
        "bucket_name": "my-bucket",
        "sa_json": '{"type": "service_account"}',
    }


def test_validate_and_clear_use_query_user_id(spa_page: Any, spa_base_url: str) -> None:
    captured = mock_api(
        spa_page,
        [
            (
                "GET",
                "/api/v1/byok/validate",
                lambda r: fulfill_json(r, {"is_valid": True}),
            ),
            (
                "DELETE",
                "/api/v1/byok/credentials",
                lambda r: fulfill_json(r, {"success": True}),
            ),
        ],
    )
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.click("#byok-validate")
    spa_page.click("#byok-clear")

    urls = [request.url for request in captured]
    assert any("user_id=scholar-01" in url and "/byok/validate" in url for url in urls)
    assert any(
        "user_id=scholar-01" in url and "/byok/credentials" in url for url in urls
    )


def test_403_surfaces_reauth_prompt(spa_page: Any, spa_base_url: str) -> None:
    mock_api(
        spa_page,
        [
            (
                "POST",
                "/api/v1/byok/credentials",
                lambda r: fulfill_json(r, {"detail": "Access denied"}, status=403),
            )
        ],
    )
    _goto(spa_page, spa_base_url)
    spa_page.fill("#auth-token", "attacker-token")
    spa_page.fill("#auth-user", "attacker")
    spa_page.click("#auth-save")
    spa_page.fill("#byok-project", "victim-project")
    spa_page.fill("#byok-bucket", "victim-bucket")
    spa_page.fill("#byok-sa", "{}")
    spa_page.click("#byok-save")

    expect(spa_page.locator("#auth-prompt")).to_be_visible()
