"""DOCX support (New Plan §18.3) — read · create · edit · format · save · verify.

A ``.docx`` is an OOXML ZIP package; the core (``[Content_Types].xml``,
``_rels/.rels``, ``word/document.xml``) is fully buildable and
parseable with the standard library.  This engine owns a real round
trip — create real packages Word/LibreOffice open, read packages Word
itself wrote (namespace-correct parsing), edit text, apply formatting,
save, and verify what was saved by re-reading it from disk.

Scope, stated honestly: the *core* OOXML surface (paragraphs, runs,
headings, alignment, sizes, tables).  Word's full style gallery and
floaters (headers/footers, embedded OLE) ride the §18.1 docling engine
when it is installed — this floor never pretends to cover them.

دعم DOCX — الأفعال الستة حرفيًا فوق حزمة OOXML مبنية بمكتبة قياسية فقط.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .contracts import (
    DocumentKind,
    DocumentSource,
    DocumentVerification,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StructureNode,
    TextBlock,
    UnsupportedDocumentError,
    VerifyError,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Types xmlns="{CT_NS}">'
    '<Default Extension="rels" ContentType='
    '"application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType='
    '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{REL_NS}">'
    f'<Relationship Id="rId1" Type="{DOC_REL_TYPE}" Target="word/document.xml"/>'
    "</Relationships>"
)

_ALIGNMENTS = ("left", "center", "right", "both")
_HEADING_STYLES = tuple(f"Heading{i}" for i in range(1, 7))
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# ------------------------------------------------------------------ model


@dataclass
class DocxRun:
    """One run — text plus its direct formatting."""

    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    size_pt: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "size_pt": self.size_pt,
        }


@dataclass
class DocxParagraph:
    """One paragraph — runs plus paragraph-level formatting."""

    runs: list[DocxRun] = field(default_factory=list)
    style: str = ""  # "" | Heading1..Heading6
    alignment: str = ""  # "" | left | center | right | both

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "style": self.style,
            "alignment": self.alignment,
            "runs": [run.as_dict() for run in self.runs],
        }


@dataclass
class DocxTable:
    """One table — plain cell text (the core OOXML surface)."""

    rows: list[list[str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"rows": [list(row) for row in self.rows]}


@dataclass
class DocxDocument:
    """The DOCX model — paragraphs in body order, then tables."""

    paragraphs: list[DocxParagraph] = field(default_factory=list)
    tables: list[DocxTable] = field(default_factory=list)

    # ------------------------------------------------------------ create

    def add_paragraph(
        self,
        text: str,
        *,
        style: str = "",
        alignment: str = "",
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        size_pt: float | None = None,
    ) -> DocxParagraph:
        """§18.3 *create* — append one paragraph, format applied to all runs."""
        if alignment and alignment not in _ALIGNMENTS:
            raise ValueError(f"alignment must be one of {_ALIGNMENTS}, got {alignment!r}")
        if style and style not in _HEADING_STYLES:
            raise ValueError(f"style must be one of {_HEADING_STYLES} or '', got {style!r}")
        run = DocxRun(
            text=text,
            bold=bool(bold),
            italic=bool(italic),
            underline=bool(underline),
            size_pt=size_pt,
        )
        para = DocxParagraph(runs=[run], style=style, alignment=alignment)
        self.paragraphs.append(para)
        return para

    def add_heading(self, text: str, *, level: int = 1) -> DocxParagraph:
        """§18.3 *create* — one heading paragraph (Heading1..Heading6)."""
        if not 1 <= level <= 6:
            raise ValueError(f"heading level must be 1..6, got {level}")
        return self.add_paragraph(text, style=f"Heading{level}")

    def add_table(self, rows: list[list[str]]) -> DocxTable:
        """§18.3 *create* — one table; every row must have equal width."""
        if not rows:
            raise ValueError("a table needs at least one row")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("table rows must all have the same width")
        table = DocxTable(rows=[list(row) for row in rows])
        self.tables.append(table)
        return table

    # -------------------------------------------------------------- edit

    def set_text(self, index: int, text: str) -> None:
        """§18.3 *edit* — replace a paragraph's text, keep its formatting."""
        para = self._paragraph_at(index)
        kept = para.runs[0] if para.runs else DocxRun()
        para.runs = [
            DocxRun(
                text=text,
                bold=kept.bold,
                italic=kept.italic,
                underline=kept.underline,
                size_pt=kept.size_pt,
            )
        ]

    def delete_paragraph(self, index: int) -> None:
        """§18.3 *edit* — remove one paragraph."""
        self.paragraphs.pop(self._resolve(index))

    def format_paragraph(
        self,
        index: int,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        size_pt: float | None = None,
        alignment: str | None = None,
        heading: int | None = None,
    ) -> DocxParagraph:
        """§18.3 *format* — apply direct formatting; ``None`` keeps current."""
        para = self._paragraph_at(index)
        if bold is not None:
            for run in para.runs:
                run.bold = bold
        if italic is not None:
            for run in para.runs:
                run.italic = italic
        if underline is not None:
            for run in para.runs:
                run.underline = underline
        if size_pt is not None:
            if size_pt <= 0:
                raise ValueError(f"size_pt must be positive, got {size_pt}")
            for run in para.runs:
                run.size_pt = size_pt
        if alignment is not None:
            if alignment not in _ALIGNMENTS:
                raise ValueError(f"alignment must be one of {_ALIGNMENTS}, got {alignment!r}")
            para.alignment = alignment
        if heading is not None:
            if not 1 <= heading <= 6:
                raise ValueError(f"heading must be 1..6, got {heading}")
            para.style = f"Heading{heading}"
        return para

    def _resolve(self, index: int) -> int:
        if not -len(self.paragraphs) <= index < len(self.paragraphs):
            raise IndexError(f"paragraph index {index} out of range")
        return index if index >= 0 else index + len(self.paragraphs)

    def _paragraph_at(self, index: int) -> DocxParagraph:
        return self.paragraphs[self._resolve(index)]

    # -------------------------------------------------------------- save

    def save(self, path: str | Path) -> Path:
        """§18.3 *save* — write a real OOXML package to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("_rels/.rels", _ROOT_RELS)
            zf.writestr("word/document.xml", _document_xml(self))
        return target

    def to_bytes(self) -> bytes:
        """The package bytes — exactly what :meth:`save` writes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("_rels/.rels", _ROOT_RELS)
            zf.writestr("word/document.xml", _document_xml(self))
        return buf.getvalue()


# ------------------------------------------------------------------- xml


def _run_xml(run: DocxRun) -> ET.Element:
    node = ET.Element(_w("r"))
    props = ET.SubElement(node, _w("rPr"))
    if run.bold:
        ET.SubElement(props, _w("b"))
    if run.italic:
        ET.SubElement(props, _w("i"))
    if run.underline:
        u = ET.SubElement(props, _w("u"))
        u.set(_w("val"), "single")
    if run.size_pt is not None:
        sz = ET.SubElement(props, _w("sz"))
        sz.set(_w("val"), str(int(round(run.size_pt * 2))))
    if not len(props):
        node.remove(props)
    t = ET.SubElement(node, _w("t"))
    t.set(_XML_SPACE, "preserve")
    t.text = run.text
    return node


def _paragraph_xml(para: DocxParagraph) -> ET.Element:
    node = ET.Element(_w("p"))
    props = ET.SubElement(node, _w("pPr"))
    if para.style:
        style = ET.SubElement(props, _w("pStyle"))
        style.set(_w("val"), para.style)
    if para.alignment:
        jc = ET.SubElement(props, _w("jc"))
        jc.set(_w("val"), para.alignment)
    if not len(props):
        node.remove(props)
    for run in para.runs:
        node.append(_run_xml(run))
    if not any(child.tag == _w("r") for child in node):
        ET.SubElement(node, _w("r"))
    return node


def _table_xml(table: DocxTable) -> ET.Element:
    node = ET.Element(_w("tbl"))
    props = ET.SubElement(node, _w("tblPr"))
    tbl_w = ET.SubElement(props, _w("tblW"))
    tbl_w.set(_w("w"), "0")
    tbl_w.set(_w("type"), "auto")
    width = len(table.rows[0])
    grid = ET.SubElement(node, _w("tblGrid"))
    for _ in range(width):
        ET.SubElement(grid, _w("gridCol"))
    for row in table.rows:
        tr = ET.SubElement(node, _w("tr"))
        for cell in row:
            tc = ET.SubElement(tr, _w("tc"))
            tc.append(_paragraph_xml(DocxParagraph(runs=[DocxRun(text=cell)])))
    return node


def _document_xml(doc: DocxDocument) -> str:
    ET.register_namespace("w", W_NS)
    root = ET.Element(_w("document"))
    body = ET.SubElement(root, _w("body"))
    for para in doc.paragraphs:
        body.append(_paragraph_xml(para))
    for table in doc.tables:
        body.append(_table_xml(table))
    sect = ET.SubElement(body, _w("sectPr"))
    pg_sz = ET.SubElement(sect, _w("pgSz"))  # A4, twips
    pg_sz.set(_w("w"), "11906")
    pg_sz.set(_w("h"), "16838")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + ET.tostring(
        root, encoding="unicode"
    )


def _is_on(el: ET.Element, tag: str) -> bool:
    node = el.find(_w(tag))
    if node is None:
        return False
    return node.get(_w("val"), "") not in ("false", "0", "none")


# ------------------------------------------------------------------- read


def read(path: str | Path) -> DocxDocument:
    """§18.3 *read* — parse a real .docx package (ours or Word's)."""
    target = Path(path)
    try:
        with zipfile.ZipFile(target) as zf:
            raw = zf.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise ParseError(f"not a readable .docx package: {target}") from exc
    except KeyError as exc:
        raise ParseError("the package has no word/document.xml — not a DOCX") from exc
    return parse_document_xml(raw)


def parse_document_xml(raw: bytes) -> DocxDocument:
    """Parse ``word/document.xml`` bytes — namespace-correct."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ParseError(f"document.xml is not well-formed: {exc}") from exc
    doc = DocxDocument()
    body = root.find(_w("body"))
    if body is None:
        return doc
    for child in body:
        if child.tag == _w("p"):
            doc.paragraphs.append(_parse_paragraph(child))
        elif child.tag == _w("tbl"):
            doc.tables.append(_parse_table(child))
    return doc


def _parse_paragraph(node: ET.Element) -> DocxParagraph:
    para = DocxParagraph()
    ppr = node.find(_w("pPr"))
    if ppr is not None:
        style = ppr.find(_w("pStyle"))
        if style is not None:
            para.style = style.get(_w("val"), "")
        jc = ppr.find(_w("jc"))
        if jc is not None:
            para.alignment = jc.get(_w("val"), "")
    for run_node in node.findall(_w("r")):
        run = DocxRun()
        rpr = run_node.find(_w("rPr"))
        if rpr is not None:
            run.bold = _is_on(rpr, "b")
            run.italic = _is_on(rpr, "i")
            run.underline = _is_on(rpr, "u")
            sz = rpr.find(_w("sz"))
            raw_val = sz.get(_w("val"), "") if sz is not None else ""
            if raw_val.isdigit():
                run.size_pt = int(raw_val) / 2.0
        run.text = "".join(t.text or "" for t in run_node.findall(_w("t")))
        para.runs.append(run)
    if not para.runs:
        para.runs.append(DocxRun())
    return para


def _parse_table(node: ET.Element) -> DocxTable:
    table = DocxTable()
    for tr in node.findall(_w("tr")):
        table.rows.append(
            ["".join(t.text or "" for t in tc.iter(_w("t"))) for tc in tr.findall(_w("tc"))]
        )
    return table


# ----------------------------------------------------------------- verify


def verify(path: str | Path, *, expect_text: str = "") -> DocumentVerification:
    """§18.3 *verify* — re-open what was saved and prove it holds.

    Checks actually run: zip integrity · main part present ·
    document.xml well-formed · paragraphs parseable · expected text
    present (when ``expect_text`` given).
    """
    target = Path(path)
    checks: dict[str, bool] = {}
    try:
        with zipfile.ZipFile(target) as zf:
            checks["zip_integrity"] = zf.testzip() is None
            names = set(zf.namelist())
            checks["main_part"] = "word/document.xml" in names
            raw = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise VerifyError(f"verification failed on {target}: {exc}") from exc
    try:
        doc = parse_document_xml(raw)
        checks["paragraphs_parse"] = True
    except ParseError:
        checks["paragraphs_parse"] = False
        doc = DocxDocument()
    if expect_text:
        joined = "\n".join(p.text for p in doc.paragraphs)
        checks["text_roundtrip"] = expect_text in joined
    ok = all(checks.values())
    detail = " · ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in checks.items())
    return DocumentVerification(ok=ok, path=str(target), checks=checks, detail=detail)


# ----------------------------------------------------------------- images


def image_inventory(path: str | Path) -> tuple[tuple[str, str, int], ...]:
    """DOCX media inventory — ``(part, format, size_bytes)`` triples."""
    with zipfile.ZipFile(Path(path)) as zf:
        return tuple(
            (name, Path(name).suffix.lstrip("."), zf.getinfo(name).file_size)
            for name in zf.namelist()
            if name.startswith("word/media/")
        )


# ----------------------------------------------------- §18.1 native floor


class DocxParseBackend(ParseBackend):
    """The native DOCX floor — always present, stdlib only."""

    name = "native.docx"
    kinds = (DocumentKind.DOCX,)

    def parse(self, source: DocumentSource) -> ParsedDocument:
        if source.kind != DocumentKind.DOCX:
            raise UnsupportedDocumentError(
                f"native.docx parses docx only, got {source.kind!r}"
            )
        try:
            with zipfile.ZipFile(io.BytesIO(source.data)) as zf:
                raw = zf.read("word/document.xml")
            doc = parse_document_xml(raw)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise ParseError(f"unreadable DOCX package: {exc}") from exc
        blocks: list[TextBlock] = []
        headings: list[StructureNode] = []
        for i, para in enumerate(doc.paragraphs, start=1):
            if not para.text.strip():
                continue
            role = "heading" if para.style.startswith("Heading") else "body"
            blocks.append(TextBlock(text=para.text, locator=f"paragraph {i}", role=role))
            if role == "heading":
                headings.append(StructureNode(name=para.text, node_type="heading"))
        for t, table in enumerate(doc.tables, start=1):
            for r, row in enumerate(table.rows, start=1):
                blocks.append(
                    TextBlock(text=" | ".join(row), locator=f"table {t} row {r}", role="table")
                )
        if not headings and blocks:
            headings.append(StructureNode(name=blocks[0].text[:60], node_type="section"))
        title = headings[0].name if headings else (blocks[0].text[:60] if blocks else "")
        return ParsedDocument(
            kind=DocumentKind.DOCX,
            uri=source.uri,
            title=title,
            sha256=hashlib.sha256(source.data).hexdigest(),
            size_bytes=len(source.data),
            structure=tuple(headings),
            blocks=tuple(blocks),
            metadata={"paragraphs": str(len(doc.paragraphs)), "tables": str(len(doc.tables))},
            parser=self.name,
        )
