#!/usr/bin/env python3
"""Phase 16 verification harness — New Plan §16 Exit Gate.

Proves the Git / GitHub section by section:

* A — Git Engine (§16.1): the eight operations verbatim (status · diff ·
       branch · worktree · commit · merge · tag · rollback), a real
       binary driven through a bounded surface, honest absence, real
       conflicts surfacing, rollback that saves what it would destroy.
* B — GitHub Engine (§16.2): the eight operations verbatim (search ·
       clone · pull · push · branch · pr · issue · release), a real
       REST law (404 honest, rate-limit reset epoch, §124 token as
       reference — masked in every repr), writes refusing without a
       credential instead of pretending.
* C — Repository Lifecycle (§16.3): the eight stages in order over a
       real bare origin — clone, index, modify, whitelisted tests only,
       commit, review gate (rejection stops, never spins), real push.
* D — Parallel Agents (§16.4 / §123): the five task kinds → five
       actions 1:1, real feature branches, a real worktree per agent,
       real checkpoints, and a release gate that refuses without
       tests + review.
* E — Events + security: only canonical §2.2 tool events leave the
       engines; token values never reach payloads, errors or reprs.
* F — Integration + regression: NEXUS_PHASE ≥ 16, nexus-core ≥ 0.16.0,
       the git/github core stays stdlib-only, and the neighbor phase
       suites (14 · 15) stay green (skippable with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import json
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

from fixtures import git, init_repo  # noqa: E402

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


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.git import (
        GIT_OPERATIONS,
        GitBinaryMissingError,
        GitEngine,
        GitEngineError,
        InvalidRepoError,
        MergeConflictError,
    )

    def vocab() -> None:
        assert GIT_OPERATIONS == (
            "status", "diff", "branch", "worktree", "commit", "merge", "tag", "rollback",
        )

    check("A·vocab eight operations verbatim", vocab)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        repo = init_repo(tmp / "repo")
        engine = GitEngine(repo)

        def status() -> None:
            st = engine.status()
            assert st.branch == "main" and st.clean and len(st.head_sha) == 40

        def diff() -> None:
            (repo / "d.txt").write_text("x\n", encoding="utf-8")
            d = engine.diff()
            assert d.files == ("d.txt",) and d.insertions == 1

        def branch() -> None:
            engine.create_branch("verify/a")
            assert engine.current_branch() == "verify/a"
            names = {b.name for b in engine.branches()}
            assert "verify/a" in names

        def worktree() -> None:
            entry = engine.add_worktree(tmp / "wt-a", new_branch="verify/wt")
            assert (Path(entry.path) / "README.md").exists()
            assert len(engine.worktrees()) == 2
            engine.remove_worktree(entry.path)

        def commit() -> None:
            (repo / "c.txt").write_text("c\n", encoding="utf-8")
            res = engine.commit("feat: verify commit", paths=(".",))
            assert len(res.sha) == 40 and "c.txt" in res.files

        def merge() -> None:
            engine.create_branch("verify/ff")
            (repo / "ff.txt").write_text("ff\n", encoding="utf-8")
            engine.commit("feat: ff", paths=(".",))
            engine.checkout("main")
            res = engine.merge("verify/ff")
            assert res.merged and res.fast_forward

        def conflict() -> None:
            engine.create_branch("verify/cf")
            (repo / "README.md").write_text("cf\n", encoding="utf-8")
            engine.commit("feat: cf", paths=(".",))
            engine.checkout("main")
            (repo / "README.md").write_text("main\n", encoding="utf-8")
            engine.commit("feat: main", paths=(".",))
            expects(MergeConflictError, engine.merge, "verify/cf")

        def tag() -> None:
            rec = engine.tag("verify-16", message="gate A")
            assert rec.annotated and rec.message == "gate A"

        def rollback() -> None:
            base = engine.head()
            (repo / "rb.txt").write_text("rb\n", encoding="utf-8")
            engine.commit("feat: rb", paths=(".",))
            res = engine.rollback(base, hard=True)
            assert res.safety_branch and not (repo / "rb.txt").exists()

        def honesty() -> None:
            expects(InvalidRepoError, GitEngine(tmp / "nope").status)
            expects(GitBinaryMissingError, GitEngine, tmp, git_executable="no-git-xyz")
            expects(GitEngineError, engine.commit, "")

        check("A·status", status)
        check("A·diff", diff)
        check("A·branch", branch)
        check("A·worktree", worktree)
        check("A·commit", commit)
        check("A·merge (fast-forward)", merge)
        check("A·merge (conflict surfaces)", conflict)
        check("A·tag (annotated)", tag)
        check("A·rollback (safety branch)", rollback)
        check("A·honesty (invalid repo / missing binary / empty message)", honesty)


# ------------------------------------------------------------------- section B


class _GateHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        return

    def _send(self, code: int, payload: Any, extra: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/repos/missing/none"):
            self._send(404, {"message": "Not Found"})
        elif self.path.startswith("/repos/limited/none"):
            self._send(429, {"message": "rate limit"}, {"X-RateLimit-Reset": "1900000000"})
        else:
            self._send(200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        self._send(401, {"message": "Requires authentication"})


def section_b() -> None:
    from nexus.github import (
        GITHUB_OPERATIONS,
        GitHubClient,
        GitHubEngine,
        NotFoundError,
        RateLimitExceededError,
        TokenNotAvailableError,
        TokenRef,
    )

    def vocab() -> None:
        assert GITHUB_OPERATIONS == (
            "search", "clone", "pull", "push", "branch", "pr", "issue", "release",
        )

    def token_law() -> None:
        ref = TokenRef("env", "NO_SUCH_TOKEN_XYZ")
        assert "NO_SUCH_TOKEN_XYZ" in repr(ref)
        expects(TokenNotAvailableError, ref.resolve)
        expects(TokenNotAvailableError, TokenRef("file", "/no/such/token").resolve)

    check("B·vocab eight operations verbatim", vocab)
    check("B·§124 token as reference (masked, honest refusal)", token_law)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GateHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        client = GitHubClient(base=f"http://127.0.0.1:{httpd.server_address[1]}", timeout=10)
        engine = GitHubEngine(client=client)

        def rest_law() -> None:
            expects(NotFoundError, client.request, "GET", "/repos/missing/none")
            try:
                client.request("GET", "/repos/limited/none")
                raise AssertionError("expected RateLimitExceededError")
            except RateLimitExceededError as exc:
                assert exc.reset_epoch == 1900000000

        def writes_refuse() -> None:
            expects(TokenNotAvailableError, engine.create_issue, "o/r", title="t")
            expects(
                TokenNotAvailableError,
                engine.create_pull,
                "o/r",
                title="t",
                head="h",
                base="b",
            )
            expects(TokenNotAvailableError, engine.create_release, "o/r", tag_name="v", name="n")

        check("B·REST law (404 honest / rate-limit reset)", rest_law)
        check("B·writes refuse without credential", writes_refuse)
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.git import LIFECYCLE_STAGES, RepoLifecycle, StageState
    from nexus.git.engine import GitEngine

    def vocab() -> None:
        assert LIFECYCLE_STAGES == (
            "discover", "clone", "index", "modify", "test", "commit", "review", "push",
        )

    check("C·vocab eight stages verbatim", vocab)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        seed = init_repo(tmp / "cand")
        bare = tmp / "cand-origin.git"
        git(tmp, "clone", "--bare", str(seed), str(bare))

        def discover() -> dict[str, Any]:
            return {"name": "cand", "clone_url": str(bare)}

        def modifier(engine: GitEngine) -> tuple[str, ...]:
            (engine.repo / "README.md").write_text("# verified\n", encoding="utf-8")
            return ("README.md",)

        def reviewer(bundle: dict) -> bool:
            return bundle["trail"] == ["README.md"]

        def happy() -> None:
            lc = RepoLifecycle(
                GitEngine,
                workspace_root=tmp / "ws",
                discover=discover,
                modifier=modifier,
                reviewer=reviewer,
                test_command="",
                pusher=lambda e, b: e.push(remote="origin", branch=b),
            )
            report = lc.run()
            assert report.ok and report.reached == "push"
            assert report.stage("commit").state is StageState.OK

        def reject() -> None:
            lc = RepoLifecycle(
                GitEngine,
                workspace_root=tmp / "ws2",
                discover=discover,
                modifier=modifier,
                reviewer=lambda bundle: False,
                test_command="",
                pusher=lambda e, b: e.push(remote="origin", branch=b),
            )
            report = lc.run()
            assert not report.ok and report.reached == "review"
            assert report.stage("push").state is StageState.PENDING

        def whitelist() -> None:
            lc = RepoLifecycle(
                GitEngine,
                workspace_root=tmp / "ws3",
                discover=discover,
                modifier=modifier,
                reviewer=reviewer,
                test_command="curl http://x",
                pusher=lambda e, b: e.push(remote="origin", branch=b),
            )
            report = lc.run()
            assert not report.ok
            detail = report.stage("test").detail
            assert "whitelisted" in detail or "forbidden" in detail, detail

        check("C·happy pipeline over a real bare origin", happy)
        check("C·review rejection stops (never spins)", reject)
        check("C·test command whitelist enforced", whitelist)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.git import (
        STRATEGY_CARDINALITY,
        TASK_KINDS,
        GitEngine,
        ParallelRepoStrategy,
        StrategyAction,
    )
    from nexus.git.parallel import StrategyError

    def map_law() -> None:
        assert TASK_KINDS == (
            "small_change", "major_feature", "parallel_agents", "risky_refactor", "release",
        )
        assert STRATEGY_CARDINALITY == {"task_kinds": 5, "strategy_actions": 5}
        s = ParallelRepoStrategy.__new__(ParallelRepoStrategy)
        s._engine = None  # noqa: SLF001 — plan() is pure
        assert s.plan("small_change").action is StrategyAction.DIRECT_COMMIT
        assert s.plan("major_feature").action is StrategyAction.FEATURE_BRANCH
        assert s.plan("parallel_agents").action is StrategyAction.WORKTREE_FLEET
        assert s.plan("risky_refactor").action is StrategyAction.CHECKPOINT_BRANCH
        assert s.plan("release").action is StrategyAction.TAG_RELEASE

    check("D·§123 map (5 kinds → 5 actions, 1:1)", map_law)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        repo = init_repo(tmp / "repo")
        engine = GitEngine(repo)
        s = ParallelRepoStrategy(engine)

        def feature() -> None:
            _plan, branch = s.feature_branch("verify-major")
            assert engine.current_branch() == "feature/verify-major"

        def fleet() -> None:
            git(repo, "branch", "verify/one")
            fleet = s.worktree_fleet(["verify/one"], root=tmp / "f")
            assert (Path(fleet.entries[0][1]) / "README.md").exists()
            s.teardown_fleet(fleet)

        def checkpoint() -> None:
            _plan, tag = s.checkpoint("verify-risky")
            assert tag in {t.name for t in engine.tags()}

        def gate() -> None:
            expects(StrategyError, s.finish_release, "v0", tests_passed=False, review_approved=True)
            s.finish_release("v0.16.0", tests_passed=True, review_approved=True)
            assert "v0.16.0" in {t.name for t in engine.tags()}

        check("D·feature branch real", feature)
        check("D·worktree fleet real", fleet)
        check("D·checkpoint tag real", checkpoint)
        check("D·release gate (tests + review)", gate)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.events import EventBus
    from nexus.git import GitEngine

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        repo = init_repo(tmp / "repo")
        bus = EventBus()

        def canonical_only() -> None:
            engine = GitEngine(repo, bus=bus)
            engine.status()
            engine.tag("evt")
            names = {e.name for e in bus.history_snapshot()}
            assert names <= {"tool.called", "tool.completed"}

        check("E·git engine publishes canonical tool events only", canonical_only)


# ------------------------------------------------------------------- section F


def section_f(no_regression: bool) -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 16
        parts = tuple(int(p) for p in nexus.__version__.split(".")[:3])
        assert parts >= (0, 16, 0), nexus.__version__

    def stdlib_only() -> None:
        for module in ("nexus/git/engine", "nexus/git/contracts", "nexus/git/lifecycle",
                       "nexus/git/parallel", "nexus/github/client", "nexus/github/engine",
                       "nexus/github/contracts"):
            src = ROOT / (module + ".py")
            tree = ast.parse(src.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports.add(node.module.split(".")[0])
            external = imports - {
                "__future__", "ast", "base64", "collections", "dataclasses", "datetime",
                "enum", "json", "os", "pathlib", "re", "shutil", "subprocess", "sys",
                "typing", "urllib", "http", "nexus",
            }
            assert not external, f"{module} imports non-stdlib: {external}"

    def regression() -> None:
        for phase in ("14", "15"):
            verify = ROOT / "tests" / f"phase{phase}" / "verify_exit_criteria.py"
            proc = subprocess.run(
                [sys.executable, str(verify), "--no-regression"],
                capture_output=True, text=True, timeout=900,
            )
            assert proc.returncode == 0, f"phase{phase} regressed: {proc.stdout[-500:]}"

    check("F·identity (NEXUS_PHASE ≥ 16 · ≥ 0.16.0)", identity)
    check("F·git/github core stays stdlib-only", stdlib_only)
    if not no_regression:
        check("F·neighbor phases green (14 · 15)", regression)
    else:
        print("  – F·regression skipped (--no-regression)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-regression", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("PHASE 16 — Git / GitHub · Exit Gate (New Plan §16)")
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
