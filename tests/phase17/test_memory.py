"""Phase 17 · §17.5 — research memory: findings persist with their sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fixtures import SurfaceServer

from nexus.memory import MemoryEngine, MemoryType, SQLiteMemoryStore
from nexus.research import ResearchError, ResearchMemory, ResearchWorkflow
from nexus.research.providers import WebSearchProvider


def make_memory(tmp_path: Path) -> MemoryEngine:
    return MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))


def filled_memory(server: SurfaceServer, tmp_path: Path) -> MemoryEngine:
    engine = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("7B gguf ram", min_corroboration=2)
    assert report.verified, "the fixture must verify before memory tests mean anything"
    ResearchMemory(engine).remember(
        report, project="rag-tool", task="t-42", workspace="ws-1",
    )
    return engine


def test_remember_requires_a_memory_engine() -> None:
    with pytest.raises(TypeError):
        ResearchMemory(None)  # type: ignore[arg-type]


def test_remember_writes_findings_with_research_evidence(server: SurfaceServer,
                                                         tmp_path: Path) -> None:
    engine = filled_memory(server, tmp_path)
    from nexus.memory import MemoryQuery

    hits = engine.search(MemoryQuery(text="gguf ram", task="t-42", project="rag-tool", limit=20))
    facts = [h.record for h in hits if h.record.type == MemoryType.FACT]
    assert facts, "the finding is remembered"
    for record in facts:
        assert record.source == "research"
        assert record.task == "t-42" and record.project == "rag-tool"
        assert record.evidence, "§17.5: the source rides the record"
        for row in record.evidence:
            assert row.method == "research" and row.uri


def test_remember_writes_the_session_summary(server: SurfaceServer, tmp_path: Path) -> None:
    engine = filled_memory(server, tmp_path)
    from nexus.memory import MemoryQuery

    hits = engine.search(
        MemoryQuery(text="research session", task="t-42", project="rag-tool", limit=20)
    )
    summaries = [h.record for h in hits if h.record.type == MemoryType.SUMMARY]
    assert summaries and "research session" in summaries[0].content
    assert "findings" in summaries[0].content


def test_scope_law_task_beats_project_beats_knowledge(server: SurfaceServer,
                                                      tmp_path: Path) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("7B gguf ram", min_corroboration=2)
    memory = ResearchMemory(make_memory(tmp_path))
    by_task = memory.remember(report, project="p", task="t")
    assert by_task
    knowledge_only = memory.remember(report)
    assert knowledge_only


def test_verified_only_and_min_confidence_filters(server: SurfaceServer, tmp_path: Path) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("7B gguf ram", min_corroboration=2)
    memory = ResearchMemory(make_memory(tmp_path))
    strict = memory.remember(report, verified_only=True, min_confidence=0.9)
    assert strict, "verified findings score above 0.9 on this fixture"
    for entry in strict[:-1]:  # the summary always rides along
        assert entry["score"] >= 0.9


def test_recall_returns_records_with_sources(server: SurfaceServer, tmp_path: Path) -> None:
    engine = filled_memory(server, tmp_path)
    rows: list[dict[str, Any]] = ResearchMemory(engine).recall("gguf ram", task="t-42")
    assert rows, "what research remembered is recallable"
    row = rows[0]
    assert row["sources"] and row["sources"][0]["method"] == "research"
    assert row["sources"][0]["uri"]


def test_recall_respects_task_scope(server: SurfaceServer, tmp_path: Path) -> None:
    engine = filled_memory(server, tmp_path)
    rows = ResearchMemory(engine).recall("gguf ram", task="some-other-task")
    assert not rows, "another task does not see this task's research"


def test_engine_remember_requires_memory() -> None:
    from nexus.research import ResearchEngine

    engine: ResearchEngine = ResearchEngine([])
    report = engine.run("anything")
    with pytest.raises(ResearchError, match="MemoryEngine"):
        engine.remember(report)
