"""Fixtures and helpers for the SPA Playwright specs (Track A, spec A2-A7).

Browser specs carry the ``frontend`` marker and are excluded from default
runs (pytest.ini ``-m "not frontend"``): pytest-playwright's driver event
loop and pytest-asyncio's Runner cannot share a process (async tests fail
with ``Runner.run() cannot be called from a running event loop``). Run them
with ``pytest -m frontend tests/frontend``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

_CALL = tuple[str, str, Callable[[Any], Any]]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag every spec collected under tests/frontend with the frontend marker."""
    frontend_root = Path(__file__).resolve().parent
    for item in items:
        if str(item.fspath).startswith(str(frontend_root)):
            item.add_marker(pytest.mark.frontend)


def wait_for_request(
    captured: list[Any], predicate: Callable[[Any], bool], timeout: float = 5.0
) -> Any:
    """Return the last captured request matching predicate, polling briefly.

    Route interception and fulfillment are asynchronous with respect to
    Playwright actions, so assertions on captured traffic must wait.
    """
    deadline = time.monotonic() + timeout
    while True:
        matches = [request for request in captured if predicate(request)]
        if matches:
            return matches[-1]
        if time.monotonic() >= deadline:
            raise AssertionError("expected request was not captured in time")
        time.sleep(0.05)


@pytest.fixture(scope="session")
def spa_base_url() -> Iterator[str]:
    """Serve the real FastAPI app on an ephemeral loopback port."""
    import app as app_module

    config = uvicorn.Config(
        app_module.create_app(), host="127.0.0.1", port=0, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    else:
        raise RuntimeError("SPA server did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def spa_page(page: Any) -> Any:
    page.set_default_timeout(3_000)
    return page


def mock_api(page: Any, routes: list[_CALL]) -> list[Any]:
    """Intercept /api/v1 calls; return the captured requests in order.

    Each route is ``(method, url_substring, responder)``; unmatched calls get a
    JSON 404 so spec failures point at the missing mock.
    """
    captured: list[Any] = []

    def handle(route: Any) -> None:
        request = route.request
        captured.append(request)
        for method, needle, responder in routes:
            if request.method == method and needle in request.url:
                responder(route)
                return
        route.fulfill(status=404, json={"detail": "unmocked endpoint"})

    page.route("**/api/v1/**", handle)
    return captured


def fulfill_json(route: Any, payload: Any, status: int = 200) -> None:
    route.fulfill(status=status, json=payload)


def fulfill_pdf(route: Any, name: str = "translated.pdf") -> None:
    route.fulfill(
        status=200,
        body=b"%PDF-1.4 mocked translated output",
        headers={
            "content-type": "application/pdf",
            "content-disposition": f'attachment; filename="{name}"',
        },
    )


@pytest.fixture
def fixture_pdf(tmp_path: Path) -> Path:
    """A one-page text PDF built with the dev-only reportlab fixture dep."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path = tmp_path / "fixture-book.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, "Sein und Zeit - fixture page")
    c.showPage()
    c.save()
    return path


def form_field(request: Any, name: str) -> str:
    """Extract a field from a multipart form-data request body."""
    body = request.post_data or ""
    marker = f'name="{name}"\r\n\r\n'
    start = body.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    return body[start : body.find("\r\n----", start)]
