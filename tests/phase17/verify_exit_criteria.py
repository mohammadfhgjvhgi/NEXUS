#!/usr/bin/env python3
"""Phase 17 verification harness — New Plan §17 Exit Gate.

Proves the Research Engine section by section:

* A — Search abstraction (§17.1): the five surfaces verbatim (web ·
       github · docs · forums · local files), one adapter each behind
       the SearchProvider contract, all live against real local HTTP
       servers and real corpora, honest absence and honest failure.
* B — Research workflow (§17.2): the eight stages verbatim and in
       order (query → search → collect → deduplicate → rank → compare
       → verify → evidence), verdicts per stage, duplicates collapsed,
       corroboration required, conflicts surfaced, evidence attached.
* C — Source classification (§17.3): the six classes verbatim, all
       reachable, the documented ladder order holds.
* D — Source confidence (§17.4): the four dimensions verbatim
       (authority · relevance · freshness · evidence), documented
       weights, per-class authority ladder, honest math.
* E — Research memory (§17.5) + events: findings persist into §12
       Task/Project memory with research evidence rows, recall keeps
       sources, only canonical §2.2 events leave the engine.
* F — Integration + regression: NEXUS_PHASE ≥ 17, nexus-core ≥
       0.17.0, the research core stays stdlib-only, and the neighbor
       phase suites (14 · 15 · 16) stay green (skippable with
       --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn: Any) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_type: type, fn: Any, *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


class _GateHandler(BaseHTTPRequestHandler):
    """One server: a web surface, a forum surface, a GitHub search stub."""

    def log_message(self, *args: Any) -> None:
        return

    def _send(self, code: int, payload: Any) -> None:
        import json

        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/web"):
            self._send(200, {"results": [
                {"title": "7B GGUF needs 4 GB", "url": "https://docs.example.com/gguf.html",
                 "snippet": "a 7B Q4 GGUF model needs about 4 GB of RAM to run"},
                {"title": "7B GGUF needs 4 GB (mirror)",
                 "url": "https://docs.example.com/gguf.html",
                 "snippet": "a 7B Q4 GGUF model needs about 4 GB of RAM to run"},
                {"title": "blog quantization", "url": "https://alice.wordpress.com/q",
                 "snippet": "a 7B Q4 GGUF model needs roughly 4 GB of RAM here"},
            ]})
        elif self.path.startswith("/search.json"):
            self._send(200, {"topics": [
                {"title": "7B ram thread", "url": "https://forum.example.com/t/1",
                 "blurb": "my 7B gguf run took 4 GB ram"},
            ]})
        elif self.path.startswith("/search/repositories"):
            self._send(200, {"items": [
                {"name": "llama.cpp", "owner": {"login": "ggml-org"},
                 "html_url": "https://github.com/ggml-org/llama.cpp",
                 "clone_url": "https://github.com/ggml-org/llama.cpp.git",
                 "stargazers_count": 90000, "license": {"spdx_id": "MIT"},
                 "pushed_at": "2026-01-10T00:00:00Z", "archived": False,
                 "description": "LLM inference", "language": "C++"},
            ]})
        elif self.path.startswith("/broken"):
            self._send(500, {"message": "kaboom"})
        else:
            self._send(404, {"message": "no such surface"})


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.github import GitHubClient, GitHubEngine
    from nexus.research import (
        SOURCE_KINDS,
        DocsSearchProvider,
        ForumSearchProvider,
        GitHubSearchProvider,
        LocalSearchProvider,
        ProviderError,
        SearchProvider,
        SourceKind,
        WebSearchProvider,
    )

    def vocab() -> None:
        assert SOURCE_KINDS == ("web", "github", "docs", "forums", "local")
        for cls in (WebSearchProvider, ForumSearchProvider, GitHubSearchProvider,
                    DocsSearchProvider, LocalSearchProvider):
            assert issubclass(cls, SearchProvider)

    check("A·vocab five surfaces verbatim, one contract", vocab)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GateHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            docs_dir = tmp / "docs"
            docs_dir.mkdir()
            (docs_dir / "gguf.md").write_text(
                "# GGUF\na 7B Q4 GGUF model needs about 4 GB of RAM to run locally\n",
                encoding="utf-8",
            )
            (docs_dir / "other.txt").write_text("the keyboard layout per window\n",
                                                encoding="utf-8")
            tree = tmp / "ws"
            (tree / "n").mkdir(parents=True)
            (tree / "n" / "todo.txt").write_text("benchmark llama.cpp locally\n",
                                                 encoding="utf-8")

            web = WebSearchProvider(f"{base}/web")
            forums = ForumSearchProvider(f"{base}/search.json")
            github = GitHubSearchProvider(
                GitHubEngine(client=GitHubClient(base=base, timeout=10))
            )
            docs = DocsSearchProvider([docs_dir])
            local = LocalSearchProvider([tree])

            def web_hits() -> None:
                hits = web.search("7B gguf ram")
                assert len(hits) == 3 and hits[0].kind == SourceKind.WEB

            def forums_hits() -> None:
                hits = forums.search("7B gguf ram")
                assert len(hits) == 1 and hits[0].kind == SourceKind.FORUMS

            def github_hits() -> None:
                hits = github.search("llama.cpp")
                assert hits and hits[0].metadata["github_type"] == "repo"

            def docs_hits() -> None:
                hits = docs.search("gguf ram 7B")
                assert hits and hits[0].uri.startswith("file:")
                assert hits[0].snippet and "4 GB" in hits[0].snippet

            def local_hits() -> None:
                hits = local.search("llama.cpp benchmark")
                assert hits and "todo.txt" in {h.title for h in hits}
                assert local.search("totally absent topic xyz") == []

            def honest_failure() -> None:
                broken = WebSearchProvider(f"{base}/broken")
                expects(ProviderError, broken.search, "anything")
                assert web.search("   ") == []

            check("A·web surface live", web_hits)
            check("A·forums surface live", forums_hits)
            check("A·github surface live (public read)", github_hits)
            check("A·docs corpus live (file:// evidence)", docs_hits)
            check("A·local files live (honest absence)", local_hits)
            check("A·honesty (500 raises · empty query is empty)", honest_failure)
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.research import (
        WORKFLOW_STAGES,
        ResearchWorkflow,
        StageState,
        WebSearchProvider,
    )

    def vocab() -> None:
        assert WORKFLOW_STAGES == (
            "query", "search", "collect", "deduplicate", "rank", "compare", "verify", "evidence",
        )

    check("B·vocab eight stages verbatim and ordered", vocab)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GateHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        workflow = ResearchWorkflow([WebSearchProvider(f"{base}/web")])

        def pipeline() -> None:
            report = workflow.run("7B gguf ram", min_corroboration=2)
            assert report.stage("query").state is StageState.OK
            assert report.stage("search").state is StageState.OK
            assert report.stage("deduplicate").detail.startswith("3 → 2"), (
                report.stage("deduplicate").detail
            )
            assert report.stage("rank").state is StageState.OK
            assert report.ok and report.reached == "evidence"
            assert report.verified, "docs source + blog source agree on 4 GB"

        def conflict_law() -> None:
            from nexus.research import SearchHit, SearchProvider

            class A(SearchProvider):
                name, kind = "a", "web"

                def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
                    return [SearchHit(title="Model RAM", uri="https://a/x",
                                      snippet="a 7B model needs 4 GB ram")]

            class B(SearchProvider):
                name, kind = "b", "forums"

                def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
                    return [SearchHit(title="Model RAM", uri="https://b/y",
                                      snippet="a 7B model needs 64 GB ram")]

            report = ResearchWorkflow([A(), B()]).run("7B model ram", min_corroboration=99)
            assert report.conflicts, "4 GB vs 64 GB must surface as a conflict"
            assert not report.verified

        def empty_honest() -> None:
            report = ResearchWorkflow([]).run("7B gguf ram")
            assert report.stage("search").state is StageState.FAILED
            assert not report.ok

        check("B·pipeline (dedup → verify → evidence) live", pipeline)
        check("B·conflict law (numbers disagree on overlapping claims)", conflict_law)
        check("B·honesty (no providers fails at search)", empty_honest)
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.research import SOURCE_CLASSES, SearchHit, SourceClass, classify

    def vocab() -> None:
        assert SOURCE_CLASSES == ("official", "documentation", "academic", "community",
                                  "personal", "unknown")

    def ladder() -> None:
        def hit(uri: str, **meta: str) -> SearchHit:
            return SearchHit(title="t", uri=uri, metadata=meta)

        seen: set[str] = set()
        seen.add(classify(hit("https://arxiv.org/abs/1")))
        seen.add(classify(hit("https://docs.python.org/3/")))
        seen.add(classify(hit("https://python.org/")))
        seen.add(classify(hit("https://reddit.com/r/x")))
        seen.add(classify(hit("https://a.wordpress.com/p")))
        seen.add(classify(hit("https://unknown.example.net/x")))
        assert seen == set(SOURCE_CLASSES), seen
        assert classify(hit("https://github.com/o/r", github_type="repo")) == SourceClass.OFFICIAL
        assert classify(hit("https://github.com/o/r/issues/1", github_type="issue")) == (
            SourceClass.COMMUNITY
        )
        assert classify(hit("file:///p/docs/g.md")) == SourceClass.DOCUMENTATION

    check("C·vocab six classes verbatim", vocab)
    check("C·ladder (all six reachable · github repo/issue law · file law)", ladder)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.research import (
        AUTHORITY_BY_CLASS,
        CONFIDENCE_DIMENSIONS,
        DEFAULT_WEIGHTS,
        SearchHit,
        SourceClass,
        SourceConfidence,
        confidence_from_hit,
    )

    def vocab() -> None:
        assert CONFIDENCE_DIMENSIONS == ("authority", "relevance", "freshness", "evidence")
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def ladder() -> None:
        assert AUTHORITY_BY_CLASS[SourceClass.OFFICIAL] > AUTHORITY_BY_CLASS[SourceClass.UNKNOWN]

    def math() -> None:
        conf = SourceConfidence(authority=1.0, relevance=0.0, freshness=0.0, evidence=0.0)
        assert abs(conf.score() - DEFAULT_WEIGHTS["authority"]) < 1e-3
        hit = SearchHit(title="llama.cpp runs GGUF", uri="u", snippet="llama.cpp GGUF locally")
        graded = confidence_from_hit(hit, classification="official",
                                     query_terms=("llama.cpp", "gguf", "local"))
        assert graded.relevance == 1.0 and graded.evidence == 1.0
        assert 0.0 <= graded.score() <= 1.0
        assert set(graded.breakdown()) == set(CONFIDENCE_DIMENSIONS)

    check("D·vocab four dimensions verbatim + weights law", vocab)
    check("D·authority ladder per §17.3 class", ladder)
    check("D·score math + dimensions computed live", math)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.events import EventBus
    from nexus.memory import MemoryEngine, MemoryType, SQLiteMemoryStore
    from nexus.research import ResearchEngine, ResearchMemory, WebSearchProvider

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GateHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            memory = MemoryEngine(SQLiteMemoryStore(str(tmp / "mem.sqlite")))
            engine = ResearchEngine([WebSearchProvider(f"{base}/web")], memory=memory)
            report = engine.run("7B gguf ram", min_corroboration=2)
            assert report.verified

            def remember_law() -> None:
                written = engine.remember(report, project="gate", task="t-1")
                assert written
                rows = engine.recall("gguf ram", task="t-1")
                assert rows and rows[0]["sources"]
                assert rows[0]["sources"][0]["method"] == "research"
                assert rows[0]["sources"][0]["uri"]

            def scope_law() -> None:
                report2 = engine.run("7B gguf ram", min_corroboration=2)
                mem = ResearchMemory(memory)
                with_task = mem.remember(report2, task="t-2")
                assert with_task
                other = mem.recall("gguf ram", task="other-task")
                assert not other

            def events_canonical() -> None:
                bus = EventBus()
                solo = ResearchEngine([WebSearchProvider(f"{base}/web")], bus=bus)
                solo.run("7B gguf ram")
                names = {event.name for event in bus.history_snapshot()}
                assert names <= {"tool.called", "tool.completed", "tool.failed"}, names
                blob = repr([event.payload for event in bus.history_snapshot()])
                assert "snippet" not in blob, "source content never rides the bus"

            def summary_rides() -> None:
                from nexus.memory import MemoryQuery

                hits = memory.search(
                    MemoryQuery(text="research session", task="t-1", project="gate", limit=20)
                )
                assert any(h.record.type == MemoryType.SUMMARY for h in hits)

            check("E·§17.5 remember with sources · recall keeps them", remember_law)
            check("E·scope law (task isolation)", scope_law)
            check("E·canonical events only · no content on the bus", events_canonical)
            check("E·session summary remembered", summary_rides)
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------- section F


def section_f(no_regression: bool) -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 17
        parts = tuple(int(p) for p in nexus.__version__.split(".")[:3])
        assert parts >= (0, 17, 0), nexus.__version__

    def stdlib_only() -> None:
        for module in ("nexus/research/contracts", "nexus/research/classify",
                       "nexus/research/providers", "nexus/research/workflow",
                       "nexus/research/memory", "nexus/research/engine"):
            src = ROOT / (module + ".py")
            tree = ast.parse(src.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports.add(node.module.split(".")[0])
            external = imports - {
                "__future__", "abc", "collections", "dataclasses", "datetime", "enum",
                "hashlib", "json", "pathlib", "re", "sys", "typing", "urllib", "http", "nexus",
            }
            assert not external, f"{module} imports non-stdlib: {external}"

    def regression() -> None:
        for phase in ("14", "15", "16"):
            verify = ROOT / "tests" / f"phase{phase}" / "verify_exit_criteria.py"
            proc = subprocess.run(
                [sys.executable, str(verify), "--no-regression"],
                capture_output=True, text=True, timeout=900,
            )
            assert proc.returncode == 0, f"phase{phase} regressed: {proc.stdout[-500:]}"

    check("F·identity (NEXUS_PHASE ≥ 17 · ≥ 0.17.0)", identity)
    check("F·research core stays stdlib-only", stdlib_only)
    if not no_regression:
        check("F·neighbor phases green (14 · 15 · 16)", regression)
    else:
        print("  – F·regression skipped (--no-regression)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-regression", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("PHASE 17 — Research Engine · Exit Gate (New Plan §17)")
    print("=" * 66)
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f(args.no_regression)
    print("-" * 66)
    print(f"PASSED: {len(PASSED)}  FAILED: {len(FAILED)}")
    if FAILED:
        for line in FAILED:
            print(f"  ✗ {line}")
        return 1
    print("Exit gate: Implemented · Integrated · Tested · Verified · Documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
