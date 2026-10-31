"""A6: translation lifecycle, polling hygiene, failed-pages + re-run (FR-05/06, NFR-03)."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import expect

from tests.frontend.conftest import (
    form_field,
    fulfill_json,
    fulfill_pdf,
    mock_api,
    wait_for_request,
)

_POLL_MS = 400


def _active_job(session: str, book_id: str) -> dict[str, Any]:
    return {
        "session_id": session,
        "user_id": "scholar-01",
        "book_id": book_id,
        "lro_name": "projects/p/locations/us-central1/operations/op-1",
        "gcs_output_uri": f"gs://bucket/outputs/{book_id}/",
        "total_pages": 10,
        "translated_pages": 0,
        "failed_pages": 0,
        "status": "RUNNING",
    }


def _progress(done: bool, failed: int = 0) -> dict[str, Any]:
    return {
        "operation_name": "op-1",
        "state": "SUCCEEDED" if done else "RUNNING",
        "total_pages": 10,
        "translated_pages": 10 if done else 4,
        "failed_pages": failed,
        "completion_pct": 100.0 if done else 40.0,
        "is_done": done,
    }


def _summary(session: str, failed: int = 0) -> dict[str, Any]:
    return {
        "session_id": session,
        "status": "SUCCEEDED",
        "total_pages": 10,
        "translated_pages": 10 - failed,
        "failed_pages": failed,
        "is_done": True,
        "output_gcs_uri": "gs://bucket/outputs/book/",
    }


def test_lifecycle_polls_then_stops_and_downloads(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    status_calls = {"n": 0}

    def on_status(route: Any) -> None:
        status_calls["n"] += 1
        done = status_calls["n"] >= 2
        fulfill_json(route, _progress(done))

    routes: list[tuple[str, str, Any]] = [
        (
            "POST",
            "/api/v1/book/translate",
            lambda r: fulfill_json(r, _active_job("sess-a1", "fixture-book")),
        ),
        ("GET", "/api/v1/book/status/", on_status),
        (
            "POST",
            "/api/v1/book/complete/",
            lambda r: fulfill_json(r, _summary("sess-a1")),
        ),
        ("GET", "/api/v1/book/download/", fulfill_pdf),
    ]
    captured = mock_api(spa_page, routes)

    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.set_input_files("#translate-file", str(fixture_pdf))
    spa_page.select_option("#translate-target", "English")
    spa_page.click("#translate-start")

    spa_page.wait_for_selector("#translate-download:not([disabled])")
    assert "$" not in (spa_page.locator("#translate-status").inner_text() or "")

    # NFR-03: polling deactivates after completion.
    count_at_done = status_calls["n"]
    time.sleep(_POLL_MS / 1000 * 3)
    assert status_calls["n"] == count_at_done

    spa_page.click("#translate-download")
    download_request = wait_for_request(
        captured, lambda r: "/api/v1/book/download/" in r.url
    )
    assert "sess-a1" in download_request.url


def test_failed_pages_banner_and_rerun_uses_new_book_id(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    sessions = iter(["sess-a1", "sess-a2"])
    books = iter(["fixture-book", "fixture-book-r2"])

    def on_translate(route: Any) -> None:
        fulfill_json(route, _active_job(next(sessions), next(books)))

    def on_status(route: Any) -> None:
        fulfill_json(route, _progress(done=True, failed=2))

    def on_complete(route: Any) -> None:
        fulfill_json(route, _summary(route.request.url.split("/")[-2], failed=2))

    captured = mock_api(
        spa_page,
        [
            ("POST", "/api/v1/book/translate", on_translate),
            ("GET", "/api/v1/book/status/", on_status),
            ("POST", "/api/v1/book/complete/", on_complete),
            ("GET", "/api/v1/book/download/", fulfill_pdf),
        ],
    )

    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.set_input_files("#translate-file", str(fixture_pdf))
    spa_page.click("#translate-start")
    spa_page.wait_for_selector("#translate-warning")
    assert "2" in (spa_page.locator("#translate-warning").inner_text() or "")

    spa_page.click("#translate-rerun")
    spa_page.wait_for_selector("#translate-download:not([disabled])")

    translate_calls = [r for r in captured if "/api/v1/book/translate" in r.url]
    assert len(translate_calls) == 2
    first_book = form_field(translate_calls[0], "book_id")
    second_book = form_field(translate_calls[1], "book_id")
    assert first_book == "fixture-book"
    assert second_book == "fixture-book-r2"

    # The UI adopts the server-confirmed session ids (sess-a1, sess-a2).
    first_session = "sess-a1"
    second_session = "sess-a2"

    # Per-attempt downloads: the original session's output remains
    # downloadable after the re-run finishes (FR-06).
    original_link = spa_page.locator(f'a[data-session="{first_session}"]')
    expect(original_link).to_be_visible()
    original_link.click()
    original_download = wait_for_request(
        captured,
        lambda r: "/api/v1/book/download/" in r.url and first_session in r.url,
    )
    assert first_session in original_download.url

    rerun_link = spa_page.locator(f'a[data-session="{second_session}"]')
    expect(rerun_link).to_be_visible()
    rerun_link.click()
    rerun_download = wait_for_request(
        captured,
        lambda r: "/api/v1/book/download/" in r.url and second_session in r.url,
    )
    assert second_session in rerun_download.url


def test_error_state_stops_polling_and_disables_download(
    spa_page: Any, spa_base_url: str, fixture_pdf: Any
) -> None:
    status_calls = {"n": 0}

    def on_status(route: Any) -> None:
        status_calls["n"] += 1
        fulfill_json(
            route,
            _progress(done=False, failed=0) | {"state": "FAILED", "is_done": True},
        )

    mock_api(
        spa_page,
        [
            (
                "POST",
                "/api/v1/book/translate",
                lambda r: fulfill_json(r, _active_job("sess-err", "fixture-book")),
            ),
            ("GET", "/api/v1/book/status/", on_status),
        ],
    )
    spa_page.goto(f"{spa_base_url}/")
    spa_page.fill("#auth-token", "test-token")
    spa_page.fill("#auth-user", "scholar-01")
    spa_page.click("#auth-save")
    spa_page.set_input_files("#translate-file", str(fixture_pdf))
    spa_page.click("#translate-start")
    spa_page.wait_for_selector("#translate-error")

    count_at_error = status_calls["n"]
    time.sleep(_POLL_MS / 1000 * 3)
    assert status_calls["n"] == count_at_error
    assert spa_page.locator("#translate-download").is_disabled()
