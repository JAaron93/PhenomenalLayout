"""A5: pre-scan + terminology (FR-04) + path/form request shapes (FR-08)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import fulfill_json, mock_api, wait_for_request


def _scan_payload() -> dict[str, Any]:
    return {
        "total_pages": 10,
        "script_analysis": {
            "script_type": "ANTIQUA",
            "ocr_confidence_score": 0.95,
            "recommended_action": "Direct batch translation",
        },
        "ocr_confidence": {"confidence_score": 0.95, "script_type": "Antiqua"},
        "detected_neologisms": [
            {"term": "Dasein"},
            {"term": "Geworfenheit"},
        ],
        "prefilled_terms": {
            "Dasein": {"german_term": "Dasein", "preferred_translation": "Being-there"}
        },
        "sample_text": "Dasein im Widersacher",
    }


def test_prescan_renders_badge_neologisms_terms(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    captured = mock_api(
        spa_page,
        [("POST", "/api/v1/book/pre-scan", lambda r: fulfill_json(r, _scan_payload()))],
    )
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.set_input_files("#prescan-file", str(fixture_pdf))
    spa_page.click("#prescan-run")

    expect(spa_page.locator("#prescan-result")).to_contain_text("Dasein")
    result = spa_page.locator("#prescan-result").inner_text()
    assert "0.95" in result
    assert "Dasein" in result and "Geworfenheit" in result
    request = wait_for_request(captured, lambda r: "/api/v1/book/pre-scan" in r.url)
    body = request.post_data or ""
    assert 'name="user_id"' in body and "scholar-01" in body


def test_vocabulary_save_uses_path_user_id(spa_page: Any, spa_base_url: str) -> None:
    captured = mock_api(
        spa_page,
        [
            (
                "POST",
                "/api/v1/vocabulary/",
                lambda r: fulfill_json(
                    r, {"german_term": "Geist", "preferred_translation": "Mind"}
                ),
            )
        ],
    )
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.fill("#vocab-term", "Geist")
    spa_page.fill("#vocab-translation", "Mind")
    spa_page.click("#vocab-save")

    assert captured[0].url.endswith("/api/v1/vocabulary/scholar-01")
    import json

    assert json.loads(captured[0].post_data or "{}") == {
        "german_term": "Geist",
        "preferred_translation": "Mind",
    }


def test_vocabulary_list_and_export(spa_page: Any, spa_base_url: str) -> None:
    from tests.frontend.conftest import fulfill_pdf

    captured = mock_api(
        spa_page,
        [
            (
                "GET",
                "/api/v1/vocabulary/scholar-01",
                lambda r: fulfill_json(
                    r,
                    {
                        "Geist": {
                            "german_term": "Geist",
                            "preferred_translation": "Mind",
                        }
                    },
                ),
            ),
            ("GET", "/api/v1/vocabulary/scholar-01/export", fulfill_pdf),
        ],
    )
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.click("#vocab-refresh")

    expect(spa_page.locator("#vocab-list")).to_contain_text("Geist")
    wait_for_request(
        captured, lambda r: "/api/v1/vocabulary/scholar-01/export" in r.url
    )
