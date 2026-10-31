"""A7: dual-pane viewer, text-only (FR-07)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import fulfill_json, mock_api


def _pair(page_number: int) -> dict[str, Any]:
    return {
        "page_number": page_number,
        "total_pages_german": 10,
        "total_pages_english": 10,
        "german_text": f"Deutscher Originaltext Seite {page_number}",
        "english_text": f"English translated text page {page_number}",
    }


def test_dualpane_renders_pairs_with_navigation(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    captured = mock_api(
        spa_page,
        [("POST", "/api/v1/book/dual-pane/", lambda r: fulfill_json(r, _pair(2)))],
    )
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.fill("#dualpane-session", "sess-a1")
    spa_page.set_input_files("#dualpane-file", str(fixture_pdf))
    spa_page.fill("#dualpane-page", "2")
    spa_page.click("#dualpane-load")

    content = spa_page.locator("#dualpane-content")
    expect(content).to_contain_text("Deutscher Originaltext Seite 2")
    assert "English translated text page 2" in (content.inner_text() or "")
    assert "thumbnails" not in (content.inner_text() or "").lower()
    request = captured[0]
    assert "user_id=scholar-01" in request.url
    assert "page_number=2" in request.url
    assert "/api/v1/book/dual-pane/sess-a1" in request.url
    assert "filename=" in (request.post_data or "")
