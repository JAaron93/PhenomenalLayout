import io
import logging
import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.helpers import restore_module_family, snapshot_module_family


# ---------------------------------------------------------------------------
# Shared PDF test-fixture factory (reportlab-free)
# ---------------------------------------------------------------------------

def build_test_pdf(pages: list[str]) -> bytes:
    """Build a minimal valid PDF with extractable text — no reportlab, no Pillow.

    Produces a PDF 1.4 document using Helvetica Type1 with WinAnsiEncoding
    (``cp1252``). ``pypdf.page.extract_text()`` can recover the original strings
    verbatim for all characters in the cp1252 / WinAnsiEncoding range, which
    includes ASCII, Western European characters, and the Windows-1252 extension
    block (positions 0x80–0x9F) — e.g. ``€`` (U+20AC), curly quotes
    (U+2018/U+2019/U+201C/U+201D), en dash (U+2013), and em dash (U+2014).

    .. note::
        Page text is encoded with ``cp1252`` (Windows-1252), **not** ``latin-1``
        (ISO-8859-1). The two codecs share the 0x00–0x7F and 0xA0–0xFF ranges
        but differ in 0x80–0x9F: latin-1 maps those bytes to C1 control
        characters, while cp1252 maps them to printable symbols (``€``, curly
        quotes, dashes, etc.). Pass only characters in the cp1252 code page;
        anything outside it raises ``UnicodeEncodeError``.

    This helper replaces ``reportlab.pdfgen.canvas.Canvas`` across the test
    suite (ADR 0002 / PR #147). Use it in place of any ``_create_*_pdf``
    local helper that previously imported from ``reportlab``.

    Args:
        pages: One string per page; each string is embedded as a single text
            run at position (72, 720) in a 612×792 pt (US Letter) media box.
            Newlines within a string are replaced with a space for simplicity —
            split multi-paragraph content into separate list items if exact
            page-break placement matters.

    Returns:
        Raw PDF bytes suitable for passing to any service or fixture that
        accepts ``bytes | BinaryIO | Path``.

    Example::

        pdf = build_test_pdf(["Seite 1: Einleitung", "Seite 2: Hauptteil"])
        result = orchestrator.pre_scan_book(user_id="u1", source=pdf)
    """
    buf = io.BytesIO()
    xrefs: dict[int, int] = {}

    def _w(data: bytes | str) -> None:
        buf.write(data.encode("latin-1") if isinstance(data, str) else data)

    def _start(n: int) -> None:
        xrefs[n] = buf.tell()
        _w(f"{n} 0 obj\n")

    def _end() -> None:
        _w("endobj\n")

    _w("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    n = len(pages)
    # Object layout (1-indexed):
    #   1          — Catalog
    #   2          — Pages root
    #   3          — Helvetica font
    #   4..3+n     — Content streams (one per page)
    #   4+n..3+2n  — Page dictionaries
    content_base = 4
    page_base = 4 + n

    # 1: Catalog
    _start(1)
    _w("<< /Type /Catalog /Pages 2 0 R >>\n")
    _end()

    # 2: Pages root
    kids = " ".join(f"{page_base + i} 0 R" for i in range(n))
    _start(2)
    _w(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>\n")
    _end()

    # 3: Font (standard Type1, WinAnsiEncoding — covers ASCII + Western European)
    _start(3)
    _w("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
       "/Encoding /WinAnsiEncoding >>\n")
    _end()

    # 4..3+n: Content streams
    for i, text in enumerate(pages):
        safe = (
            text.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .replace("\r", " ")
                .replace("\n", " ")
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("cp1252")
        _start(content_base + i)
        _w(f"<< /Length {len(stream)} >>\nstream\n")
        buf.write(stream)
        _w("\nendstream\n")
        _end()

    # 4+n..3+2n: Page dictionaries
    for i in range(n):
        _start(page_base + i)
        _w(
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_base + i} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>\n"
        )
        _end()

    # Cross-reference table
    xref_pos = buf.tell()
    total = 3 + 2 * n  # catalog + pages root + font + n streams + n page dicts
    _w(f"xref\n0 {total + 1}\n")
    _w("0000000000 65535 f \n")
    for i in range(1, total + 1):
        _w(f"{xrefs[i]:010d} 00000 n \n")
    _w(f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n")

    return buf.getvalue()

pytest_plugins: tuple[str, ...] = ("pytest_asyncio", "pytester")

logger = logging.getLogger(__name__)

# Modules to reload in dependency order (base → dependent)
# Order matters: auth → rate_limit → memory_routes → app
_RELOAD_MODULE_NAMES = [
    "api.auth",
    "api.rate_limit",
    "api.memory_routes",
    "app",
]


@pytest.fixture(autouse=True)
def _module_family_identity_guard() -> Iterator[None]:
    """Restore api/app module identity after every test.

    Several test files perform ad-hoc sys.modules surgery (pop/del/re-import)
    to re-execute modules under patched environments. When the ``api``
    package is popped, its next import creates a package object with no
    submodule attributes (api/__init__.py imports none), so
    ``monkeypatch.setattr("api.rate_limit.time", ...)`` raises AttributeError,
    and ``importlib.reload(api.rate_limit)`` raises ImportError when the
    sys.modules entry and the package attribute point to different module
    objects. Restoring identity after each test makes those order-dependent
    failures impossible regardless of fixture ordering or xdist scheduling.

    This restores object identity only; in-place reload mutations are the
    responsibility of each fixture's own reload-after-patch-exit teardown.
    """
    snapshot = snapshot_module_family()
    yield
    for name in restore_module_family(snapshot):
        logger.debug("Restored module-family identity for %s", name)


@pytest.fixture(autouse=True)
def per_test_cleanup():
    """Release memory-monitor resources after each test."""
    yield
    try:
        from utils.memory_monitor import cleanup_memory_monitor

        cleanup_memory_monitor()
    except Exception:
        pass


@pytest.fixture
def lingo_translator(monkeypatch):
    """Provide a LingoTranslator instance with a test API key for any test module/class."""
    # Set the environment variable using monkeypatch (automatically restored after test)
    monkeypatch.setenv("LINGO_API_KEY", "test_api_key")

    # Import LingoTranslator after setting the environment variable
    from services.translation_service import LingoTranslator

    return LingoTranslator()


def pytest_configure(config: pytest.Config) -> None:
    """Set required environment variables for tests early in startup.

    This runs before test collection, ensuring modules that read environment
    variables at import time (e.g., `config.settings.Settings`) see the values.
    """
    # Set DEBUG=True for tests to enable auto-generated SECRET_KEY
    os.environ.setdefault("DEBUG", "true")
    # Provide a deterministic SECRET_KEY for tests to ensure consistency across workers
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only!")
    # Set memory API security environment variables
    os.environ.setdefault("MEMORY_API_ENABLE_AUTH", "true")
    os.environ.setdefault("MEMORY_API_JWT_SECRET", "test-secret-key")
    os.environ.setdefault("MEMORY_API_KEY", "test-admin-key")
    # Set mock Lingo API key to ensure safe collection for legacy translation services
    os.environ.setdefault("LINGO_API_KEY", "mock_lingo_api_key_for_tests")

    # When focusing, quiet output at runtime without relying on pre-parsed
    # addopts
    if os.getenv("FOCUSED"):
        config.option.quiet = max(getattr(config.option, "quiet", 0), 1)


@pytest.fixture(scope="module")
def test_client():
    """Pytest fixture providing a test client with test environment.

    Uses module scope to prevent cached state leakage across tests that
    could occur when reloading modules with function-scoped fixtures.
    """
    test_env = {
        "MEMORY_API_ENABLE_AUTH": "true",
        "MEMORY_API_JWT_SECRET": "test-secret-key",
        "MEMORY_API_KEY": "test-admin-key",
        "MEMORY_API_READ_RATE_LIMIT": "100",
        "MEMORY_API_WRITE_RATE_LIMIT": "100",
        "MEMORY_API_ADMIN_RATE_LIMIT": "100",
    }

    with patch.dict("os.environ", test_env):
        # Reload modules to pick up environment
        import importlib
        import sys

        for name in _RELOAD_MODULE_NAMES:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                __import__(name)

        app_module = sys.modules["app"]
        client = TestClient(app_module.create_app())
        yield client

    # Teardown: reload modules to restore state after patch context exits.
    # This MUST run after patch.dict exits — reloading inside the patched
    # context bakes the test-env values (e.g., RATE_LIMITS=100) into the
    # module constants for the rest of the worker process, which then makes
    # tests asserting the default limits (api.rate_limit consumers) fail
    # depending on xdist scheduling order.
    for name in _RELOAD_MODULE_NAMES:
        if name in sys.modules:
            try:
                importlib.reload(sys.modules[name])
            except Exception:
                logger.debug("Failed to reload %s during teardown", name, exc_info=True)


@pytest.fixture
def read_token(test_client):
    """Pytest fixture providing a read-only token."""
    import api.auth

    return api.auth.create_jwt_token("read_user", api.auth.UserRole.READ_ONLY)


@pytest.fixture
def admin_token(test_client):
    """Pytest fixture providing an admin token."""
    import api.auth

    return api.auth.create_jwt_token("admin_user", api.auth.UserRole.ADMIN)


@pytest.fixture
def reload_app_with_env():
    """Fixture to reload modules with patched environment and cleanup after.

    Isolates environment changes by patching os.environ, reloading affected
    modules in dependency order, and restoring original modules after test.
    Yields a factory function that returns a fresh TestClient.
    """
    import sys

    # Save original module objects before any reloads
    original_modules = {}
    for name in _RELOAD_MODULE_NAMES:
        if name in sys.modules:
            original_modules[name] = sys.modules[name]

    # Track active patches and created test clients
    active_patches = []
    created_clients = []

    def _factory(test_env: dict) -> TestClient:
        """Create TestClient with patched environment and fresh module imports."""
        from unittest.mock import patch

        # Create a long-lived patch that stays active
        patch_obj = patch.dict("os.environ", test_env)
        patch_obj.start()
        active_patches.append(patch_obj)

        # Remove modules from sys.modules to ensure fresh imports
        for name in _RELOAD_MODULE_NAMES:
            if name in sys.modules:
                del sys.modules[name]

        # Import fresh modules
        for name in _RELOAD_MODULE_NAMES:
            __import__(name)

        app_module = sys.modules["app"]
        client = TestClient(app_module.create_app())
        created_clients.append(client)
        return client

    try:
        yield _factory
    finally:
        # Close all created test clients
        for client in created_clients:
            client.close()
        # Stop all active patches
        for patch_obj in active_patches:
            patch_obj.stop()
        # Restore original modules to prevent state leakage between tests
        for name in original_modules:
            sys.modules[name] = original_modules[name]
