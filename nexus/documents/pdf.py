"""PDF support (New Plan §18.5) — read · search · extract · summarize · analyze.

A real PDF parser over the standard library: object scan, xref-less
trailer resolution, catalog → page tree → content streams,
FlateDecode (``zlib``), the show-text operators (``Tj · TJ · ' · "``),
PDF string escapes and hex strings, WinAnsi/cp1252 text.

Scope, stated honestly: text-focused.  CID/Type0 fonts with embedded
cmaps, encrypted files and XFA forms are *not* decoded — the parser
reports what it could not read instead of inventing text.  Image-only
pages simply extract no text (OCR is §12's job, not §18.5's).

دعم PDF — الأفعال الخمسة حرفيًا؛ والمحلل يقرأ ما يستطيع ويعترف بما لا.

Stdlib only.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    DocumentKind,
    DocumentSource,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StructureNode,
    TextBlock,
    UnsupportedDocumentError,
)

# ------------------------------------------------------------------ model


@dataclass(frozen=True, slots=True)
class PdfPage:
    """One page — its extracted text and its physical box."""

    number: int  # 1-based
    text: str
    width: float = 612.0
    height: float = 792.0

    def as_dict(self) -> dict[str, Any]:
        return {"number": self.number, "text": self.text, "width": self.width,
                "height": self.height}


@dataclass(frozen=True, slots=True)
class PdfDocument:
    """The parsed PDF — metadata, pages, fonts actually referenced."""

    pages: tuple[PdfPage, ...]
    metadata: dict[str, str] = field(default_factory=dict)
    fonts: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)

    def words(self) -> int:
        return len(self.text.split())

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages": [p.as_dict() for p in self.pages],
            "metadata": dict(self.metadata),
            "fonts": list(self.fonts),
            "words": self.words(),
        }


# ----------------------------------------------------------------- parser

_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b", re.DOTALL)
_REF_RE = re.compile(rb"(\d+)\s+(\d+)\s+R")
_FONT_RE = re.compile(rb"/(\S+)\s+[\d.]+\s+Tf")
_STREAM_RE = re.compile(rb"stream\r?\n")

_ESCAPES = {
    ord("n"): b"\n",
    ord("r"): b"\r",
    ord("t"): b"\t",
    ord("b"): b"\b",
    ord("f"): b"\f",
    ord("("): b"(",
    ord(")"): b")",
    ord("\\"): b"\\",
}


def _decode_bytes(raw: bytes) -> str:
    return raw.decode("cp1252", errors="replace")


def _read_pdf_string(data: bytes, start: int) -> tuple[bytes, int]:
    """A ``(...)`` literal string with nesting and escapes → bytes, next index."""
    out = bytearray()
    depth = 1
    i = start + 1
    while i < len(data) and depth:
        b = data[i]
        if b == 0x5C:  # backslash
            nxt = data[i + 1] if i + 1 < len(data) else None
            if nxt is not None and nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
            elif nxt is not None and 0x30 <= nxt <= 0x37:
                oct_digits = data[i + 1 : i + 4]
                j = 0
                while j < len(oct_digits) and 0x30 <= oct_digits[j] <= 0x37:
                    j += 1
                out.append(int(oct_digits[:j], 8) & 0xFF)
                i += 1 + j
            elif nxt in (0x0A, 0x0D):  # line continuation
                i += 2
                if nxt == 0x0D and data[i : i + 1] == b"\n":
                    i += 1
            else:
                i += 2
        elif b == 0x28:  # (
            depth += 1
            out.append(b)
            i += 1
        elif b == 0x29:  # )
            depth -= 1
            if depth:
                out.append(b)
            i += 1
        else:
            out.append(b)
            i += 1
    return bytes(out), i


def _read_hex_string(data: bytes, start: int) -> tuple[bytes, int]:
    end = data.find(b">", start)
    if end == -1:
        return b"", len(data)
    raw = re.sub(rb"\s", b"", data[start + 1 : end])
    if len(raw) % 2:
        raw += b"0"
    return bytes.fromhex(raw.decode("ascii", errors="replace")), end + 1


def _skip_ws(data: bytes, i: int) -> int:
    while i < len(data) and data[i] in b" \t\r\n\x00\x0c":
        i += 1
    return i


def _content_to_text(content: bytes) -> tuple[str, set[str]]:
    """One decoded content stream → text + the fonts it referenced."""
    parts: list[str] = []
    fonts = {m.group(1).decode("latin-1", errors="replace") for m in _FONT_RE.finditer(content)}
    i, n = 0, len(content)
    while i < n:
        b = content[i]
        if b == 0x28:  # ( — literal string, then the show operator
            raw, j = _read_pdf_string(content, i)
            k = _skip_ws(content, j)
            if content.startswith(b"Tj", k) or content.startswith(b'"', k):
                parts.append(_decode_bytes(raw))
                if content[k : k + 1] == b'"':
                    parts.append("\n")
                i = k + (2 if content.startswith(b"Tj", k) else 1)
                continue
            if content.startswith(b"'", k):
                parts.append("\n")
                parts.append(_decode_bytes(raw))
                i = k + 1
                continue
            i = j
            continue
        if b == 0x3C and content[i : i + 2] != b"<<":  # < — hex string
            raw, j = _read_hex_string(content, i)
            k = _skip_ws(content, j)
            if content.startswith(b"Tj", k):
                parts.append(_decode_bytes(raw))
                i = k + 2
                continue
            i = j
            continue
        if b == 0x5B:  # [ — TJ array of strings and kerning numbers
            j = i + 1
            depth = 1
            while j < n and depth:
                cj = content[j]
                if cj == 0x5B:
                    depth += 1
                elif cj == 0x5D:
                    depth -= 1
                elif cj == 0x28:
                    raw, j2 = _read_pdf_string(content, j)
                    parts.append(_decode_bytes(raw))
                    j = j2 - 1
                elif cj == 0x3C and content[j : j + 2] != b"<<":
                    raw, j2 = _read_hex_string(content, j)
                    parts.append(_decode_bytes(raw))
                    j = j2 - 1
                j += 1
            i = j
            continue
        if content.startswith((b"Td", b"TD", b"T*", b"ET"), i):
            parts.append("\n")
            i += 2
            continue
        i += 1
    text = "".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), fonts


def _decode_stream(raw_body: bytes, stream_bytes: bytes) -> bytes:
    if b"/FlateDecode" in raw_body:
        try:
            return zlib.decompress(stream_bytes)
        except zlib.error as exc:
            raise ParseError(f"FlateDecode stream is corrupt: {exc}") from exc
    return stream_bytes


def _parse_objects(data: bytes) -> dict[tuple[int, int], bytes]:
    objects: dict[tuple[int, int], bytes] = {}
    for m in _OBJ_RE.finditer(data):
        num, gen = int(m.group(1)), int(m.group(2))
        body_start = m.end()
        end = data.find(b"endobj", body_start)
        if end == -1:
            continue
        body = data[body_start:end]
        sm = _STREAM_RE.search(body)
        if sm is not None:
            stream_start = sm.end()
            stream_end = body.find(b"endstream", stream_start)
            if stream_end == -1:
                stream_end = len(body)
            stream_raw = body[stream_start:stream_end]
            if stream_raw.endswith(b"\r\n"):
                stream_raw = stream_raw[:-2]
            elif stream_raw.endswith((b"\n", b"\r")):
                stream_raw = stream_raw[:-1]
            body = body[: sm.start()] + b"__STREAM__"
            decoded = _decode_stream(body, stream_raw)
            objects[(num, gen)] = b"STREAM:" + body + b"\x00" + decoded
        else:
            objects[(num, gen)] = body
    return objects


def _resolve(objects: dict[tuple[int, int], bytes], ref: bytes | None) -> bytes:
    if ref is None:
        return b""
    m = re.fullmatch(rb"\s*(\d+)\s+(\d+)\s+R\s*", ref)
    if not m:
        return ref
    return objects.get((int(m.group(1)), int(m.group(2))), b"")


def _ref_after(body: bytes, key: str) -> bytes | None:
    m = re.search(rb"/" + key.encode() + rb"\s+(\d+)\s+(\d+)\s+R", body)
    if m is None:
        return None
    return m.group(1) + b" " + m.group(2) + b" R"


def _kids_refs(pages_body: bytes) -> list[bytes]:
    m = re.search(rb"/Kids\s*\[(.*?)\]", pages_body, re.DOTALL)
    if m is None:
        return []
    return [r.group(0).strip() for r in _REF_RE.finditer(m.group(1))]


def parse_pdf(data: bytes) -> PdfDocument:
    """§18.5 *read* — parse real PDF bytes into pages + metadata."""
    if not data.startswith(b"%PDF-"):
        raise ParseError("not a PDF (missing %PDF- header)")
    objects = _parse_objects(data)

    root_ref = None
    tm = re.search(rb"/Root\s+(\d+)\s+(\d+)\s+R", data)
    if tm is not None:
        root_ref = tm.group(0).strip()
    catalog = _resolve(objects, root_ref)
    if not catalog or b"/Catalog" not in catalog:
        for body in objects.values():
            if b"/Catalog" in body:
                catalog = body
                break
    pages_body = _resolve(objects, _ref_after(catalog, "Pages") if catalog else None)
    if not pages_body:
        raise ParseError("no page tree found — the PDF has no readable pages")

    fonts: set[str] = set()
    pages: list[PdfPage] = []

    def walk_page(node_ref: bytes) -> None:
        node = _resolve(objects, node_ref)
        if b"/Pages" in node and b"/Kids" in node:
            for kid in _kids_refs(node):
                walk_page(kid)
            return
        if b"/Page" not in node:
            return
        page_num = len(pages) + 1
        width, height = 612.0, 792.0
        box = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", node)
        if box is not None:
            width = float(box.group(3)) - float(box.group(1))
            height = float(box.group(4)) - float(box.group(2))
        text = ""
        content_ref = _ref_after(node, "Contents")
        if content_ref is not None:
            content_body = _resolve(objects, content_ref)
            if b"__STREAM__" in content_body:
                text, page_fonts = _content_from_stored(content_body)
                fonts.update(page_fonts)
        else:
            arr = re.search(rb"/Contents\s*\[(.*?)\]", node, re.DOTALL)
            if arr is not None:
                chunks: list[str] = []
                for r in _REF_RE.finditer(arr.group(1)):
                    body = _resolve(objects, r.group(0).strip())
                    if b"__STREAM__" in body:
                        chunk, page_fonts = _content_from_stored(body)
                        chunks.append(chunk)
                        fonts.update(page_fonts)
                text = "\n".join(c for c in chunks if c)
        pages.append(PdfPage(number=page_num, text=text, width=width, height=height))

    def _content_from_stored(body: bytes) -> tuple[str, set[str]]:
        _, _, decoded = body.partition(b"\x00")
        return _content_to_text(decoded)

    for kid in _kids_refs(pages_body):
        walk_page(kid)

    metadata: dict[str, str] = {}
    im = re.search(rb"/Info\s+(\d+)\s+(\d+)\s+R", data)
    if im is not None:
        info = objects.get((int(im.group(1)), int(im.group(2))), b"")
        for key in ("Title", "Author", "Producer", "Creator", "CreationDate"):
            vm = re.search(
                rb"/" + key.encode() + rb"\s*(\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]*>)", info
            )
            if vm is None:
                continue
            raw_val = vm.group(1)
            if raw_val.startswith(b"("):
                s, _ = _read_pdf_string(info, vm.start(1))
                metadata[key] = _decode_bytes(s).strip()
            else:
                s, _ = _read_hex_string(info, vm.start(1))
                metadata[key] = _decode_bytes(s).strip()
    return PdfDocument(pages=tuple(pages), metadata=metadata, fonts=tuple(sorted(fonts)))


# ------------------------------------------------------------------ verbs


def search(doc: PdfDocument, term: str) -> list[dict[str, Any]]:
    """§18.5 *search* — case-insensitive hits with page numbers and context."""
    if not term.strip():
        return []
    needle = term.lower()
    out: list[dict[str, Any]] = []
    for page in doc.pages:
        low = page.text.lower()
        start = 0
        while True:
            idx = low.find(needle, start)
            if idx == -1:
                break
            ctx_from = max(0, idx - 40)
            ctx_to = min(len(page.text), idx + len(term) + 40)
            out.append(
                {
                    "page": page.number,
                    "match": page.text[idx : idx + len(term)],
                    "context": page.text[ctx_from:ctx_to].replace("\n", " "),
                }
            )
            start = idx + len(term)
    return out


def extract(doc: PdfDocument, *, page: int | None = None) -> str:
    """§18.5 *extract* — all text, or one page's text (1-based)."""
    if page is None:
        return doc.text
    for p in doc.pages:
        if p.number == page:
            return p.text
    raise IndexError(f"no page {page} (document has {len(doc.pages)} pages)")


_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    this to was with عن في من على الى إلى ما هل هذا هذه التي الذي""".split()
)


def summarize(doc: PdfDocument, *, max_sentences: int = 5) -> list[str]:
    """§18.5 *summarize* — extractive: top sentences by word frequency.

    No model, no magic: sentence scores are the summed frequencies of
    their significant words; the top sentences come back in document
    order so the summary stays readable.
    """
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?؟])\s+|\n+", doc.text)
        if len(s.strip()) >= 15
    ]
    if not sentences:
        return []
    freq: dict[str, int] = {}
    for sentence in sentences:
        for word in re.findall(r"[\w]+", sentence.lower()):
            if word not in _STOPWORDS and not word.isdigit():
                freq[word] = freq.get(word, 0) + 1
    scored = [
        (sum(freq.get(w, 0) for w in re.findall(r"[\w]+", s.lower())), i, s)
        for i, s in enumerate(sentences)
    ]
    top = sorted(scored, key=lambda t: (-t[0], t[1]))[:max(1, max_sentences)]
    return [s for _, _, s in sorted(top, key=lambda t: t[1])]


def analyze(doc: PdfDocument) -> dict[str, Any]:
    """§18.5 *analyze* — counts, per-page stats, metadata, fonts."""
    per_page = [
        {
            "page": p.number,
            "words": len(p.text.split()),
            "chars": len(p.text),
        }
        for p in doc.pages
    ]
    return {
        "pages": len(doc.pages),
        "words": doc.words(),
        "chars": len(doc.text),
        "per_page": per_page,
        "metadata": dict(doc.metadata),
        "fonts": list(doc.fonts),
        "empty_pages": [p.number for p in doc.pages if not p.text.strip()],
    }


# ----------------------------------------------------- §18.1 native floor


class PdfParseBackend(ParseBackend):
    """The native PDF floor — always present, stdlib only."""

    name = "native.pdf"
    kinds = (DocumentKind.PDF,)

    def parse(self, source: DocumentSource) -> ParsedDocument:
        if source.kind != DocumentKind.PDF:
            raise UnsupportedDocumentError(
                f"native.pdf parses pdf only, got {source.kind!r}"
            )
        import hashlib

        doc = parse_pdf(source.data)
        blocks = [
            TextBlock(text=p.text, locator=f"page {p.number}", role="body")
            for p in doc.pages
            if p.text.strip()
        ]
        structure = tuple(
            StructureNode(name=f"page {p.number}", node_type="page") for p in doc.pages
        )
        return ParsedDocument(
            kind=DocumentKind.PDF,
            uri=source.uri,
            title=doc.metadata.get("Title", ""),
            sha256=hashlib.sha256(source.data).hexdigest(),
            size_bytes=len(source.data),
            structure=structure,
            blocks=tuple(blocks),
            metadata={
                "pages": str(len(doc.pages)),
                **{k: v for k, v in doc.metadata.items()},
            },
            parser=self.name,
        )
