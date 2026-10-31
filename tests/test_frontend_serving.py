"""SPA serving and Gradio-mount removal checks (spec A1, FR-09 first half)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_root_serves_spa_shell() -> None:
    response = _client().get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="app"' in response.text


def test_ui_route_is_gone() -> None:
    response = _client().get("/ui")
    assert response.status_code == 404


def test_no_gradio_import_in_app() -> None:
    from pathlib import Path

    import app

    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "gradio" not in source
