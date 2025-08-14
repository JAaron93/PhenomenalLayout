from pathlib import Path
import importlib
import pytest


def write_minimal_pdf(path: Path) -> None:
    """Write a minimal but structurally valid PDF for tests.

    Includes Catalog, Pages, one Page, and a small Contents stream with
    correct xref offsets and startxref.
    """

    header = b"%PDF-1.4\n"

    # 1 0 obj: Catalog
    obj1 = b"<< /Type /Catalog /Pages 2 0 R >>"
    ob1 = b"1 0 obj\n" + obj1 + b"\nendobj\n"

    # 2 0 obj: Pages
    obj2 = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    ob2 = b"2 0 obj\n" + obj2 + b"\nendobj\n"

    # 3 0 obj: Page
    obj3 = (
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>"
    )
    ob3 = b"3 0 obj\n" + obj3 + b"\nendobj\n"

    # 4 0 obj: Contents
    stream = b"BT 0 0 Td ET\n"
    obj4 = (
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"endstream\n"
    )
    ob4 = b"4 0 obj\n" + obj4 + b"endobj\n"

    objects = [ob1, ob2, ob3, ob4]
    offsets: list[int] = []
    pos = len(header)
    for ob in objects:
        offsets.append(pos)
        pos += len(ob)

    xref_start = pos
    xref_header = b"xref\n0 5\n0000000000 65535 f \n"
    xref_entries = b"".join(
        f"{off:010d} 00000 n \n".encode() for off in offsets
    )
    xref = xref_header + xref_entries

    trailer = (
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode()
        + b"\n%%EOF\n"
    )

    data = header + b"".join(objects) + xref + trailer
    path.write_bytes(data)


def write_encrypted_pdf(path: Path) -> None:
    """Write an encrypted single-page PDF to the given path.

    Skips the test if pypdf is not available.
    """
    try:
        mod = importlib.import_module("pypdf")
        PdfWriter = getattr(mod, "PdfWriter")
    except (ImportError, AttributeError):  # pragma: no cover - optional dep
        pytest.skip("pypdf not available")
    else:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("pwd")
        with path.open("wb") as fh:
            writer.write(fh)
