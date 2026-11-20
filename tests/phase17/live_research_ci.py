#!/usr/bin/env python3
"""Phase 17 live proof — real surfaces, a real workflow, a real memory (CI-safe).

What this proves, on a real machine, with the real network and real files:

1. §17.1 *github* — a real GitHub repository search over api.github.com
   (public, credential-free, §124 unchanged);
2. §17.1 *web* — a real public HTTP search endpoint (the Wikipedia
   search API, then the DuckDuckGo Instant Answer API — both keyless;
   the rung holds when either answers, fails when neither does);
3. §17.1 *docs* + *local files* — this repository's own docs/ and
   nexus/ trees, walked for real;
4. §17.2 — the eight-stage workflow over all four surfaces, honest
   stage verdicts, dedup/rank/compare/verify all live;
5. §17.4 — the four dimensions computed and reported;
6. §17.5 — verified findings remembered into a real SQLite §12 memory
   and recalled back with their sources.

Exit code 0 only if every rung held.  No secrets, no tokens — public
network paths only.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nexus.github import GitHubClient, GitHubEngine  # noqa: E402
from nexus.memory import MemoryEngine, SQLiteMemoryStore  # noqa: E402
from nexus.research import (  # noqa: E402
    WORKFLOW_STAGES,
    DocsSearchProvider,
    GitHubSearchProvider,
    LocalSearchProvider,
    ResearchEngine,
    WebSearchProvider,
)

RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def rung_1_github_surface(engine: GitHubEngine) -> None:
    provider = GitHubSearchProvider(engine)
    hits = provider.search("llama.cpp gguf", max_results=5)
    record(
        "17.1 github: real api.github.com repository search",
        bool(hits) and hits[0].metadata.get("github_type") == "repo",
        f"{len(hits)} hits · {hits[0].uri if hits else 'none'}",
    )


def rung_2_web_surface() -> WebSearchProvider | None:
    """Real public web search — keyless endpoints, first that answers wins."""
    engines: list[WebSearchProvider] = [
        WebSearchProvider(
            "https://en.wikipedia.org/w/api.php",
            query_param="srsearch",
            result_key="query.search",
            field_map={"title": "title", "uri": "title", "snippet": "snippet"},
            uri_template="https://en.wikipedia.org/wiki/{title}",
            strip_html=True,
            extra_params={"action": "query", "list": "search", "format": "json",
                          "srlimit": "5"},
            timeout=20.0,
        ),
        WebSearchProvider(
            "https://api.duckduckgo.com/",
            result_key="RelatedTopics",
            field_map={"title": "Text", "uri": "FirstURL", "snippet": "Text"},
            extra_params={"format": "json", "no_html": "1"},
            timeout=20.0,
        ),
    ]
    errors: list[str] = []
    for engine in engines:
        try:
            hits = engine.search("gguf model inference")
            if not hits:
                errors.append(f"{engine.name}: empty")
                continue
            record(
                "17.1 web: real public search endpoint",
                True,
                f"{len(hits)} hits · {engine.base_url.split('/')[2]} · {hits[0].uri[:48]}",
            )
            return engine
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{engine.name}: {exc}")
    record("17.1 web: real public search endpoint", False, " ; ".join(errors)[:120])
    return None


def rung_3_corpus_surfaces() -> tuple[DocsSearchProvider, LocalSearchProvider]:
    docs = DocsSearchProvider([ROOT / "docs"])
    local = LocalSearchProvider([ROOT / "nexus"])
    doc_hits = docs.search("research engine exit criteria")
    local_hits = local.search("research workflow stages")
    record(
        "17.1 docs+local: the repository's own trees answer",
        bool(doc_hits) and bool(local_hits),
        f"docs={len(doc_hits)} local={len(local_hits)}",
    )
    return docs, local


def rung_4_workflow_stages(engine: ResearchEngine) -> None:
    report = engine.run("local LLM inference gguf", min_corroboration=1, top_k=8)
    stages_ok = all(t.state.value in ("ok", "skipped") for t in report.stages)
    record(
        "17.2 workflow: eight stages walked with verdicts",
        len(report.stages) == len(WORKFLOW_STAGES) and stages_ok,
        f"reached={report.reached} findings={len(report.findings)}",
    )
    return None if not report.findings else report  # type: ignore[return-value]


def rung_5_confidence_dimensions(report: object) -> None:
    findings = getattr(report, "findings", ())
    if not findings:
        record("17.4 confidence: four dimensions reported", False, "no findings to grade")
        return
    best = findings[0].best
    breakdown = best.confidence.breakdown()
    record(
        "17.4 confidence: authority/relevance/freshness/evidence all present",
        set(breakdown) == {"authority", "relevance", "freshness", "evidence"},
        f"score={best.score} class={best.source_class}",
    )


def rung_6_memory_roundtrip(report: object) -> None:
    with tempfile.TemporaryDirectory() as raw:
        memory = MemoryEngine(SQLiteMemoryStore(str(Path(raw) / "mem.sqlite")))
        try:
            engine = ResearchEngine([], memory=memory)
            written = engine.remember(report, project="phase17-live", task="live-proof")  # type: ignore[arg-type]
            rows = engine.recall("gguf inference", task="live-proof")
            record(
                "17.5 memory: findings remembered and recalled with sources",
                bool(written) and bool(rows) and bool(rows[0]["sources"]),
                f"records={len(written)} recalled={len(rows)}",
            )
        finally:
            # Real-Windows law (phase16 pattern): an open SQLite handle keeps
            # the file locked (WinError 32) — close before temp cleanup.
            memory.close()


def main() -> int:
    print("=" * 66)
    print("PHASE 17 — Research Engine · live proof (real network + real files)")
    print("=" * 66)
    try:
        github_engine = GitHubEngine(client=GitHubClient(timeout=20))
        rung_1_github_surface(github_engine)
    except Exception as exc:  # noqa: BLE001
        record("17.1 github: real api.github.com repository search", False, str(exc)[:120])

    web = None
    try:
        web = rung_2_web_surface()
    except Exception as exc:  # noqa: BLE001
        record("17.1 web: real public search endpoint", False, str(exc)[:120])

    docs: DocsSearchProvider | None = None
    local: LocalSearchProvider | None = None
    try:
        docs, local = rung_3_corpus_surfaces()
    except Exception as exc:  # noqa: BLE001
        record("17.1 docs+local: the repository's own trees answer", False, str(exc)[:120])

    providers = [p for p in (GitHubSearchProvider(
        GitHubEngine(client=GitHubClient(timeout=20))), web, docs, local) if p is not None]
    engine = ResearchEngine(providers)
    report = None
    try:
        report = rung_4_workflow_stages(engine)
    except Exception as exc:  # noqa: BLE001
        record("17.2 workflow: eight stages walked with verdicts", False, str(exc)[:120])

    if report is not None:
        rung_5_confidence_dimensions(report)
        try:
            rung_6_memory_roundtrip(report)
        except Exception as exc:  # noqa: BLE001
            record("17.5 memory: findings remembered and recalled with sources",
                   False, str(exc)[:120])
    else:
        record("17.4 confidence: authority/relevance/freshness/evidence all present",
               False, "no report")
        record("17.5 memory: findings remembered and recalled with sources",
               False, "no report")

    print("-" * 66)
    failed = [r for r in RESULTS if not r[1]]
    print(f"LIVE PROOF: {len(RESULTS) - len(failed)}/{len(RESULTS)} rungs passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
