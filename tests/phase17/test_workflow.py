"""Phase 17 · §17.2 — the eight-stage workflow: order, verdicts, honesty."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import SurfaceServer

from nexus.research import (
    WORKFLOW_STAGES,
    Finding,
    ProviderError,
    ResearchError,
    ResearchWorkflow,
    SearchHit,
    SearchProvider,
    SourceKind,
    StageState,
)
from nexus.research.providers import WebSearchProvider


class StaticProvider(SearchProvider):
    """A scripted surface — hits and/or raises, deterministically."""

    kind = SourceKind.WEB

    def __init__(self, name: str, batches: list[dict[str, str]] | None = None,
                 error: Exception | None = None) -> None:
        self.name = name
        self.batch = batches or []
        self.error = error

    def search(self, query: str, *, max_results: int = 10) -> list:  # noqa: ANN201
        if self.error is not None:
            raise self.error
        return [SearchHit(title=row["title"], uri=row["uri"], snippet=row["snippet"],
                          provider=self.name, kind=self.kind)
                for row in self.batch[: max(1, max_results)]]


def hit(title: str, uri: str, snippet: str, provider: str = "web") -> dict[str, str]:
    return {"title": title, "uri": uri, "snippet": snippet, "provider": provider}


def test_stage_vocabulary_is_verbatim_and_ordered() -> None:
    assert WORKFLOW_STAGES == (
        "query", "search", "collect", "deduplicate", "rank", "compare", "verify", "evidence",
    )


def test_empty_query_fails_at_query_stage() -> None:
    report = ResearchWorkflow([StaticProvider("web", [hit("t", "u", "s")])]).run("   ")
    assert report.stage("query").state is StageState.FAILED
    assert not report.ok and report.reached == "query"


def test_no_providers_fails_at_search_stage() -> None:
    report = ResearchWorkflow([]).run("llama.cpp")
    assert report.stage("search").state is StageState.FAILED
    assert report.reached == "search" and not report.ok


def test_every_surface_failing_is_a_search_failure() -> None:
    broken = StaticProvider("web", error=ProviderError("down"))
    report = ResearchWorkflow([broken]).run("llama.cpp")
    assert report.stage("search").state is StageState.FAILED
    assert "down" in report.errors[0]


def test_one_failing_surface_never_sinks_the_run(server: SurfaceServer) -> None:
    broken = StaticProvider("ghost", error=ProviderError("unreachable"))
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([broken, web]).run("llama.cpp gguf ram")
    assert report.stage("search").state is StageState.OK
    assert "ghost" in report.errors[0], "the failure is recorded, not hidden"
    assert report.ok and report.findings


def test_deduplicate_collapses_uri_and_content_duplicates(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("llama.cpp gguf ram")
    dedup = report.stage("deduplicate")
    assert dedup.state is StageState.OK
    # the fixture ships the same URI twice (5 raw) — dedup keeps 4 unique
    assert dedup.detail.startswith("5 → 4")


def test_rank_orders_by_confidence_score(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("gguf 7B ram", max_per_provider=10)
    scores = [f.best.score for f in report.findings]
    assert scores == sorted(scores, reverse=True)
    assert report.stage("rank").state is StageState.OK


def test_compare_clusters_agreeing_sources(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("7B gguf model ram", max_per_provider=10)
    corroborated = [f for f in report.findings if f.distinct_sources >= 2]
    assert corroborated, "docs+blog+forum agree that a 7B Q4 needs ~4 GB"
    assert all(f.mean_authority > 0 for f in report.findings)


def test_compare_surfaces_conflicting_numbers() -> None:
    a = StaticProvider("web", [hit("Model RAM", "https://a/x", "a 7B model needs 4 GB ram",
                                   provider="a")])
    b = StaticProvider("forums", [hit("Model RAM", "https://b/y",
                                      "a 7B model needs 64 GB ram", provider="b")])
    report = ResearchWorkflow([a, b]).run("7B model ram", min_corroboration=99)
    assert report.conflicts, "4 GB vs 64 GB on the same claim must conflict"
    assert "conflicting numbers" in report.conflicts[0]


def test_verify_requires_corroboration_and_authority(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    solo = ResearchWorkflow([web]).run("7B gguf ram", min_corroboration=99)
    assert solo.stage("verify").detail.startswith("0/"), "no corroboration, no verification"
    duo = ResearchWorkflow([web]).run("7B gguf ram", min_corroboration=2)
    assert duo.verified, "independent agreement verifies"


def test_verify_rejects_low_authority_even_when_corroborated() -> None:
    a = StaticProvider("blog", [hit("topic x", "https://p1.wordpress.com/a", "topic x facts 4 GB",
                                    provider="blog")])
    b = StaticProvider("blog2", [hit("topic x", "https://p2.wordpress.com/b", "topic x facts 4 GB",
                                     provider="blog2")])
    report = ResearchWorkflow([a, b]).run("topic x facts", min_corroboration=2, min_authority=0.5)
    assert report.findings, "the cluster exists"
    assert not report.verified, "two personal blogs corroborate but lack authority"


def test_conflicted_findings_never_verify() -> None:
    a = StaticProvider("web", [hit("Model RAM", "https://a/x", "a 7B model needs 4 GB ram")])
    b = StaticProvider("forums", [hit("Model RAM", "https://b/y", "a 7B model needs 64 GB ram")])
    c = StaticProvider("docs", [hit("Model RAM", "https://c/z", "a 7B model needs 4 GB ram")])
    report = ResearchWorkflow([a, b, c]).run("7B model ram")
    assert report.conflicts
    assert not report.verified, "a contested claim stays unverified — §verify's honesty"


def test_evidence_attaches_rows_with_addresses(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    report = ResearchWorkflow([web]).run("7B gguf ram")
    for finding in report.findings:
        rows = report.evidence_of(finding)
        assert rows
        for row in rows:
            assert row.uri and row.source_class in ("official", "documentation", "academic",
                                                    "community", "personal", "unknown")


def test_report_reached_and_ok_law(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    good = ResearchWorkflow([web]).run("llama.cpp gguf ram")
    assert good.ok and good.reached == "evidence"
    empty = ResearchWorkflow([StaticProvider("web", [])]).run("llama.cpp")
    assert not empty.ok and not empty.findings
    assert empty.stage("search").state is StageState.OK, (
        "zero results is OK at search — the report walks through honestly empty"
    )


def test_report_stage_unknown_name_raises() -> None:
    report = ResearchWorkflow([]).run("x")
    with pytest.raises(ResearchError):
        report.stage("nope")


def test_report_to_dict_is_complete(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    data = ResearchWorkflow([web]).run("7B gguf ram").to_dict()
    for key in ("query", "terms", "reached", "ok", "stages", "findings", "conflicts", "errors"):
        assert key in data
    assert len(data["stages"]) == 8
    if data["findings"]:
        assert "evidence" in data["findings"][0]


def test_workflow_rejects_unknown_provider_kind() -> None:
    class Weird(SearchProvider):
        name = "weird"
        kind = "darknet"

        def search(self, query: str, *, max_results: int = 10) -> list:
            return []

    with pytest.raises(ResearchError, match="darknet"):
        ResearchWorkflow([Weird()])

def test_finding_shape(tmp_path: Path) -> None:
    finding = Finding(claim="c", hits=(), terms=("t",))
    assert finding.distinct_sources == 0 and finding.mean_authority == 0.0
    data = finding.as_dict(verified=False)
    assert data["verified"] is False and data["evidence"] == []
