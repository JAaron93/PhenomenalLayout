from dataclasses import dataclass
from typing import Any

import pytest

from services.mcp_lingo_client import McpLingoClient, McpLingoConfig


class FakeToolResult:
    def __init__(self, structured: Any = None, content: Any = None):
        self.structuredContent = structured
        self.content = content


@dataclass
class CallRecord:
    name: str
    arguments: dict


class FakeSession:
    def __init__(
        self, succeed_on_call: int = 1, result: FakeToolResult | None = None
    ):
        self.calls: list[CallRecord] = []
        self._succeed_on_call = succeed_on_call
        self._result = result or FakeToolResult(structured="ok")

    async def call_tool(self, name: str, arguments: dict):
        """Record the call and simulate success/failure.
        Succeeds on the Nth (1-indexed) call; raises Exception before that.
        """
        self.calls.append(CallRecord(name=name, arguments=arguments))
        if len(self.calls) < self._succeed_on_call:
            raise RuntimeError("simulated failure")
        return self._result


@pytest.fixture()
def make_client():
    def _make(succeed_on_call: int = 1):
        cfg = McpLingoConfig(api_key="dummy")
        client = McpLingoClient(cfg)
        # Inject fake session and tool name to avoid starting real MCP client
        client._session = FakeSession(succeed_on_call=succeed_on_call)  # type: ignore[attr-defined]
        client._tool_name = "translate"  # type: ignore[attr-defined]
        # Ensure no schema-driven special path interferes with shapes in tests
        client._tool_schema = None  # type: ignore[attr-defined]
        return client

    return _make



    client = make_client(succeed_on_call=2)  # force at least two attempts if needed
    # Call with only text
    result = await client._call_translate_tool(
        text="hi", source_lang="en", target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    # No attempted args should include 'texts'
    for rec in calls:
        assert "texts" not in rec.arguments
    # At least one attempt includes 'text'
    assert any("text" in rec.arguments for rec in calls)


@pytest.mark.asyncio
async def test_batch_texts_uses_only_texts_shapes(make_client):
    client = make_client(succeed_on_call=1)
    # Call with only texts
    result = await client._call_translate_tool(
        texts=["a", "b"], source_lang="en", target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    # No attempt should include 'text'
    for rec in calls:
        assert "text" not in rec.arguments
    # At least one attempt includes 'texts'
    assert any("texts" in rec.arguments for rec in calls)


@pytest.mark.asyncio
async def test_both_text_and_texts_prefers_batch(make_client, caplog):
    client = make_client(
        succeed_on_call=2
    )  # ensure we see more than one attempt if first fails
    # Provide both; should prefer batch mode (texts)
    result = await client._call_translate_tool(
        text="hi", texts=["a", "b"], source_lang="en", target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    for rec in calls:
        assert "texts" in rec.arguments
        assert "text" not in rec.arguments
        assert rec.name == "translate"
    # Optionally verify debug log message occurred (not strict)
    # assert any("preferring batch" in m.message.lower() for m in caplog.records)


@pytest.mark.asyncio
async def test_text_list_coerces_to_texts(make_client):
    client = make_client(succeed_on_call=1)
    # Provide text as a list; should coerce to texts (batch mode)
    result = await client._call_translate_tool(
        text=["a", "b"], texts=None, source_lang="en", target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    for rec in calls:
        assert "texts" in rec.arguments
        assert "text" not in rec.arguments


@pytest.mark.asyncio
async def test_neither_text_nor_texts_raises(make_client):
    client = make_client()
    with pytest.raises(ValueError, match="Must provide text or texts"):
        await client._call_translate_tool(source_lang="en", target_lang="de")


@pytest.mark.asyncio
async def test_prunes_none_language_fields(make_client):
    client = make_client(succeed_on_call=1)
    # source_lang is None, target_lang is set
    result = await client._call_translate_tool(
        text="hi", source_lang=None, target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    # Ensure no None-valued keys were included (i.e., no source keys at all)
    for rec in calls:
        keys = set(rec.arguments.keys())
        # No source-like keys present
        assert not (
            {"sourceLocale", "source_lang", "source", "from", "sourceLanguage"} & keys
        )
        # Target keys should remain
        assert {"targetLocale", "target_lang", "target", "to", "targetLanguage"} & keys


@pytest.mark.asyncio
async def test_min_attempts_only(make_client):
    # Configure stub to succeed on first valid attempt
    client = make_client(succeed_on_call=1)
    result = await client._call_translate_tool(
        text="hi", source_lang="en", target_lang="de"
    )
    assert isinstance(result, FakeToolResult)

    calls = client._session.calls  # type: ignore[attr-defined]
    # Should only call the tool once (no extra irrelevant attempts)
    assert len(calls) == 1
    # And that single attempt should be a single-text shape
    assert "text" in calls[0].arguments
    assert "texts" not in calls[0].arguments
