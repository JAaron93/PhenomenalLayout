"""Tests ensuring the web-eval demo never exposes API key material."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

_DEMO_PATH = Path(__file__).resolve().parents[1] / "examples" / "web_eval_demo.py"


def _load_demo() -> Any:
    spec = importlib.util.spec_from_file_location("web_eval_demo_under_test", _DEMO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


class TestApiKeyDisplay:
    @pytest.mark.usefixtures("no_sleep")
    def test_set_key_prints_only_presence(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("OP_API_KEY", "super-secret-key-value")
        _load_demo().main()
        output = capsys.readouterr().out
        assert "super-secret-key-value" not in output
        assert "fingerprint" not in output.lower()
        assert "API Key: set" in output

    @pytest.mark.usefixtures("no_sleep")
    def test_missing_key_prints_not_set(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("OP_API_KEY", raising=False)
        _load_demo().main()
        output = capsys.readouterr().out
        assert "API Key: not set" in output

    def test_demo_does_not_import_hashing(self) -> None:
        source = _DEMO_PATH.read_text(encoding="utf-8")
        assert "hashlib" not in source
        assert "sha256" not in source
        assert os.environ.get("OP_API_KEY", "") != "super-secret-key-value"
