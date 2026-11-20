"""Phase 18 · §18.3 DOCX — read · create · edit · format · save · verify."""

from __future__ import annotations

import pytest

from nexus.documents import (
    DocumentSource,
    ParseError,
    UnsupportedDocumentError,
    VerifyError,
)
from nexus.documents.docx import (
    DocxDocument,
    DocxParseBackend,
    read,
    verify,
)

TEXT = "documents become runtime objects"


def _doc() -> DocxDocument:
    doc = DocxDocument()
    doc.add_heading("Report", level=1)
    doc.add_paragraph(TEXT)
    return doc


def test_create_save_read_roundtrip(tmp_path) -> None:
    path = _doc().save(tmp_path / "r.docx")
    back = read(path)
    assert [p.text for p in back.paragraphs] == ["Report", TEXT]


def test_heading_levels_and_styles(tmp_path) -> None:
    doc = DocxDocument()
    doc.add_heading("one", level=1)
    doc.add_heading("two", level=6)
    with pytest.raises(ValueError):
        doc.add_heading("bad", level=7)
    back = read(doc.save(tmp_path / "h.docx"))
    assert [p.style for p in back.paragraphs] == ["Heading1", "Heading6"]


def test_format_bold_italic_underline(tmp_path) -> None:
    doc = DocxDocument()
    doc.add_paragraph("plain")
    doc.format_paragraph(0, bold=True, italic=True, underline=True)
    back = read(doc.save(tmp_path / "f.docx"))
    run = back.paragraphs[0].runs[0]
    assert run.bold and run.italic and run.underline


def test_format_size_pt(tmp_path) -> None:
    doc = DocxDocument()
    doc.add_paragraph("big")
    doc.format_paragraph(0, size_pt=14)
    back = read(doc.save(tmp_path / "s.docx"))
    assert back.paragraphs[0].runs[0].size_pt == 14.0


def test_alignment_roundtrip(tmp_path) -> None:
    doc = DocxDocument()
    doc.add_paragraph("centered", alignment="center")
    with pytest.raises(ValueError):
        doc.add_paragraph("bad", alignment="diagonal")
    back = read(doc.save(tmp_path / "a.docx"))
    assert back.paragraphs[0].alignment == "center"


def test_edit_set_text_keeps_formatting(tmp_path) -> None:
    doc = DocxDocument()
    doc.add_paragraph("original", bold=True)
    doc.set_text(0, "replaced")
    back = read(doc.save(tmp_path / "e.docx"))
    assert back.paragraphs[0].text == "replaced"
    assert back.paragraphs[0].runs[0].bold is True


def test_edit_delete_paragraph(tmp_path) -> None:
    doc = _doc()
    doc.delete_paragraph(0)
    back = read(doc.save(tmp_path / "d.docx"))
    assert [p.text for p in back.paragraphs] == [TEXT]


def test_table_roundtrip(tmp_path) -> None:
    doc = _doc()
    doc.add_table([["a", "b"], ["c", "d"]])
    back = read(doc.save(tmp_path / "t.docx"))
    assert back.tables[0].rows == [["a", "b"], ["c", "d"]]


def test_table_rows_must_match_width() -> None:
    doc = DocxDocument()
    with pytest.raises(ValueError):
        doc.add_table([["a", "b"], ["c"]])


def test_verify_ok(tmp_path) -> None:
    path = _doc().save(tmp_path / "v.docx")
    verdict = verify(path, expect_text=TEXT)
    assert verdict.ok and verdict.checks["text_roundtrip"]


def test_verify_rejects_corruption(tmp_path) -> None:
    path = _doc().save(tmp_path / "c.docx")
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    with pytest.raises(VerifyError):
        verify(path)


def test_read_rejects_non_docx(tmp_path) -> None:
    bogus = tmp_path / "bogus.docx"
    bogus.write_bytes(b"PK\x03\x04 definitely not a zip payload")
    with pytest.raises(ParseError):
        read(bogus)


def test_backend_kind_law(tmp_path) -> None:
    backend = DocxParseBackend()
    with pytest.raises(UnsupportedDocumentError):
        backend.parse(
            DocumentSource(data=b"%PDF-1.4 fake", name="x.pdf")
        )


def test_backend_parses_bytes(tmp_path) -> None:
    data = _doc().to_bytes()
    parsed = DocxParseBackend().parse(
        DocumentSource(data=data, name="r.docx")
    )
    assert parsed.kind == "docx" and parsed.parser == "native.docx"
    roles = {b.role for b in parsed.blocks}
    assert "heading" in roles and "body" in roles
    assert parsed.blocks[0].locator == "paragraph 1"
    assert parsed.sha256
