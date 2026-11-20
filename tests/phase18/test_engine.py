"""Phase 18 · the DocumentEngine facade — §18.1–§18.5 composed."""

from __future__ import annotations

import pytest
from fixtures import PDF_PAGE_1, build_docx, build_pdf, build_pptx, write_pdf

from nexus.documents import (
    PIPELINE_STAGES,
    DocumentEngine,
    DocumentError,
    DocumentKind,
    ParsedDocument,
    ParseError,
)


def _engine(**kwargs: object) -> DocumentEngine:
    """An engine with the native floors only — docling absence is the norm."""
    return DocumentEngine(use_docling=False, **kwargs)


def test_native_floors_always_registered() -> None:
    engine = _engine()
    names = [b.name for b in engine.backends]
    assert names == ["native.docx", "native.pptx", "native.pdf"]
    engine.close()


def test_parse_picks_the_serving_backend(tmp_path) -> None:
    engine = _engine()
    path = build_pdf(tmp_path / "d.pdf")
    parsed = engine.parse(path)
    assert isinstance(parsed, ParsedDocument)
    assert parsed.kind == DocumentKind.PDF and parsed.parser == "native.pdf"
    engine.close()


def test_parse_garbage_raises_honest_aggregate(tmp_path) -> None:
    engine = _engine()
    bogus = tmp_path / "bogus.pdf"
    bogus.write_bytes(b"%PDF-1.4 nonsense body, no objects")
    with pytest.raises(ParseError) as excinfo:
        engine.parse(bogus)
    assert "native.pdf" in str(excinfo.value)
    engine.close()


def test_ingest_runs_all_five_stages(tmp_path) -> None:
    engine = _engine()
    path = build_docx(tmp_path / "d.docx")
    report = engine.ingest(path)
    assert [s.name for s in report.stages] == list(PIPELINE_STAGES)
    assert report.stage("memory").state.value == "skipped"  # no memory bound
    assert report.index_id is not None
    hits = engine.index.search("documents runtime")
    assert hits and hits[0]["locator"].startswith("paragraph")
    engine.close()


def test_ingest_with_memory_end_to_end(tmp_path) -> None:
    from nexus.memory import MemoryEngine, MemoryType, SQLiteMemoryStore

    memory = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))
    engine = _engine(memory=memory)
    path = build_pdf(tmp_path / "d.pdf")
    report = engine.ingest(path)
    assert report.ok, [s.as_dict() for s in report.stages]
    assert report.memory_records == 2
    rows = engine.recall("NEXUS windows")
    assert rows
    fact = next(r for r in rows if r["type"] == MemoryType.FACT)
    assert fact["sources"], "the fact keeps its document provenance"
    assert fact["sources"][0]["method"] == "document"
    memory.close()
    engine.close()


def test_pdf_verbs_through_the_facade(tmp_path) -> None:
    engine = _engine()
    doc = engine.pdf_read(write_pdf([PDF_PAGE_1], title="facade"))
    assert engine.pdf_search(doc, "AVX")
    assert "Windows" in engine.pdf_extract(doc, page=1)
    assert engine.pdf_summarize(doc)
    analysis = engine.pdf_analyze(doc)
    assert analysis["pages"] == 1
    engine.close()


def test_pptx_and_docx_verbs_through_the_facade(tmp_path) -> None:
    engine = _engine()
    pptx_path = build_pptx(tmp_path / "d.pptx")
    pres = engine.pptx_read(pptx_path)
    sources = engine.pptx_sources(pres)
    assert [s["title"] for s in sources] == [
        "NEXUS Documents",
        "Pipeline",
        "Proof",
    ]
    verdict = engine.pptx_verify(pptx_path, expect_titles=[s["title"] for s in sources])
    assert verdict.ok

    docx_path = build_docx(tmp_path / "d.docx")
    document = engine.docx_read(docx_path)
    assert engine.docx_verify(docx_path, expect_text=document.paragraphs[0].text).ok
    engine.close()


def test_events_stay_canonical(tmp_path) -> None:
    from nexus.events import EventBus

    bus = EventBus()
    engine = _engine(bus=bus)
    engine.ingest(build_pdf(tmp_path / "d.pdf"))
    names = {event.name for event in bus.history_snapshot()}
    assert names <= {"tool.called", "tool.completed", "tool.failed"}, names
    blob = repr([event.payload for event in bus.history_snapshot()])
    assert "AVX" not in blob, "pdf content never rides the bus"
    engine.close()


def test_engine_close_releases_the_index(tmp_path) -> None:
    import sqlite3

    engine = _engine()
    engine.close()
    with pytest.raises(sqlite3.ProgrammingError):
        engine.index.stats()


def test_remember_without_memory_raises(tmp_path) -> None:
    engine = _engine()
    path = build_pdf(tmp_path / "d.pdf")
    report = engine.ingest(path)
    with pytest.raises(DocumentError):
        engine.remember(report)
    engine.close()
