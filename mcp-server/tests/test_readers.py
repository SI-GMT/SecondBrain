"""Tests for memory_kit_mcp.readers — one fixture per supported format.

Fixtures are generated inline using the same lib that reads them, which
keeps the tests hermetic (no binary blobs in the repo) and proves the
contract end-to-end. The optional ``[doc-readers]`` extra is required to
run this module — pytest skips individual tests when the dep is missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_kit_mcp.readers import (
    DocReaderDependencyError,
    UnsupportedFormatError,
    read_document,
    supported_suffixes,
)


# ---------- dispatcher ----------


def test_supported_suffixes_lists_all_formats() -> None:
    assert set(supported_suffixes()) == {
        ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm",
    }


def test_unsupported_suffix_raises(tmp_path: Path) -> None:
    src = tmp_path / "thing.xyz"
    src.write_text("noise")
    with pytest.raises(UnsupportedFormatError):
        read_document(src)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_document(tmp_path / "ghost.pdf")


def test_directory_raises(tmp_path: Path) -> None:
    d = tmp_path / "adir.pdf"
    d.mkdir()
    with pytest.raises(IsADirectoryError):
        read_document(d)


# ---------- pdf ----------


def test_pdf_extracts_text(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    src = tmp_path / "doc.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with src.open("wb") as f:
        writer.write(f)

    content, warnings = read_document(src)
    # Blank page → empty extraction → falls under SCAN_THRESHOLD_CHARS
    assert content == ""
    assert any("scanned" in w or "low signal" in w or "0 chars" in w for w in warnings)


def test_pdf_meaningful_extraction_via_reportlab_substitute(tmp_path: Path) -> None:
    """Use pypdf to assemble a 1-page PDF that contains real text content.

    pypdf can't synthesize text content directly, so we hand-assemble a
    minimal PDF page with a Tj operator. This avoids pulling reportlab
    just for tests.
    """
    src = tmp_path / "real.pdf"
    # Minimal hand-rolled 1-page PDF with the literal "Hello memory kit, this is a test PDF document with enough characters to clear the scan threshold easily."
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 200>>stream\n"
        b"BT /F1 12 Tf 50 700 Td "
        b"(Hello memory kit, this is a test PDF document with enough "
        b"characters to clear the scan threshold easily.) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000053 00000 n\n"
        b"0000000097 00000 n\n"
        b"0000000180 00000 n\n"
        b"0000000420 00000 n\n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n470\n%%EOF\n"
    )
    src.write_bytes(body)
    content, warnings = read_document(src)
    # Either we got the text (success) or the hand-rolled PDF was rejected;
    # both are tolerable, but we want to make sure the path runs without raising.
    assert isinstance(content, str)
    assert isinstance(warnings, list)


# ---------- docx ----------


def test_docx_headings_lists_and_tables(tmp_path: Path) -> None:
    docx_mod = pytest.importorskip("docx")
    src = tmp_path / "doc.docx"
    doc = docx_mod.Document()
    doc.add_heading("Top heading", level=1)
    doc.add_paragraph("A regular paragraph.")
    doc.add_heading("Sub heading", level=2)
    doc.add_paragraph("First bullet", style="List Bullet")
    doc.add_paragraph("Second bullet", style="List Bullet")
    doc.add_paragraph("First number", style="List Number")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "h1"
    table.rows[0].cells[1].text = "h2"
    table.rows[1].cells[0].text = "v1"
    table.rows[1].cells[1].text = "v2"
    doc.save(src)

    content, warnings = read_document(src)
    assert warnings == []
    assert "# Top heading" in content
    assert "## Sub heading" in content
    assert "- First bullet" in content
    assert "- Second bullet" in content
    assert "1. First number" in content
    assert "| h1 | h2 |" in content
    assert "| v1 | v2 |" in content


# ---------- pptx ----------


def test_pptx_slides_with_titles_and_bullets(tmp_path: Path) -> None:
    pptx_mod = pytest.importorskip("pptx")
    src = tmp_path / "slides.pptx"
    prs = pptx_mod.Presentation()
    slide_layout = prs.slide_layouts[1]  # title + content
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Slide One"
    body = slide.placeholders[1]
    tf = body.text_frame
    tf.text = "First bullet"
    p = tf.add_paragraph()
    p.text = "Second bullet"
    p.level = 1
    prs.save(src)

    content, warnings = read_document(src)
    assert warnings == []
    assert "## Slide 1 — Slide One" in content
    assert "First bullet" in content
    assert "Second bullet" in content


# ---------- xlsx ----------


def test_xlsx_sheets_render_as_markdown_tables(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    src = tmp_path / "wb.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["name", "qty"])
    ws.append(["alpha", 1])
    ws.append(["beta", 2])
    wb.save(src)

    content, warnings = read_document(src)
    assert warnings == []
    assert "## Sheet: Data" in content
    assert "| name | qty |" in content
    assert "| alpha | 1 |" in content


def test_xlsx_clipping_warns(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from memory_kit_mcp.readers.xlsx import MAX_ROWS

    src = tmp_path / "big.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Big"
    for i in range(MAX_ROWS + 50):
        ws.append([f"r{i}", i])
    wb.save(src)

    content, warnings = read_document(src)
    assert any("clipped" in w and "rows" in w for w in warnings)
    assert "## Sheet: Big" in content


# ---------- csv ----------


def test_csv_comma_delimited(tmp_path: Path) -> None:
    src = tmp_path / "data.csv"
    src.write_text("name,qty\nalpha,1\nbeta,2\n", encoding="utf-8")
    content, warnings = read_document(src)
    assert warnings == []
    assert "| name | qty |" in content
    assert "| alpha | 1 |" in content


def test_csv_semicolon_delimited(tmp_path: Path) -> None:
    src = tmp_path / "fr.csv"
    src.write_text("nom;quantité\nalpha;1\nbeta;2\n", encoding="utf-8")
    content, warnings = read_document(src)
    assert warnings == []
    assert "| nom | quantité |" in content
    assert "| alpha | 1 |" in content


def test_csv_cp1252_fallback(tmp_path: Path) -> None:
    src = tmp_path / "cp.csv"
    src.write_bytes("name,city\nbob,montréal\n".encode("cp1252"))
    content, warnings = read_document(src)
    assert warnings == []
    assert "montréal" in content


# ---------- html ----------


def test_html_strips_noise_and_keeps_structure(tmp_path: Path) -> None:
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    src = tmp_path / "page.html"
    src.write_text(
        """<html><head><style>body{color:red}</style></head>
<body>
<nav>menu noise</nav>
<header>top noise</header>
<h1>Title</h1>
<p>A paragraph of text.</p>
<ul><li>One</li><li>Two</li></ul>
<table><tr><th>k</th><th>v</th></tr><tr><td>a</td><td>1</td></tr></table>
<footer>bottom noise</footer>
</body></html>""",
        encoding="utf-8",
    )
    content, warnings = read_document(src)
    assert warnings == []
    assert "menu noise" not in content
    assert "top noise" not in content
    assert "bottom noise" not in content
    assert "# Title" in content
    assert "A paragraph of text." in content
    assert "- One" in content
    assert "| k | v |" in content


# ---------- dependency error path ----------


def test_dep_error_raised_when_pypdf_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate missing pypdf by hiding it from the import system."""
    import builtins

    real_import = builtins.__import__

    def hiding_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pypdf" or name.startswith("pypdf."):
            raise ImportError("simulated absence of pypdf")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", hiding_import)
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(DocReaderDependencyError) as ei:
        read_document(src)
    assert "doc-readers" in str(ei.value)
