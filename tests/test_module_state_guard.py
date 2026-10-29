"""Regression tests for the api/app module-family identity invariant.

Ordered single-process reproduction of the original flake (red before the
conftest identity guard, green after):

    pytest tests/test_config_issue.py tests/test_rate_limit.py

tests/test_config_issue.py pops the ``api`` package from sys.modules; before
the guard, the next test's ``monkeypatch.setattr("api.rate_limit.time", ...)``
failed with ``AttributeError: module 'api' has no attribute 'rate_limit'``.
"""

import importlib
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

import api.auth
import api.rate_limit
from tests.helpers import (
    API_MODULE_FAMILY,
    restore_module_family,
    snapshot_module_family,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_CROSS_TEST_PROBE = '''
import importlib
import sys

import pytest

import api.auth  # noqa: F401  — cache the family before the polluter runs
import api.rate_limit  # noqa: F401


@pytest.fixture
def _polluter_teardown_surgery():
    """Remove the api package in teardown, like tests/test_config_issue.py."""
    yield
    sys.modules.pop("api", None)
    sys.modules.pop("api.auth", None)


def test_polluter(_polluter_teardown_surgery) -> None:
    assert "api" in sys.modules


def test_victim(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr("api.rate_limit.time", sentinel)
    import api.rate_limit

    assert api.rate_limit.time is sentinel
    importlib.reload(api.rate_limit)
'''


def test_snapshot_restore_round_trips_identity() -> None:
    before = snapshot_module_family()

    sys.modules.pop("api", None)
    sys.modules.pop("api.auth", None)
    restore_module_family(before)

    assert sys.modules["api"] is before["api"].entry
    assert sys.modules["api.auth"] is before["api.auth"].entry
    assert sys.modules["api"].rate_limit is before["api.rate_limit"].parent_attr
    assert sys.modules["api"].auth is before["api.auth"].parent_attr


def test_resolve_survives_polluter_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = snapshot_module_family()
    try:
        sys.modules.pop("api", None)
        sys.modules.pop("api.auth", None)
    finally:
        restore_module_family(snapshot)

    # The victim pattern from tests/test_rate_limit.py: dotted-path patching
    # into api.rate_limit must resolve through a consistent package.
    sentinel = object()
    monkeypatch.setattr("api.rate_limit.time", sentinel)
    assert api.rate_limit.time is sentinel


def test_reload_raises_on_entry_attr_divergence() -> None:
    """importlib.reload requires the sys.modules entry to be the same object.

    Documents the mechanism behind the flake's teardown ImportError
    ("module api.rate_limit not in sys.modules"): the divergence class this
    suite's identity guard eliminates.
    """
    snapshot = snapshot_module_family(["api.rate_limit"])
    try:
        fresh = importlib.util.module_from_spec(
            importlib.machinery.ModuleSpec("api.rate_limit", None)
        )
        fresh.__package__ = "api"
        sys.modules["api"].rate_limit = fresh
        try:
            importlib.reload(fresh)
        except ImportError as exc:
            assert "not in sys.modules" in str(exc)
        else:
            raise AssertionError("reload should require a consistent entry")
    finally:
        restore_module_family(snapshot)


def test_absent_before_snapshot_is_removed_on_restore() -> None:
    name = "api.auth"
    sys.modules.pop(name, None)
    attr = getattr(sys.modules["api"], "auth", None)
    if attr is not None:
        delattr(sys.modules["api"], "auth")

    snapshot = snapshot_module_family([name])
    assert snapshot[name].entry is None
    assert snapshot[name].parent_attr is None

    importlib.import_module(name)  # reintroduces entry and package attribute
    restore_module_family(snapshot)

    assert name not in sys.modules
    assert not hasattr(sys.modules["api"], "auth")


def test_guard_reports_repaired_names() -> None:
    snapshot = snapshot_module_family(API_MODULE_FAMILY)
    sys.modules.pop("api", None)
    repaired = restore_module_family(snapshot)
    assert "api" in repaired
    assert sys.modules["api"] is snapshot["api"].entry


def test_guard_restores_identity_across_teardown_surgery(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The autouse guard — not the helpers — must clean up between tests.

    Runs an isolated two-test session: a polluter fixture pops the api
    package during teardown, then the next test exercises dotted-path
    patching and reload. With the real conftest guard loaded (via -p) both
    tests pass; the negative control (guard not loaded) proves this run
    would catch the guard being disabled.
    """
    monkeypatch.setenv("PYTHONPATH", str(_PROJECT_ROOT))
    pytester.makepyfile(_CROSS_TEST_PROBE)

    guarded = pytester.runpytest_subprocess("-p", "tests.conftest", "-q")
    guarded.assert_outcomes(passed=2)

    unguarded = pytester.runpytest_subprocess("-q")
    unguarded.assert_outcomes(passed=1, failed=1)
