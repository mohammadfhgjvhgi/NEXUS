"""Phase 17 · the §17 facade — providers in, verified evidence out, events clean."""

from __future__ import annotations

from pathlib import Path

from fixtures import SurfaceServer, make_docs_corpus

from nexus.events import EventBus
from nexus.research import (
    SCORED_SHAPE,
    SOURCE_CLASSES,
    SOURCE_KINDS,
    WORKFLOW_STAGES,
    ResearchEngine,
    WebSearchProvider,
)


def build_engine(server: SurfaceServer, tmp_path: Path, **kwargs: object) -> ResearchEngine:
    providers: list[object] = [
        WebSearchProvider(f"{server.base}/web"),
    ]
    docs = make_docs_corpus(tmp_path)
    from nexus.research import DocsSearchProvider

    providers.append(DocsSearchProvider([docs]))
    memory = None
    if kwargs.get("memory") is not None:
        memory = kwargs["memory"]
    return ResearchEngine(providers, bus=kwargs.get("bus"), memory=memory)  # type: ignore[arg-type]


def test_contract_cardinality_constant() -> None:
    assert SCORED_SHAPE == {
        "source_kinds": 5,
        "source_classes": 6,
        "workflow_stages": 8,
        "confidence_dimensions": 4,
    }
    assert len(SOURCE_KINDS) == 5 and len(SOURCE_CLASSES) == 6 and len(WORKFLOW_STAGES) == 8


def test_end_to_end_run_produces_verified_findings(server: SurfaceServer, tmp_path: Path) -> None:
    engine = build_engine(server, tmp_path)
    report = engine.run("7B gguf ram", min_corroboration=2)
    assert report.ok and report.reached == "evidence"
    assert report.verified, "docs+web agree on this fixture"
    best = report.verified[0]
    rows = report.evidence_of(best)
    assert rows and all(row.uri for row in rows)


def test_events_stay_canonical(server: SurfaceServer, tmp_path: Path) -> None:
    bus = EventBus()
    engine = build_engine(server, tmp_path, bus=bus)
    engine.run("7B gguf ram")
    names = {event.name for event in bus.history_snapshot()}
    assert names <= {"tool.called", "tool.completed", "tool.failed"}, names


def test_events_carry_counts_not_content(server: SurfaceServer, tmp_path: Path) -> None:
    bus = EventBus()
    engine = build_engine(server, tmp_path, bus=bus)
    engine.run("a-very-secret-query-token-xyz")
    for event in bus.history_snapshot():
        blob = repr(event.payload)
        assert "a-very-secret-query-token-xyz" not in blob, "query text never rides the bus"


def test_remember_and_recall_roundtrip(server: SurfaceServer, tmp_path: Path) -> None:
    from nexus.memory import MemoryEngine, SQLiteMemoryStore

    memory = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))
    engine = build_engine(server, tmp_path, memory=memory)
    report = engine.run("7B gguf ram", min_corroboration=2)
    written = engine.remember(report, project="rag", task="t-7")
    assert written, "findings + summary are written"
    rows = engine.recall("gguf ram", task="t-7")
    assert rows and rows[0]["sources"], "recall keeps the sources"


def test_research_verb_alias(server: SurfaceServer, tmp_path: Path) -> None:
    engine = build_engine(server, tmp_path)
    report = engine.research("llama.cpp gguf")
    assert report.ok


def test_add_provider_extends_the_fanout(server: SurfaceServer, tmp_path: Path) -> None:
    engine = build_engine(server, tmp_path)
    before = engine.run("7B gguf ram").stage("search").detail
    from nexus.research import DocsSearchProvider

    extra = make_docs_corpus(tmp_path / "second")
    engine.add_provider(DocsSearchProvider([extra]))
    after = engine.run("7B gguf ram").stage("search").detail
    assert after.count("=") > before.count("="), "the new surface joined the fan-out"
