"""Eradication regression net: the Lingo.dev translation stack is GONE.

Negative-sweep assertions for the Lingo eradication (ADR 0004, Track C
T-3.1 red phase — later extended by the T-4.1 pollution net in Track D).
The suite fails until the legacy modules, package export, scripts, test
modules, conftest fixtures, and examples are deleted — that failing state
is the Track C TDD red gate.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT: Path = Path(__file__).resolve().parents[1]

#: The four Lingo-era service modules (T-3.1 deletion list).
_LEGACY_MODULES: tuple[str, ...] = (
    "services.translation_service",
    "services.mcp_lingo_client",
    "services.parallel_translation_service",
    "services.enhanced_translation_service",
)

#: Legacy artifacts deleted under T-3.1 (scripts, tests, examples).
_LEGACY_FILES: tuple[str, ...] = (
    "services/translation_service.py",
    "services/mcp_lingo_client.py",
    "services/parallel_translation_service.py",
    "services/enhanced_translation_service.py",
    "scripts/verify/verify_mcp_timeout_configuration.py",
    "examples/mcp_demo_file.txt",
    "examples/parallel_translation_demo.py",
    "examples/neologism_integration_example.py",
    "tests/test_lingo_translator.py",
    "tests/test_translation_service.py",
    "tests/test_parallel_translation.py",
    "tests/services/test_mcp_lingo_client.py",
)


class TestLingoModulesDeleted:
    """The four Lingo-era service modules must be gone (T-3.1)."""

    @pytest.mark.parametrize("module_name", _LEGACY_MODULES)
    def test_legacy_module_is_gone(self, module_name: str) -> None:
        """Importing a Lingo-era module must raise ModuleNotFoundError."""
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)
        assert importlib.util.find_spec(module_name) is None


class TestLegacyArtifactsDeleted:
    """Legacy scripts, test modules, and examples must not exist."""

    @pytest.mark.parametrize("relative_path", _LEGACY_FILES)
    def test_legacy_artifact_absent(self, relative_path: str) -> None:
        """A Lingo-era artifact must not exist on disk."""
        assert not (REPO_ROOT / relative_path).exists()


class TestPackageExportRemoved:
    """The deferred additive-then-remove export block (T-1.4 → T-3.1)."""

    def test_services_package_no_longer_exports_translation_service(self) -> None:
        """``services`` no longer carries the TranslationService surface."""
        sys.modules.pop("services", None)
        import services as services_pkg

        assert not hasattr(services_pkg, "TranslationService")
        exported = set(getattr(services_pkg, "__all__", []))
        assert "TranslationService" not in exported
        assert "TRANSLATION_SERVICE_AVAILABLE" not in exported

    def test_philosophy_service_has_no_legacy_delegation_shim(self) -> None:
        """The philosophy service carries no legacy delegation typing shim.

        Track B retained a ``from .translation_service import ...`` typing
        shim to keep delegation annotations happy; with the module deleted
        the shim is dead weight (mypy flags it as an unused ignore), so
        T-3.1 removes both the shim and its stale docstring mention.
        """
        philosophy_path = REPO_ROOT / "services" / "philosophy_enhanced_translation_service.py"
        text = philosophy_path.read_text(encoding="utf-8")
        assert "from .translation_service import" not in text
        assert "TranslationService = None" not in text
        assert "wraps the existing TranslationService" not in text


class TestConftestLingoEradicated:
    """The conftest ``lingo_translator`` fixture + mock-key block is gone."""

    def test_conftest_has_no_lingo_references(self) -> None:
        """tests/conftest.py carries zero Lingo-era references."""
        text = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert (
            "lingo" not in text.lower()
        ), "conftest still references the Lingo stack (fixture/mock-key block)"


class TestConfigurationEradication:
    """LINGO-era configuration tokens are eradicated from all surfaces (T-3.3)."""

    _SURFACES: ClassVar[dict[str, Path]] = {
        ".env.example": REPO_ROOT / ".env.example",
        "config/settings.py": REPO_ROOT / "config" / "settings.py",
        "app.py": REPO_ROOT / "app.py",
        "scripts/run_tests_with_env.py": REPO_ROOT
        / "scripts"
        / "run_tests_with_env.py",
        "tests/test_deployment_config.py": REPO_ROOT
        / "tests"
        / "test_deployment_config.py",
    }

    @pytest.mark.parametrize(
        "surface", sorted(_SURFACES.keys())
    )
    def test_surface_has_no_lingo_tokens(self, surface: str) -> None:
        """Configuration surfaces must not carry LINGO-era env tokens."""
        text = self._SURFACES[surface].read_text(encoding="utf-8")
        assert "lingo" not in text.lower(), f"{surface} still references the Lingo stack"


class TestDependencyPrune:
    """The Lingo MCP SDK is pruned from runtime manifests (T-3.2)."""

    def test_requirements_in_has_no_mcp_sdk(self) -> None:
        """``requirements.in`` carries no Lingo MCP SDK dependency."""
        text = (REPO_ROOT / "requirements.in").read_text(encoding="utf-8")
        mcp_lines = [
            line for line in text.splitlines() if line.lstrip().startswith("mcp")
        ]
        assert not mcp_lines, f"stale MCP SDK lines: {mcp_lines!r}"

    def test_requirements_txt_has_no_mcp_sdk(self) -> None:
        """Regenerated ``requirements.txt`` carries no Lingo MCP SDK entry."""
        text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        mcp_lines = [
            line for line in text.splitlines() if line.lstrip().startswith("mcp")
        ]
        assert not mcp_lines, f"stale MCP SDK lines: {mcp_lines!r}"

    def test_pyproject_manifest_is_gcp_only(self) -> None:
        """``pyproject.toml`` no longer advertises the Lingo stack."""
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "Lingo.dev" not in text
        assert "mcp fallbacks" not in text

    def test_requirements_keep_fastapi_runtime_multipart(self) -> None:
        """FastAPI form routes need ``python-multipart`` installed explicitly.

        The legacy Lingo MCP SDK carried ``python-multipart`` transitively;
        once the SDK is pruned the app's own ``UploadFile``/``Form`` routes
        (api/routes.py) need it declared or route registration fails on a
        fresh install.
        """
        text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert "python-multipart==" in text
        source = (REPO_ROOT / "requirements.in").read_text(encoding="utf-8")
        assert "python-multipart" in source
