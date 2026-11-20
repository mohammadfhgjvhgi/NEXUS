"""Phase 18 · §18.2 pipeline — five stages, honest verdicts, canonical events."""

from __future__ import annotations

from fixtures import PDF_PAGE_1, build_docx, build_pdf, write_pdf

from nexus.documents import (
    PIPELINE_STAGES,
    DocumentSource,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StageState,
)
from nexus.documents.index import DocumentIndex
from nexus.documents.pipeline import DocumentPipeline


def test_stages_verbatim_and_ordered(tmp_path) -> None:
    path = build_docx(tmp_path / "d.docx")
    report = DocumentPipeline([]).run(DocumentSource.from_path(path))
    assert [s.name for s in report.stages] == list(PIPELINE_STAGES)
    assert report.stage("parse").state is StageState.FAILED
    assert not report.ok


def test_full_run_with_index_and_memory(tmp_path) -> None:
    from nexus.documents.docx import DocxParseBackend
    from nexus.documents.memory import DocumentMemory
    from nexus.documents.pdf import PdfParseBackend
    from nexus.documents.pptx import PptxParseBackend
    from nexus.memory import MemoryEngine, SQLiteMemoryStore

    path = build_docx(tmp_path / "d.docx")
    memory = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))
    pipeline = DocumentPipeline(
        [DocxParseBackend(), PptxParseBackend(), PdfParseBackend()],
        index=DocumentIndex(),
        memory=DocumentMemory(memory),  # the pipeline speaks the bridge contract
    )
    report = pipeline.run(DocumentSource.from_path(path))
    assert report.ok, [s.as_dict() for s in report.stages]
    assert report.reached == "memory"
    assert report.index_id is not None
    assert report.memory_records == 2  # the document + the session summary
    assert report.document is not None and report.document.words() > 0
    memory.close()


def test_index_and_memory_skipped_when_unbound(tmp_path) -> None:
    from nexus.documents.docx import DocxParseBackend
    from nexus.documents.pdf import PdfParseBackend
    from nexus.documents.pptx import PptxParseBackend

    path = build_docx(tmp_path / "d.docx")
    report = DocumentPipeline(
        [DocxParseBackend(), PptxParseBackend(), PdfParseBackend()]
    ).run(DocumentSource.from_path(path))
    assert report.stage("index").state is StageState.SKIPPED
    assert report.stage("index").detail == "no index bound"
    assert report.stage("memory").state is StageState.SKIPPED
    assert report.ok, "unbound stages were never promised — skips don't fail the run"


def test_pdf_flows_to_memory_stage(tmp_path) -> None:
    from nexus.documents.docx import DocxParseBackend
    from nexus.documents.pdf import PdfParseBackend
    from nexus.documents.pptx import PptxParseBackend

    path = build_pdf(tmp_path / "d.pdf")
    report = DocumentPipeline(
        [DocxParseBackend(), PptxParseBackend(), PdfParseBackend()],
        index=DocumentIndex(),
    ).run(DocumentSource.from_path(path))
    assert report.stage("parse").state is StageState.OK
    assert "native.pdf" in report.stage("parse").detail
    assert report.stage("memory").state is StageState.SKIPPED
    assert report.index_id is not None


def test_garbage_fails_honestly_at_parse() -> None:
    report = DocumentPipeline(
        [_NoopBackend()]
    ).run(DocumentSource(data=b"garbage-not-a-document", name="g.bin"))
    assert report.stage("parse").state is StageState.FAILED
    assert report.errors
    assert not report.ok


def test_backend_crash_recorded_not_hidden() -> None:
    class Crashy(ParseBackend):
        name = "crashy"
        kinds = ("docx", "pptx", "pdf", "unknown")

        def parse(self, source: DocumentSource) -> ParsedDocument:
            raise RuntimeError("backend exploded")

    report = DocumentPipeline([Crashy()]).run(
        DocumentSource(data=b"%PDF-1.4 bytes", name="x.pdf")
    )
    assert report.stage("parse").state is StageState.FAILED
    assert "backend exploded" in report.stage("parse").detail


def test_events_canonical_and_content_free(tmp_path) -> None:
    from nexus.documents.docx import DocxParseBackend
    from nexus.documents.pdf import PdfParseBackend
    from nexus.documents.pptx import PptxParseBackend
    from nexus.events import EventBus

    bus = EventBus()
    path = build_docx(tmp_path / "d.docx")
    pipeline = DocumentPipeline(
        [DocxParseBackend(), PptxParseBackend(), PdfParseBackend()],
        index=DocumentIndex(),
        bus=bus,
    )
    pipeline.run(DocumentSource.from_path(path))
    names = {event.name for event in bus.history_snapshot()}
    assert names <= {"tool.completed", "tool.failed"}, names
    blob = repr([event.payload for event in bus.history_snapshot()])
    assert "runtime objects" not in blob, "document content never rides the bus"


def test_pdf_fixture_writer_roundtrip(tmp_path) -> None:
    """The fixture writer makes real PDFs the native parser reads back."""
    data = write_pdf([PDF_PAGE_1], title="roundtrip")
    src = DocumentSource(data=data, name="r.pdf")
    from nexus.documents.pdf import PdfParseBackend

    parsed = PdfParseBackend().parse(src)
    assert parsed.blocks and "AVX" in parsed.blocks[0].text


class _NoopBackend(ParseBackend):
    """A backend that honestly refuses everything — for the failure path."""

    name = "noop"
    kinds = ("docx", "pptx", "pdf", "unknown")

    def parse(self, source: DocumentSource) -> ParsedDocument:
        raise ParseError("cannot read this")
