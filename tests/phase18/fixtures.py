"""Phase 18 fixtures — real files, not mocks.

``write_pdf`` produces real PDF bytes (FlateDecode streams, WinAnsi
text, a real xref table) — the §18.5 engine then reads them back.
The DOCX/PPTX fixtures come from the engines themselves (create →
save), which is the point: the round trip is the proof.
"""

from __future__ import annotations

import zlib
from pathlib import Path

#: A real 1×1 transparent PNG — media fixtures must be real images.
PNG_1X1: bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44"
    "ae426082"
)

DOC_TITLE = "NEXUS Document Intelligence"
DOC_BODY = [
    "Documents become real runtime objects in phase eighteen.",
    "The pipeline parses structure extracts indexes and remembers.",
]
DOC_TABLE = [["surface", "status"], ["docx", "green"], ["pptx", "green"], ["pdf", "green"]]

PPTX_TITLES = ["NEXUS Documents", "Pipeline", "Proof"]
PPTX_BULLETS: dict[str, list[str]] = {
    "NEXUS Documents": ["docx pptx pdf", "stdlib only floor"],
    "Pipeline": ["parse structure extract", "index memory"],
    "Proof": ["real files in, verified files out"],
}

PDF_PAGE_1 = (
    "NEXUS runs local models on a real Windows machine. "
    "The i7-3770 has AVX but no dedicated GPU.\n"
    "Memory stays local. Nothing leaves the box without a task scope."
)
PDF_PAGE_2 = (
    "Phase eighteen adds document intelligence. "
    "DOCX PPTX and PDF are parsed into structure.\n"
    "Every finding keeps its provenance: page, slide or paragraph."
)


def write_pdf(pages: list[str | bytes], *, title: str = "NEXUS Test PDF") -> bytes:
    """A real minimal PDF writer — FlateDecode + WinAnsi + real xref.

    Fixture-side helper (the §18.5 spec verbs are read · search ·
    extract · summarize · analyze — creating PDFs is not a product
    verb, but tests need *real* files to read).
    """
    objs: dict[int, bytes] = {}
    kids: list[bytes] = []
    catalog_id, pages_id, info_id, font_id = 1, 2, 3, 4
    next_id = 5
    for text in pages:
        raw = text.encode("cp1252", errors="replace") if isinstance(text, str) else text
        content_id = next_id
        next_id += 1
        page_id = next_id
        next_id += 1
        parts = [b"BT /F1 12 Tf 72 720 Td"]
        for line in raw.split(b"\n"):
            esc = (
                line.replace(b"\\", b"\\\\")
                .replace(b"(", b"\\(")
                .replace(b")", b"\\)")
            )
            parts.append(b"(" + esc + b") Tj 0 -16 Td")
        parts.append(b"ET")
        stream = zlib.compress(b"\n".join(parts))
        objs[content_id] = (
            b"<< /Length " + str(len(stream)).encode() + b" /Filter /FlateDecode >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        objs[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            b" /Resources << /Font << /F1 " + str(font_id).encode() + b" 0 R >> >>"
            b" /Contents " + str(content_id).encode() + b" 0 R >>"
        )
        kids.append(str(page_id).encode() + b" 0 R")
    objs[catalog_id] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[pages_id] = (
        b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count "
        + str(len(pages)).encode() + b" >>"
    )
    esc_title = title.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    objs[info_id] = (
        b"<< /Title (" + esc_title.encode("cp1252", errors="replace") + b")"
        b" /Producer (nexus-phase18-fixture) >>"
    )
    objs[font_id] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        b" /Encoding /WinAnsiEncoding >>"
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += str(num).encode() + b" 0 obj\n" + objs[num] + b"\nendobj\n"
    xref_pos = len(out)
    size = max(objs) + 1
    out += b"xref\n0 " + str(size).encode() + b"\n0000000000 65535 f \n"
    for num in range(1, size):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(size).encode() + b" /Root 1 0 R /Info 3 0 R >>\n"
        b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    )
    return bytes(out)


def build_docx(path: Path) -> Path:
    """A real .docx on disk — heading, body, formatted line, table."""
    from nexus.documents.docx import DocxDocument

    doc = DocxDocument()
    doc.add_heading(DOC_TITLE, level=1)
    for line in DOC_BODY:
        doc.add_paragraph(line)
    doc.add_paragraph("the emphasized line", bold=True, italic=True, underline=True)
    doc.add_table(DOC_TABLE)
    return doc.save(path)


def build_pptx(path: Path) -> Path:
    """A real .pptx on disk — three slides, one carrying a real image."""
    from nexus.documents.pptx import PptxPresentation

    pres = PptxPresentation()
    for title in PPTX_TITLES:
        pres.add_slide(title, PPTX_BULLETS[title])
    pres.add_image(1, PNG_1X1)  # slide 2 carries the picture
    return pres.save(path)


def build_pdf(path: Path) -> Path:
    """A real two-page .pdf on disk."""
    path.write_bytes(write_pdf([PDF_PAGE_1, PDF_PAGE_2], title="NEXUS PDF Fixture"))
    return path
