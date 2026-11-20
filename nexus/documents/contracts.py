"""Document-intelligence contracts (New Plan §18.1–§18.5).

Vocabularies verbatim from the plan:

§18.2 — the pipeline, five stages after the document itself::

    Document → Parse → Structure → Extract → Index → Memory

§18.3 — the DOCX verbs::

    read   create   edit   format   save   verify

§18.4 — the PPTX verbs::

    create   slides   images   layout   sources   save   verify

§18.5 — the PDF verbs::

    read   search   extract   summarize   analyze

NEXUS owns the document semantics (Plan §61's law): every external
parsing engine — docling (§18.1, MODE A when installed, MODE B through
this contract otherwise) — enters behind :class:`ParseBackend`; the
pipeline never sees a vendor type.  The native stdlib backends
(DOCX/PPTX/PDF OOXML readers) are the always-present floor, so a
document flows even when the heavy engine is absent.

عقود ذكاء المستندات — مراحل السير الخمس وأفعال DOCX/PPTX/PDF حرفية كما
في الخطة؛ كل محرك تحليل خارجي يدخل خلف عقد ParseBackend واحد.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------- errors


class DocumentError(Exception):
    """Document-engine misuse or operation failure."""


class UnsupportedDocumentError(DocumentError):
    """The document kind is not supported by this engine/backend."""


class BackendUnavailableError(DocumentError):
    """An optional engine (docling, §18.1) is not installed on this host."""


class ParseError(DocumentError):
    """The document bytes could not be parsed — never silently guessed."""


class VerifyError(DocumentError):
    """A saved document failed its verification."""


# --------------------------------------------------------------- helpers


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def sha256_hex(data: bytes) -> str:
    """The document digest — identity, not content."""
    return hashlib.sha256(data).hexdigest()


def sniff_kind(data: bytes, *, name: str = "") -> str:
    """Honest kind detection — magic bytes first, extension second.

    DOCX/PPTX (and XLSX) are ZIP packages: distinguished by their
    ``[Content_Types].xml`` main part, not by hope.  PDF starts with
    ``%PDF-``.  Anything else is ``unknown`` — never guessed.
    """
    if data.startswith(b"%PDF-"):
        return DocumentKind.PDF
    if data[:2] == b"PK":
        main = _zip_main_part(data)
        if main.endswith("wordprocessingml.document.main+xml"):
            return DocumentKind.DOCX
        if main.endswith("presentationml.presentation.main+xml"):
            return DocumentKind.PPTX
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix in (DocumentKind.DOCX, DocumentKind.PPTX, DocumentKind.PDF):
        return suffix
    return DocumentKind.UNKNOWN


def _zip_main_part(data: bytes) -> str:
    """The ``[Content_Types].xml`` main-part ContentType, '' when absent."""
    import io
    from xml.etree import ElementTree

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            raw = zf.read("[Content_Types].xml")
    except (zipfile.BadZipFile, KeyError):
        return ""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return ""
    for override in root.iter(
        "{http://schemas.openxmlformats.org/package/2006/content-types}Override"
    ):
        part = override.get("PartName", "")
        if part in ("/word/document.xml", "/ppt/presentation.xml"):
            return override.get("ContentType", "")
    return ""


# ------------------------------------------------------------ §18 kinds


class DocumentKind:
    """The document kinds this phase serves — verbatim, no extras."""

    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    UNKNOWN = "unknown"


DOCUMENT_KINDS: tuple[str, ...] = (
    DocumentKind.DOCX,
    DocumentKind.PPTX,
    DocumentKind.PDF,
    DocumentKind.UNKNOWN,
)


# ------------------------------------------------------ §18.2 pipeline


#: §18.2 — the pipeline stages after the document itself, verbatim and
#: ordered: ``Document → Parse → Structure → Extract → Index → Memory``.
PIPELINE_STAGES: tuple[str, ...] = ("parse", "structure", "extract", "index", "memory")


class StageState(Enum):
    """A stage verdict — pending / ok / failed / skipped."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class StageTrace:
    """One §18.2 stage's outcome — name, state, an honest detail line."""

    name: str
    state: StageState = StageState.PENDING
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state.value, "detail": self.detail}


# ------------------------------------------------------ parsed document


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One extracted text unit with its location inside the document.

    ``locator`` is the human-facing location (``page 3``, ``slide 2``,
    ``paragraph 7``) — provenance for evidence and index hits.
    """

    text: str
    locator: str = ""
    role: str = "body"  # body | heading | title | bullet | table | caption

    def as_dict(self) -> dict[str, str]:
        return {"text": self.text, "locator": self.locator, "role": self.role}


@dataclass(frozen=True, slots=True)
class StructureNode:
    """One structural unit — a page, a slide, a heading, a section."""

    name: str
    node_type: str = "section"  # page | slide | heading | section
    children: tuple[StructureNode, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type,
            "children": [c.as_dict() for c in self.children],
        }


@dataclass(frozen=True, slots=True)
class ImageRef:
    """One embedded image — an inventory entry, not the bytes."""

    locator: str
    format: str  # png | jpeg | ...
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "locator": self.locator,
            "format": self.format,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """The parse stage's product — structure, text, images, metadata."""

    kind: str
    uri: str
    title: str
    sha256: str
    size_bytes: int
    structure: tuple[StructureNode, ...] = ()
    blocks: tuple[TextBlock, ...] = ()
    images: tuple[ImageRef, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    parser: str = ""

    def text(self) -> str:
        """All block text joined — the extract stage's raw material."""
        return "\n".join(block.text for block in self.blocks if block.text.strip())

    def words(self) -> int:
        return sum(len(block.text.split()) for block in self.blocks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "uri": self.uri,
            "title": self.title,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "words": self.words(),
            "blocks": len(self.blocks),
            "images": [i.as_dict() for i in self.images],
            "structure": [s.as_dict() for s in self.structure],
            "metadata": dict(self.metadata),
            "parser": self.parser,
        }


# ------------------------------------------------------- §18.1 backends


class ParseBackend(ABC):
    """One §18.1 parsing engine behind the NEXUS contract.

    ``name`` is a stable id (events, reports); ``kinds`` lists the
    document kinds it can parse.  ``parse`` returns a
    :class:`ParsedDocument` or raises honestly: ``ParseError`` for
    bytes it cannot read, ``UnsupportedDocumentError`` for kinds it
    does not serve, ``BackendUnavailableError`` when the engine itself
    is not installed.
    """

    name: str
    kinds: tuple[str, ...]

    @abstractmethod
    def parse(self, source: DocumentSource) -> ParsedDocument:
        """Parse one source — honest output or an honest raise."""


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """A document entering the engine — bytes plus provenance."""

    data: bytes
    name: str = ""
    uri: str = ""
    kind: str = ""

    def __post_init__(self) -> None:
        if not self.data:
            raise DocumentError("document source is empty")
        if not self.uri:
            # honest default: bytes without a real path keep a memory://
            # identity — a relative name must not fake a file:// location
            object.__setattr__(
                self, "uri", f"memory://{self.name}" if self.name else "memory://document"
            )
        if not self.kind:
            object.__setattr__(self, "kind", sniff_kind(self.data, name=self.name))

    @classmethod
    def from_path(cls, path: str | Path) -> DocumentSource:
        p = Path(path)
        return cls(data=p.read_bytes(), name=p.name, uri=p.resolve().as_uri())

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "uri": self.uri, "kind": self.kind,
                "size_bytes": str(len(self.data))}


@dataclass(frozen=True, slots=True)
class DocumentVerification:
    """The *verify* verb's product — checks that were actually run."""

    ok: bool
    path: str
    checks: dict[str, bool] = field(default_factory=dict)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "path": self.path, "checks": dict(self.checks),
                "detail": self.detail}
