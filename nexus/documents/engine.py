"""The Document Engine (New Plan §18) — one facade over §18.1–§18.5.

``DocumentEngine`` composes the section the plan names and nothing
more:

* §18.1 — docling (MODE A when installed, MODE B always) plus the
  native stdlib floors (DOCX · PPTX · PDF) behind one
  :class:`ParseBackend` contract;
* §18.2 — the five-stage pipeline (Document → Parse → Structure →
  Extract → Index → Memory) with an honest verdict per stage;
* §18.3/§18.4/§18.5 — the DOCX, PPTX and PDF verbs, thin delegates to
  the native engines;
* memory — :meth:`remember` / :meth:`recall` through the §12 Memory
  Engine, provenance riding every record.

Every operation publishes canonical §2.2 tool events only — counts
travel, document *content* stays out of the bus.

محرك المستندات — واجهة واحدة فوق docling والأرضيات القياسية والسير
الخمسي وأفعال DOCX/PPTX/PDF والذاكرة.

Stdlib only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.events import EventName

from .contracts import (
    DocumentError,
    DocumentSource,
    ParseBackend,
    ParsedDocument,
    ParseError,
    UnsupportedDocumentError,
)
from .docx import DocxDocument, DocxParseBackend
from .memory import DocumentMemory
from .pdf import PdfDocument, PdfParseBackend
from .pipeline import DocumentPipeline, DocumentReport
from .pptx import PptxParseBackend, PptxPresentation


class DocumentEngine:
    """The §18 facade — documents in, structure, index and memory out."""

    source_name = "nexus.documents"

    def __init__(
        self,
        *,
        bus: Any | None = None,
        memory: Any | None = None,
        index: Any | None = None,
        backends: list[ParseBackend] | None = None,
        use_docling: bool = True,
    ) -> None:
        self._bus = bus
        if backends is None:
            backends = []
            if use_docling:
                from .docling import docling_available

                if docling_available().installed:
                    from .docling import DoclingParseBackend

                    backends.append(DoclingParseBackend())
            backends.extend([DocxParseBackend(), PptxParseBackend(), PdfParseBackend()])
        self.backends: list[ParseBackend] = backends
        self._owns_index = index is None
        if index is None:
            from .index import DocumentIndex

            index = DocumentIndex()  # in-memory — real engine, zero setup
        self.index = index
        self._memory = DocumentMemory(memory) if memory is not None else None
        self._pipeline = DocumentPipeline(
            self.backends, index=self.index, memory=self._memory, bus=bus
        )

    # ------------------------------------------------------ §18.1/§18.2

    def parse(self, source: DocumentSource | str | Path) -> ParsedDocument:
        """§18.1 — parse one document; the first serving backend wins."""
        src = self._as_source(source)
        self._emit(
            EventName.TOOL_CALLED, tool="documents.parse", kind=src.kind,
            size_bytes=len(src.data),
        )
        errors: list[str] = []
        for backend in self.backends:
            try:
                parsed = backend.parse(src)
            except UnsupportedDocumentError:
                continue
            except (ParseError, DocumentError) as exc:
                errors.append(f"{backend.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — a backend crash is a parse failure
                errors.append(f"{backend.name}: {type(exc).__name__}: {exc}")
                continue
            self._emit(
                EventName.TOOL_COMPLETED, tool="documents.parse", kind=src.kind,
                parser=backend.name, blocks=len(parsed.blocks),
            )
            return parsed
        self._emit(EventName.TOOL_FAILED, tool="documents.parse", kind=src.kind)
        raise ParseError("; ".join(errors) or f"no backend serves kind {src.kind!r}")

    def ingest(self, source: DocumentSource | str | Path) -> DocumentReport:
        """§18.2 — the five-stage pipeline over one document."""
        src = self._as_source(source)
        self._emit(EventName.TOOL_CALLED, tool="documents.ingest", kind=src.kind,
                   size_bytes=len(src.data))
        report = self._pipeline.run(src)
        self._emit(
            EventName.TOOL_COMPLETED if report.ok else EventName.TOOL_FAILED,
            tool="documents.ingest",
            kind=src.kind,
            reached=report.reached,
            memory_records=report.memory_records,
        )
        return report

    # ------------------------------------------------------------- §18.3

    @staticmethod
    def docx_create() -> DocxDocument:
        """§18.3 *create* — a fresh DOCX model."""
        from .docx import DocxDocument as D

        return D()

    @staticmethod
    def docx_read(path: str | Path) -> DocxDocument:
        """§18.3 *read*."""
        from . import docx as docx_mod

        return docx_mod.read(path)

    @staticmethod
    def docx_save(document: DocxDocument, path: str | Path) -> Path:
        """§18.3 *save*."""
        return document.save(path)

    @staticmethod
    def docx_verify(path: str | Path, *, expect_text: str = "") -> Any:
        """§18.3 *verify*."""
        from . import docx as docx_mod

        return docx_mod.verify(path, expect_text=expect_text)

    # ------------------------------------------------------------- §18.4

    @staticmethod
    def pptx_create(
        *, width_emu: int | None = None, height_emu: int | None = None
    ) -> PptxPresentation:
        """§18.4 *create* — a fresh presentation (default 16:9)."""
        pres = PptxPresentation()
        if width_emu is not None:
            pres.width_emu = width_emu
        if height_emu is not None:
            pres.height_emu = height_emu
        return pres

    @staticmethod
    def pptx_read(path: str | Path) -> PptxPresentation:
        """§18.4 — read slides back, in presentation order."""
        from . import pptx as pptx_mod

        return pptx_mod.read(path)

    @staticmethod
    def pptx_sources(presentation: PptxPresentation) -> list[dict[str, Any]]:
        """§18.4 *sources* — per-slide text provenance."""
        return presentation.sources()

    @staticmethod
    def pptx_save(presentation: PptxPresentation, path: str | Path) -> Path:
        """§18.4 *save*."""
        return presentation.save(path)

    @staticmethod
    def pptx_verify(
        path: str | Path, *, expect_titles: list[str] | None = None
    ) -> Any:
        """§18.4 *verify*."""
        from . import pptx as pptx_mod

        return pptx_mod.verify(path, expect_titles=expect_titles)

    # ------------------------------------------------------------- §18.5

    @staticmethod
    def pdf_read(source: bytes | str | Path) -> PdfDocument:
        """§18.5 *read* — parse a real PDF (bytes or path)."""
        from . import pdf as pdf_mod

        data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
        return pdf_mod.parse_pdf(data)

    @staticmethod
    def pdf_search(document: PdfDocument, term: str) -> list[dict[str, Any]]:
        """§18.5 *search*."""
        from . import pdf as pdf_mod

        return pdf_mod.search(document, term)

    @staticmethod
    def pdf_extract(document: PdfDocument, *, page: int | None = None) -> str:
        """§18.5 *extract*."""
        from . import pdf as pdf_mod

        return pdf_mod.extract(document, page=page)

    @staticmethod
    def pdf_summarize(document: PdfDocument, *, max_sentences: int = 5) -> list[str]:
        """§18.5 *summarize* — extractive, ordered, honest."""
        from . import pdf as pdf_mod

        return pdf_mod.summarize(document, max_sentences=max_sentences)

    @staticmethod
    def pdf_analyze(document: PdfDocument) -> dict[str, Any]:
        """§18.5 *analyze*."""
        from . import pdf as pdf_mod

        return pdf_mod.analyze(document)

    # ------------------------------------------------------------ memory

    def remember(
        self,
        report: DocumentReport | ParsedDocument,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
    ) -> list[dict[str, Any]]:
        """§18.2 *memory* — persist one document with its provenance."""
        if self._memory is None:
            raise DocumentError(
                "document memory needs a §12 MemoryEngine — pass memory=DocumentEngine(...)"
            )
        parsed = report.document if isinstance(report, DocumentReport) else report
        if parsed is None:
            raise DocumentError("the report holds no parsed document to remember")
        written = self._memory.remember(
            parsed, project=project, workspace=workspace, task=task, session=session
        )
        if self._bus is not None and written:
            self._bus.publish(
                EventName.MEMORY_CREATED,
                payload={"tool": "documents.remember", "records": len(written)},
                source=self.source_name,
            )
        return written

    def recall(
        self,
        prompt: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """§18.2 *memory* — search what documents remembered."""
        if self._memory is None:
            raise DocumentError(
                "document memory needs a §12 MemoryEngine — pass memory=DocumentEngine(...)"
            )
        return self._memory.recall(
            prompt, project=project, workspace=workspace, task=task, session=session, limit=limit
        )

    # ------------------------------------------------------------ plumbing

    def _as_source(self, source: DocumentSource | str | Path) -> DocumentSource:
        if isinstance(source, DocumentSource):
            return source
        path = Path(source)
        return DocumentSource.from_path(path)

    def _emit(self, name: EventName, **payload: Any) -> None:
        if self._bus is None:
            return
        self._bus.publish(name, payload=payload, source=self.source_name)

    def close(self) -> None:
        """Release owned resources — the WinError-32 law, kept."""
        if self._owns_index and hasattr(self.index, "close"):
            self.index.close()

    def __enter__(self) -> DocumentEngine:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
