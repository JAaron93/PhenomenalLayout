from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

try:
    import mcp.types as types
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except Exception:  # pragma: no cover - optional dependency not present in tests
    ClientSession = object  # type: ignore
    StdioServerParameters = object  # type: ignore

    def stdio_client(*args, **kwargs):  # type: ignore
        raise RuntimeError("mcp package is not installed")

    class _DummyTypes:  # Minimal stand-ins for typing/instance checks
        class TextContent:
            def __init__(self, text: str = "") -> None:
                self.text = text

        class CallToolResult:
            def __init__(self) -> None:
                self.structuredContent = None
                self.content = None

    types = _DummyTypes()  # type: ignore

logger = logging.getLogger(__name__)


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of d without keys whose values are None.

    This is non-mutating and preserves insertion order for the remaining items.
    """
    return {k: v for k, v in d.items() if v is not None}


def _dedupe_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable-deduplicate dictionaries by a robust signature.

    The signature combines the sorted key set and a tuple of (key, type(value))
    pairs to avoid collisions between similarly-shaped payloads that differ only
    by value types. The first occurrence is preserved (stable).
    """
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for a in attempts:
        keys_sorted = sorted(a.keys())
        type_signature = tuple((k, type(a[k])) for k in keys_sorted)
        sig = (tuple(keys_sorted), type_signature)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(a)
    return out


DEFAULT_TOOL_CANDIDATES: tuple[str, ...] = (
    "translate",
    "localize",
    "localizeText",
    "localize_object",
    "localizeObject",
)


@dataclass
class McpLingoConfig:
    """Configuration for the Lingo.dev MCP client."""
    api_key: str
    command: str = "npx"
    # npx -y lingo.dev mcp <api-key>
    args: Sequence[str] = ("-y", "lingo.dev", "mcp")
    env: Optional[dict[str, str]] = None
    # Tool discovery/override
    tool_name: Optional[str] = None
    # Timeout for startup and calls
    startup_timeout_s: float = float(os.environ.get("LINGO_MCP_STARTUP_TIMEOUT", 20))
    call_timeout_s: float = float(os.environ.get("LINGO_MCP_CALL_TIMEOUT", 60))
    # Timeout for cleanup operations
    session_cleanup_timeout_s: float = float(
        os.environ.get("LINGO_MCP_SESSION_CLEANUP_TIMEOUT", 10)
    )
    stdio_cleanup_timeout_s: float = float(
        os.environ.get("LINGO_MCP_STDIO_CLEANUP_TIMEOUT", 10)
    )


class McpLingoClient:
    """Thin wrapper that launches the Lingo.dev MCP server via stdio and exposes
    convenience methods to call its translation tool.

    Usage:
        client = McpLingoClient(McpLingoConfig(api_key=...))
        await client.start()
        translated = await client.translate_text("Hello", source_lang="en", target_lang="de")
        await client.stop()
    """

    def __init__(self, config: McpLingoConfig):
        self._config = config
        self._stdio_ctx: Optional[asyncio.AbstractAsyncContextManager] = None
        self._session_ctx: Optional[asyncio.AbstractAsyncContextManager] = None
        self._session: Optional[ClientSession] = None
        self._tool_name: Optional[str] = None
        self._tool_schema: Optional[dict[str, Any]] = None

    async def start(self) -> None:
        if self._session is not None:
            return

        # Ensure we inherit the user's environment so that npx/node are on PATH
        inherited_env = os.environ.copy()
        if self._config.env:
            inherited_env.update(self._config.env)

        server_params = StdioServerParameters(
            command=self._config.command,
            args=[*self._config.args, self._config.api_key],
            env=inherited_env,
        )

        # Establish stdio client connection and MCP session
        logger.info(
            "Starting Lingo MCP stdio client via %s %s",
            self._config.command,
            " ".join(server_params.args),
        )
        self._stdio_ctx = stdio_client(server_params)
        read, write = await asyncio.wait_for(
            self._stdio_ctx.__aenter__(), timeout=self._config.startup_timeout_s
        )

        self._session_ctx = ClientSession(read, write)
        self._session = await self._session_ctx.__aenter__()
        await asyncio.wait_for(
            self._session.initialize(), timeout=self._config.startup_timeout_s
        )
        logger.info("Lingo MCP session initialized")

        # Discover tool name if not provided
        await self._discover_tool_name()

    async def stop(self) -> None:
        """Close session and underlying stdio transport with enhanced cleanup."""
        logger.info("Starting MCP client shutdown")
        cleanup_errors = []

        # Close session and underlying stdio transport
        if self._session is not None and self._session_ctx is not None:
            try:
                logger.debug("Closing MCP session")
                await asyncio.wait_for(
                    self._session_ctx.__aexit__(None, None, None),
                    timeout=self._config.session_cleanup_timeout_s
                )
                logger.debug("MCP session closed successfully")
            except TimeoutError:
                cleanup_errors.append("Session cleanup timeout")
                logger.warning("MCP session cleanup timed out")
            except Exception as e:
                cleanup_errors.append(f"Session cleanup error: {e}")
                logger.exception("Failed to close MCP session")
            finally:
                self._session = None
                self._session_ctx = None

        if self._stdio_ctx is not None:
            try:
                logger.debug("Closing stdio transport")
                await asyncio.wait_for(
                    self._stdio_ctx.__aexit__(None, None, None),
                    timeout=self._config.stdio_cleanup_timeout_s
                )
                logger.debug("Stdio transport closed successfully")
            except TimeoutError:
                cleanup_errors.append("Stdio cleanup timeout")
                logger.warning("Stdio transport cleanup timed out")
            except Exception as e:
                cleanup_errors.append(f"Stdio cleanup error: {e}")
                logger.exception("Failed to close stdio transport")
            finally:
                self._stdio_ctx = None

        # Log cleanup summary
        if cleanup_errors:
            logger.warning(
                "MCP client completed with %d cleanup errors: %s",
                len(cleanup_errors), "; ".join(cleanup_errors)
            )
        else:
            logger.info("MCP client shutdown completed successfully")

        # Clear tool discovery cache
        self._tool_name = None
        self._tool_schema = None

    async def _discover_tool_name(self) -> None:
        if self._session is None:
            raise RuntimeError("MCP session not started")
        if self._config.tool_name:
            self._tool_name = self._config.tool_name
            return

        tools = await self._session.list_tools()
        available = [t.name for t in tools.tools]
        logger.info("Lingo MCP available tools: %s", available)
        # Prefer common names
        for candidate in DEFAULT_TOOL_CANDIDATES:
            if candidate in available:
                self._tool_name = candidate
                # capture schema
                for t in tools.tools:
                    if t.name == candidate:
                        # inputSchema is a JSONSchema; convert to dict for logging
                        try:
                            self._tool_schema = getattr(t, "inputSchema", None)
                            if self._tool_schema is not None:
                                # mcp.types may wrap schema; attempt to get underlying
                                schema_dict = (
                                    self._tool_schema
                                    if isinstance(self._tool_schema, dict)
                                    else getattr(self._tool_schema, "schema", None)
                                )
                                logger.info(
                                    "Lingo MCP tool schema (truncated): %s",
                                    str(schema_dict)[:512],
                                )
                        except Exception:
                            pass
                        break
                logger.info("Lingo MCP selected tool: %s", self._tool_name)
                return
        # Fallback: if a single tool exists, use it
        if len(available) == 1:
            self._tool_name = available[0]
            # capture schema
            for t in tools.tools:
                if t.name == self._tool_name:
                    try:
                        self._tool_schema = getattr(t, "inputSchema", None)
                        schema_dict = (
                            self._tool_schema
                            if isinstance(self._tool_schema, dict)
                            else getattr(self._tool_schema, "schema", None)
                        )
                        logger.info(
                            "Lingo MCP tool schema (truncated): %s",
                            str(schema_dict)[:512],
                        )
                    except Exception:
                        pass
                    break
            logger.info("Lingo MCP selected sole tool: %s", self._tool_name)
            return
        raise RuntimeError(
            f"Unable to determine Lingo MCP translation tool. Available tools: {available}. "
            f"Set LINGO_MCP_TOOL_NAME to override."
        )

    async def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        if not text:
            return ""
        # Try a few times in case of transient server errors
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                result = await self._call_translate_tool(
                    text=text, source_lang=source_lang, target_lang=target_lang
                )
                return self._extract_text(result, fallback=text)
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.error("MCP Lingo translate_text error: %s", e)
        return text

    async def translate_batch(
        self, texts: Sequence[str], source_lang: str, target_lang: str
    ) -> list[str]:
        if not texts:
            return []
        # Call once if tool supports batch; otherwise call per-item
        try:
            result = await self._call_translate_tool(
                texts=list(texts), source_lang=source_lang, target_lang=target_lang
            )
            structured = getattr(result, "structuredContent", None)
            if isinstance(structured, list) and all(
                isinstance(x, str) for x in structured
            ):
                return list(structured)
        except Exception as e:
            # Log the exception before falling back to per-item calls to aid debugging
            logger.warning(
                "MCP Lingo translate_batch batch call failed; falling back to per-item calls: %s",
                e,
            )
            # Fall back to per-item calls
            pass

        out: list[str] = []
        for t in texts:
            translated = await self.translate_text(t, source_lang, target_lang)
            out.append(translated)
        return out

    def _normalize_lang(self, lang: Optional[str]) -> Optional[str]:
        if lang is None:
            return None
        return lang.strip().lower()

    def _normalize_locale(self, lang: Optional[str]) -> Optional[str]:
        """Return a best-effort BCP-47 code for the MCP tool.

        Accepts inputs like 'english', 'en', 'en-us', 'EN_us', 'German', etc.
        """
        if not lang:
            return None
        l = lang.strip().lower()
        # Common language-name to code mapping
        name_map = {
            "english": "en",
            "deutsch": "de",
            "german": "de",
            "français": "fr",
            "french": "fr",
            "español": "es",
            "spanish": "es",
            "italian": "it",
            "italiano": "it",
            "portuguese": "pt",
            "português": "pt",
            "japanese": "ja",
            "日本語": "ja",
            "chinese": "zh",
            "中文": "zh",
        }
        if l in name_map:
            return name_map[l]
        # Normalize underscore to hyphen and casing like en-us -> en-US
        l = l.replace("_", "-")
        parts = l.split("-")
        if len(parts) == 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
            return f"{parts[0]}-{parts[1].upper()}"
        # Fallback: use two-letter code if available
        if len(l) >= 2:
            return l[:2]
        return l

    def _filter_args_by_schema(self, args: dict[str, Any]) -> dict[str, Any]:
        """Filter a payload to only include keys declared in the tool schema.

        If no schema is available or parsing fails, the original args are
        returned unchanged.
        """
        if not self._tool_schema:
            return args
        try:
            schema = (
                self._tool_schema
                if isinstance(self._tool_schema, dict)
                else getattr(self._tool_schema, "schema", None)
            ) or {}
            props = set((schema.get("properties") or {}).keys())
            if not props:
                return args
            return {k: v for k, v in args.items() if k in props}
        except Exception:
            return args

    @staticmethod
    def _build_translate_arg_attempts(
        *,
        text: str | None,
        texts: list[str] | None,
        target: str | None,
        source: str | None,
    ) -> list[dict[str, object]]:
        """Build a list of argument shapes for translate/localize tools.

        Behavior:
        - Determines single vs batch mode (based on provided payloads)
        - Normalizes list provided via `text` into `texts` for batch mode
        - Uses current set of supported key synonyms for payload and language fields
        - Drops None values and deduplicates by key+type signature to reduce retries

        Supported shapes (preserve order; earlier are attempted first):
        Single-text payloads:
        - {text, sourceLocale, targetLocale}
        - {text, source_lang, target_lang}
        - {text, source, target}
        - {text, from, to}
        - {text, sourceLanguage, targetLanguage}

        Batch payloads:
        - {texts, sourceLocale, targetLocale}
        - {texts, source_lang, target_lang}
        - {texts, source, target}
        - {texts, from, to}
        - {texts, sourceLanguage, targetLanguage}
        - {inputs, source, target}
        - {inputs, from, to}
        - {inputs, sourceLocale, targetLocale}

        Developer note: Adding new shapes
        - Only add shapes that have been observed in upstream tool schemas to avoid
          unnecessary retries.
        - Add new dict templates to the appropriate "single_shapes_templates" or
          "batch_shapes_templates" lists below, keeping more common shapes earlier.
        - Update/extend tests in tests/services/test_mcp_lingo_client.py to cover
          the new permutations to ensure stable behavior.
        - Prefer introducing new synonyms rather than removing existing ones to
          maintain backward compatibility.
        """
        # Determine mode
        mode = (
            "batch"
            if (texts and len(texts) > 0) or isinstance(text, list)
            else "single"
        )

        # Normalize list provided as `text` for batch mode
        if mode == "batch" and not texts and isinstance(text, list):
            texts = list(text)
            text = None

        # Define templates using existing synonyms (preserve current ones)
        single_shapes_templates: list[dict[str, object]] = [
            {"text": None, "sourceLocale": None, "targetLocale": None},
            {"text": None, "source_lang": None, "target_lang": None},
            {"text": None, "source": None, "target": None},
            {"text": None, "from": None, "to": None},
            {"text": None, "sourceLanguage": None, "targetLanguage": None},
        ]

        batch_shapes_templates: list[dict[str, object]] = [
            {"texts": None, "sourceLocale": None, "targetLocale": None},
            {"texts": None, "source_lang": None, "target_lang": None},
            {"texts": None, "source": None, "target": None},
            {"texts": None, "from": None, "to": None},
            {"texts": None, "sourceLanguage": None, "targetLanguage": None},
            # Some tools expect "inputs" instead of texts (preserve exact permutations used)
            {"inputs": None, "source": None, "target": None},
            {"inputs": None, "from": None, "to": None},
            {"inputs": None, "sourceLocale": None, "targetLocale": None},
        ]

        templates = (
            batch_shapes_templates if mode == "batch" else single_shapes_templates
        )

        attempts: list[dict[str, object]] = []
        seen_key_sets: set[tuple[str, ...]] = set()

        for tpl in templates:
            attempt: dict[str, object] = dict(tpl)
            # Fill payload
            if "text" in attempt:
                attempt["text"] = text  # type: ignore[assignment]
            if "texts" in attempt:
                attempt["texts"] = texts  # type: ignore[assignment]
            if "inputs" in attempt:
                attempt["inputs"] = texts  # type: ignore[assignment]
            # Fill languages
            if "targetLocale" in attempt:
                attempt["targetLocale"] = target  # type: ignore[assignment]
            if "sourceLocale" in attempt:
                attempt["sourceLocale"] = source  # type: ignore[assignment]
            if "target_lang" in attempt:
                attempt["target_lang"] = target  # type: ignore[assignment]
            if "source_lang" in attempt:
                attempt["source_lang"] = source  # type: ignore[assignment]
            if "target" in attempt:
                attempt["target"] = target  # type: ignore[assignment]
            if "source" in attempt:
                attempt["source"] = source  # type: ignore[assignment]
            if "to" in attempt:
                attempt["to"] = target  # type: ignore[assignment]
            if "from" in attempt:
                attempt["from"] = source  # type: ignore[assignment]
            if "targetLanguage" in attempt:
                attempt["targetLanguage"] = target  # type: ignore[assignment]
            if "sourceLanguage" in attempt:
                attempt["sourceLanguage"] = source  # type: ignore[assignment]

            # Drop None values
            attempt = _drop_none(attempt)
            if not attempt:
                continue

            # Deduplicate by key tuple (legacy guard within the loop)
            key_tuple = tuple(sorted(attempt.keys()))
            if key_tuple in seen_key_sets:
                continue
            seen_key_sets.add(key_tuple)
            attempts.append(attempt)

        # Final robust stable-deduplication using key+type signature
        return _dedupe_attempts(attempts)

    async def _call_translate_tool(self, **kwargs: Any) -> types.CallToolResult:
        """Call the resolved translation tool with smart argument shaping.

        Mode selection and precedence:
        - Batch mode is used when a non-empty "texts" (list/tuple) is provided.
        - Single mode is used when a non-empty string "text" is provided.
        - If both are provided, batch mode takes precedence and "text" is ignored.
        - If "text" is a list/tuple and "texts" is not provided, it is coerced to
          batch mode by moving the list into "texts".
        - If neither payload is provided, a ValueError is raised.

        Schema-aware fast path (single mode only):
        - If the discovered tool schema indicates properties/requirements compatible
          with {text, targetLocale}, the method will attempt a single, exact schema-
          aligned call before falling back to the generic permutation attempts.

        Generic attempts:
        - Builds a list of payload permutations using _build_translate_arg_attempts,
          preserving the project’s known synonyms for keys like source/target and
          text/texts/inputs.
        - None-valued fields are dropped, arguments are filtered by the tool schema
          when available, and attempts are stable-deduplicated to minimize retries.
        """
        if self._session is None or self._tool_name is None:
            raise RuntimeError("MCP client not started or tool not resolved")

        src = self._normalize_lang(kwargs.get("source_lang"))
        tgt = self._normalize_locale(kwargs.get("target_lang"))
        text = kwargs.get("text")
        texts = kwargs.get("texts")

        # Determine desired mode and coerce inputs per semantics:
        # - If texts (list of strings) is provided (non-empty), use batch mode
        # - Else if text (string) is provided, use single mode
        # - If both are provided, prefer batch mode and log debug warning
        # - If text is a list and texts is None, coerce to batch mode (texts=text)
        # - If neither provided, raise ValueError("Must provide text or texts")
        use_batch: bool
        # Coerce list passed as `text` into `texts`
        if texts is None and isinstance(text, (list, tuple)):
            texts = list(text)
            text = None
            logger.debug("Coerced list provided as 'text' into 'texts' for batch mode")

        has_texts = isinstance(texts, (list, tuple)) and len(texts) > 0
        has_text = isinstance(text, str) and len(text.strip()) > 0

        if has_texts and has_text:
            logger.debug(
                "Both 'text' and 'texts' provided; preferring batch mode with 'texts'"
            )
            use_batch = True
            # Ensure we don't accidentally use single payload key later
            text = None
        elif has_texts:
            use_batch = True
        elif has_text:
            use_batch = False
        else:
            raise ValueError("Must provide text or texts")

        logger.debug("Translate call mode=%s", "batch" if use_batch else "single")

        # If schema explicitly requires text and targetLocale, construct exactly that
        # Only attempt this path for single mode to avoid wrong payload keys.
        if self._tool_schema and not use_batch:
            try:
                schema = (
                    self._tool_schema
                    if isinstance(self._tool_schema, dict)
                    else getattr(self._tool_schema, "schema", None)
                ) or {}
                req = set(schema.get("required") or [])
                props = set((schema.get("properties") or {}).keys())
                if {"text", "targetLocale"}.issubset(req | props):
                    if text is None or text == "":
                        # Do not call the tool with empty text
                        raise RuntimeError("translate_text called with empty text")
                    filtered = {"text": text, "targetLocale": tgt}
                    filtered = self._filter_args_by_schema(filtered)
                    call = self._session.call_tool(self._tool_name, arguments=filtered)
                    return await asyncio.wait_for(
                        call, timeout=self._config.call_timeout_s
                    )
            except Exception:
                # Fall back to generic attempts below
                pass

        # Build argument attempts using helper to preserve project synonyms
        arg_attempts = self._build_translate_arg_attempts(
            text=text if not use_batch else None,
            texts=list(texts)
            if use_batch and isinstance(texts, (list, tuple))
            else (texts if use_batch else None),
            target=tgt,
            source=src,
        )

        # Debug: number of attempts and the sanitized key sets for observability
        try:
            key_sets = [sorted(a.keys()) for a in arg_attempts]
            logger.debug(
                "Translate arg attempts: count=%d, key_sets=%s",
                len(arg_attempts),
                key_sets,
            )
        except Exception:
            # Never fail due to logging
            pass

        last_err: Optional[Exception] = None
        errors: list[Exception] = []
        attempt_index = 0
        for args in arg_attempts:
            attempt_index += 1
            # Remove None values
            args = _drop_none(args)
            if not args:
                continue
            try:
                filtered = self._filter_args_by_schema(args)
                # Structured logging for observability
                try:
                    logger.info(
                        "mcp_translate_attempt",
                        extra={
                            "event": "mcp_translate_attempt",
                            "tool": self._tool_name,
                            "mode": "batch" if use_batch else "single",
                            "attempt": attempt_index,
                            "keys": sorted(filtered.keys()),
                        },
                    )
                except Exception:
                    pass
                call = self._session.call_tool(self._tool_name, arguments=filtered)
                result = await asyncio.wait_for(
                    call, timeout=self._config.call_timeout_s
                )
                try:
                    logger.info(
                        "mcp_translate_success",
                        extra={
                            "event": "mcp_translate_success",
                            "tool": self._tool_name,
                            "mode": "batch" if use_batch else "single",
                            "attempt": attempt_index,
                            "keys": sorted(filtered.keys()),
                        },
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                errors.append(e)
                last_err = e
                try:
                    logger.warning(
                        "mcp_translate_failure",
                        extra={
                            "event": "mcp_translate_failure",
                            "tool": self._tool_name,
                            "mode": "batch" if use_batch else "single",
                            "attempt": attempt_index,
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                    )
                except Exception:
                    pass
                continue
        # If we get here, all attempts failed
        attempted_key_sets = []
        try:
            attempted_key_sets = [sorted(a.keys()) for a in arg_attempts]
        except Exception:
            attempted_key_sets = []
        error_summaries = "; ".join(f"{type(e).__name__}: {e}" for e in errors)
        raise RuntimeError(
            f"Failed calling MCP tool '{self._tool_name}' after {len(arg_attempts)} attempts. "
            f"Tried key sets={attempted_key_sets}. Errors: {error_summaries}"
        ) from last_err

    @staticmethod
    def _extract_text(result: types.CallToolResult, fallback: str) -> str:
        # Prefer structured content if it is a string
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, str):
            txt = structured
        else:
            # Otherwise parse the first text content block
            content = getattr(result, "content", None)
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, types.TextContent):
                        txt = block.text
                        break
                else:
                    return fallback
            else:
                return fallback

        lowered = txt.lower()
        if "internal server error" in lowered or lowered.startswith(
            "server error (500)"
        ):
            # Treat as a failed call, do not inject into output
            raise RuntimeError("MCP returned server error text")
        return txt
