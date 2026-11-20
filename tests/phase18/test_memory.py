"""Phase 18 · §18.2 memory stage — documents persist with provenance (§12)."""

from __future__ import annotations

import pytest
from fixtures import build_pdf

from nexus.documents import DocumentError, DocumentSource
from nexus.documents.memory import DocumentMemory
from nexus.documents.pdf import PdfParseBackend
from nexus.memory import MemoryEngine, MemoryQuery, MemoryType, SQLiteMemoryStore


def _memory(tmp_path):
    return MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))


def _parsed(tmp_path):
    from nexus.documents.pipeline import DocumentPipeline

    path = build_pdf(tmp_path / "d.pdf")
    report = DocumentPipeline([PdfParseBackend()]).run(DocumentSource.from_path(path))
    assert report.document is not None
    return report.document


def test_remember_and_recall_keeps_sources(tmp_path) -> None:
    memory = _memory(tmp_path)
    bridge = DocumentMemory(memory)
    parsed = _parsed(tmp_path)
    written = bridge.remember(parsed, task="doc-task")
    assert len(written) == 2  # document fact + session summary

    rows = bridge.recall("NEXUS document", task="doc-task")
    assert rows
    fact = next(r for r in rows if r["type"] == MemoryType.FACT)
    assert fact["sources"], "provenance rides the record"
    assert fact["sources"][0]["method"] == "document"
    assert fact["sources"][0]["uri"] == parsed.uri
    memory.close()


def test_scope_law_task_isolation(tmp_path) -> None:
    memory = _memory(tmp_path)
    bridge = DocumentMemory(memory)
    parsed = _parsed(tmp_path)
    bridge.remember(parsed, task="task-a")
    assert bridge.recall("document", task="task-b") == []
    assert bridge.recall("document", task="task-a")
    memory.close()


def test_summary_record_exists(tmp_path) -> None:
    memory = _memory(tmp_path)
    bridge = DocumentMemory(memory)
    parsed = _parsed(tmp_path)
    bridge.remember(parsed, project="proj")
    hits = memory.search(MemoryQuery(text="document ingest session", project="proj"))
    assert any(h.record.type == MemoryType.SUMMARY for h in hits)
    memory.close()


def test_bridge_requires_a_memory_engine() -> None:
    with pytest.raises(TypeError):
        DocumentMemory(None)
    with pytest.raises(TypeError):
        DocumentMemory(object())


def test_engine_remember_without_memory_is_honest(tmp_path) -> None:
    from nexus.documents import DocumentEngine

    engine = DocumentEngine(index=None, use_docling=False)
    path = build_pdf(tmp_path / "d.pdf")
    report = engine.ingest(path)
    assert report.document is not None
    with pytest.raises(DocumentError):
        engine.remember(report)
    engine.close()


def test_snippet_comes_from_first_blocks(tmp_path) -> None:
    memory = _memory(tmp_path)
    bridge = DocumentMemory(memory)
    parsed = _parsed(tmp_path)
    bridge.remember(parsed, task="snip")
    rows = bridge.recall("document", task="snip")
    fact = next(r for r in rows if r["type"] == MemoryType.FACT)
    assert fact["sources"][0]["snippet"].strip()
    memory.close()
