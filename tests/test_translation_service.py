import os
import sys
import types

import pytest

# Pre-stub minimal 'mcp' package tree used by services.mcp_lingo_client to avoid external deps
if "mcp" not in sys.modules:
    mcp_pkg = types.ModuleType("mcp")
    sys.modules["mcp"] = mcp_pkg
    # Create submodules
    client_mod = types.ModuleType("mcp.client")
    session_mod = types.ModuleType("mcp.client.session")
    stdio_mod = types.ModuleType("mcp.client.stdio")
    types_mod = types.ModuleType("mcp.types")

    # Minimal dummies expected by imports
    class _Dummy:
        pass

    session_mod.ClientSession = _Dummy
    session_mod.SessionOptions = _Dummy
    stdio_mod.StdioServerParameters = _Dummy

    # Minimal callable placeholder
    def _stdio_client(*args, **kwargs):
        return None

    stdio_mod.stdio_client = _stdio_client
    types_mod.JSONRPCError = Exception

    sys.modules["mcp.client"] = client_mod
    sys.modules["mcp.client.session"] = session_mod
    sys.modules["mcp.client.stdio"] = stdio_mod
    sys.modules["mcp.types"] = types_mod

# Prefer package-relative imports; fallback to absolute for flat execution
try:
    from services.mcp_lingo_client import McpLingoConfig
    from services.translation_service import (
        LingoTranslator,
        MCPLingoTranslator,
        TranslationService,
    )
except Exception:  # pragma: no cover
    from mcp_lingo_client import McpLingoConfig
    from translation_service import (
        LingoTranslator,
        MCPLingoTranslator,
        TranslationService,
    )


@pytest.fixture(autouse=True)
def restore_env(monkeypatch):
    # Ensure we start with a clean env slate for Lingo-related vars per test
    for key in [
        "LINGO_API_KEY",
        "LINGO_USE_MCP",
        "LINGO_MCP_TOOL_NAME",
        "LINGO_MCP_STARTUP_TIMEOUT",
        "LINGO_MCP_CALL_TIMEOUT",
        "LINGO_MCP_SESSION_CLEANUP_TIMEOUT",
        "LINGO_MCP_STDIO_CLEANUP_TIMEOUT",
    ]:
        if key in os.environ:
            monkeypatch.delenv(key, raising=False)
    yield


def test_mcplingo_translator_requires_valid_config():
    # Missing config
    with pytest.raises(ValueError):
        MCPLingoTranslator(config=None)  # type: ignore[arg-type]

    # Missing api_key in config
    cfg = McpLingoConfig(api_key="")
    with pytest.raises(ValueError):
        MCPLingoTranslator(cfg)

    # Valid config should not raise
    ok = McpLingoConfig(api_key="test_key")
    t = MCPLingoTranslator(ok)
    assert isinstance(t, MCPLingoTranslator)


def test_translation_service_initializes_mcp_provider_with_config(monkeypatch):
    # Arrange MCP env
    monkeypatch.setenv("LINGO_API_KEY", "unit_test_key")
    monkeypatch.setenv("LINGO_USE_MCP", "true")
    monkeypatch.setenv("LINGO_MCP_TOOL_NAME", "translate")
    monkeypatch.setenv("LINGO_MCP_STARTUP_TIMEOUT", "12.5")
    monkeypatch.setenv("LINGO_MCP_CALL_TIMEOUT", "45.0")

    # Act
    svc = TranslationService()

    # Assert provider wiring
    assert "lingo" in svc.providers
    provider = svc.providers["lingo"]
    assert isinstance(provider, MCPLingoTranslator)

    # White-box: verify internal client config was constructed from env
    client = getattr(provider, "_client", None)
    assert client is not None
    cfg = getattr(client, "_config", None)
    assert cfg is not None

    assert cfg.api_key == "unit_test_key"
    assert cfg.tool_name == "translate"
    assert pytest.approx(cfg.startup_timeout_s, rel=1e-6) == 12.5
    assert pytest.approx(cfg.call_timeout_s, rel=1e-6) == 45.0

    # Ensure env passthrough was set (at least PATH should exist)
    assert isinstance(cfg.env, dict)
    assert "PATH" in cfg.env


def test_translation_service_initializes_rest_provider_when_mcp_disabled(monkeypatch):
    monkeypatch.setenv("LINGO_API_KEY", "unit_test_key")
    monkeypatch.setenv("LINGO_USE_MCP", "false")

    svc = TranslationService()

    assert "lingo" in svc.providers
    provider = svc.providers["lingo"]
    assert isinstance(provider, LingoTranslator)
    assert provider.api_key == "unit_test_key"
