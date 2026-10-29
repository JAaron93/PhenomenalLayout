"""Tests for validated filesystem path construction helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.path_safety import (
    resolve_managed_path,
    resolve_managed_path_or_none,
    resolve_within,
    safe_component,
)


class TestSafeComponent:
    def test_preserves_safe_identifiers(self) -> None:
        assert safe_component("user_123") == "user_123"
        assert safe_component("translator-01") == "translator-01"

    def test_maps_legacy_sanitized_characters(self) -> None:
        assert safe_component("user@example.com") == "user_example_com"
        assert safe_component("a/b\\c:d") == "a_b_c_d"

    def test_rejects_empty_identifier(self) -> None:
        with pytest.raises(ValueError, match="path component"):
            safe_component("   ")

    def test_truncates_long_identifiers(self) -> None:
        assert len(safe_component("x" * 500)) == 128


class TestResolveWithin:
    def test_joins_beneath_base(self, tmp_path: Path) -> None:
        base_real = Path(os.path.realpath(tmp_path))
        result = resolve_within(tmp_path, "user_1.json")
        assert result.parent == base_real

    def test_multiple_components_join_in_order(self, tmp_path: Path) -> None:
        base_real = Path(os.path.realpath(tmp_path))
        result = resolve_within(tmp_path, "sub", "file.json")
        assert result.parent == base_real / "sub"

    def test_rejects_traversal_components(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsafe path component"):
            resolve_within(tmp_path, "../../etc/passwd")

    def test_rejects_dot_components(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsafe path component"):
            resolve_within(tmp_path, "..")

    def test_rejects_symlink_escape(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "path-safety-outside-target"
        outside.mkdir(exist_ok=True)
        try:
            (tmp_path / "link").symlink_to(outside)
            with pytest.raises(ValueError, match="escapes base directory"):
                resolve_within(tmp_path, "link", "x.json")
        finally:
            outside.rmdir()

    def test_rejects_empty_components(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "  ")

    def test_accepts_extension_bearing_filenames(self, tmp_path: Path) -> None:
        result = resolve_within(tmp_path, "translator-01_klages_1929.json")
        assert result.name == "translator-01_klages_1929.json"


class TestResolveManagedPath:
    def test_accepts_temp_dir_files(self, tmp_path: Path) -> None:
        probe = tmp_path / "doc.pdf"
        probe.write_bytes(b"%PDF-1.4")
        assert resolve_managed_path(probe) == Path(os.path.realpath(probe))

    def test_accepts_managed_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "uploads").mkdir()
        probe = tmp_path / "uploads" / "doc.pdf"
        probe.write_bytes(b"%PDF-1.4")
        assert resolve_managed_path("uploads/doc.pdf") == Path(os.path.realpath(probe))

    def test_rejects_outside_paths(self) -> None:
        with pytest.raises(ValueError, match="outside managed storage"):
            resolve_managed_path("/etc/hostname")

    def test_resolves_symlink_to_outside_target_as_outside(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "escalate.pdf").symlink_to("/etc/hostname")
        with pytest.raises(ValueError, match="outside managed storage"):
            resolve_managed_path(tmp_path / "escalate.pdf")

    def test_or_none_returns_none_outside(self) -> None:
        assert resolve_managed_path_or_none("/etc/hostname") is None

    def test_or_none_returns_path_inside_temp(self, tmp_path: Path) -> None:
        probe = tmp_path / "x.pdf"
        probe.write_bytes(b"x")
        assert resolve_managed_path_or_none(probe) is not None

    def test_gradio_temp_dir_env_is_honored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GRADIO_TEMP_DIR", str(tmp_path / "gradio-custom"))
        (tmp_path / "gradio-custom").mkdir()
        probe = tmp_path / "gradio-custom" / "doc.pdf"
        probe.write_bytes(b"%PDF-1.4")
        assert resolve_managed_path(probe) == Path(os.path.realpath(probe))
