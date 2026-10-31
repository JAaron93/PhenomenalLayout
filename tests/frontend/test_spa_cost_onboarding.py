"""A3: cost estimator + onboarding walkthrough (FR-01, FR-02)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import fulfill_json, mock_api


def _goto(spa_page: Any, spa_base_url: str) -> None:
    spa_page.goto(f"{spa_base_url}/")


def test_cost_quote_renders_itemized_estimate(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    captured = mock_api(
        spa_page,
        [
            (
                "POST",
                "/api/v1/cost/estimate",
                lambda r: fulfill_json(
                    r,
                    {
                        "total_pages": 10,
                        "file_size_mb": 1.0,
                        "base_cost": 0.8,
                        "staging_overhead_cost": 0.001,
                        "storage_cost_1mo": 0.02,
                        "storage_cost_12mo": 0.24,
                        "free_tier_covered": True,
                        "total_estimate": 0.82,
                        "tolerance_range": [0.8, 5.82],
                        "estimation_time_sec": 0.05,
                    },
                ),
            )
        ],
    )
    _goto(spa_page, spa_base_url)
    spa_page.set_input_files("#cost-file", str(fixture_pdf))
    spa_page.click("#cost-submit")

    expect(spa_page.locator("#cost-result")).to_contain_text("$0.080/page")
    expect(spa_page.locator("#cost-result")).to_contain_text("$0.82")
    assert len(captured) == 1
    assert "filename=" in (captured[0].post_data or "")


def test_cost_estimator_filters_non_pdf(spa_page: Any, spa_base_url: str) -> None:
    _goto(spa_page, spa_base_url)
    assert spa_page.get_attribute("#cost-file", "accept") == ".pdf"


def test_onboarding_walkthrough_renders_six_steps(
    spa_page: Any, spa_base_url: str
) -> None:
    steps = [
        {"step_number": n, "title": f"Step {n}", "description": f"Do step {n}"}
        for n in range(1, 7)
    ]
    mock_api(
        spa_page,
        [
            (
                "GET",
                "/api/v1/byok/onboarding-guide",
                lambda r: fulfill_json(
                    r,
                    {
                        "steps": steps,
                        "gcloud_script": "gcloud services enable translate.googleapis.com",
                    },
                ),
            )
        ],
    )
    _goto(spa_page, spa_base_url)
    spa_page.click("#onboarding-open")

    expect(spa_page.locator(".onboarding-step")).to_have_count(6)
    expect(spa_page.locator("#gcloud-script")).to_contain_text("gcloud services enable")
    assert spa_page.is_visible("#onboarding-copy")
