#!/usr/bin/env python3
"""Phase 16 live proof — a real git roundtrip + a real GitHub clone (CI-safe).

What this proves, on a real machine, with the real binary and the real
network:

1. the §16.1 Git Engine drives a real repository through the eight
   operations — init/commit/branch/worktree/merge/tag/rollback/diff;
2. the §16.2 GitHub Engine clones a real public repository from
   github.com over HTTPS (no credential needed for public reads);
3. the §16.3 lifecycle runs end-to-end over that clone's local bare
   mirror — discover → clone → index → modify → test → commit →
   review → push — with every stage verdict OK.

Exit code 0 only if every rung held.  No secrets, no tokens — public
network paths only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import git, init_repo  # noqa: E402

from nexus.git import GitEngine, RepoLifecycle, StageState  # noqa: E402
from nexus.github import GitHubEngine  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def rung_1_git_engine_roundtrip(tmp: Path) -> None:
    """The eight operations over a real repository, in order."""
    repo = init_repo(tmp / "roundtrip")
    engine = GitEngine(repo)

    # status — clean, on main
    st = engine.status()
    record("16.1 status: clean on main", st.clean and st.branch == "main", st.branch)

    # diff — an untracked file is visible (git alone would hide it)
    (repo / "new.txt").write_text("line\n", encoding="utf-8")
    d = engine.diff()
    record("16.1 diff: untracked file visible", d.files == ("new.txt",) and d.insertions == 1)

    # branch
    ref = engine.create_branch("live/branch")
    record(
        "16.1 branch: created + checked out",
        ref.current and engine.current_branch() == "live/branch",
    )

    # worktree
    entry = engine.add_worktree(tmp / "live-wt", new_branch="live/wt")
    record("16.1 worktree: real linked tree", (Path(entry.path) / "README.md").exists())
    engine.remove_worktree(entry.path)

    # commit
    res = engine.commit("feat: live proof commit", paths=(".",))
    record("16.1 commit: real sha", len(res.sha) == 40 and "new.txt" in res.files, res.short_sha)

    # merge (fast-forward)
    engine.create_branch("live/ff")
    (repo / "ff.txt").write_text("ff\n", encoding="utf-8")
    engine.commit("feat: ff work", paths=(".",))
    engine.checkout("main")
    m = engine.merge("live/ff")
    record("16.1 merge: fast-forward", m.merged and m.fast_forward)

    # tag (annotated)
    t = engine.tag("live-proof-16", message="PHASE 16 live proof")
    record("16.1 tag: annotated", t.annotated and t.message == "PHASE 16 live proof")

    # rollback with safety branch
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "rb.txt").write_text("rb\n", encoding="utf-8")
    engine.commit("feat: to be rolled back", paths=(".",))
    rb = engine.rollback(base, hard=True)
    record(
        "16.1 rollback: HEAD moved + safety branch",
        rb.to_sha == base and rb.safety_branch is not None,
        rb.safety_branch or "",
    )


def rung_2_real_github_clone(tmp: Path) -> None:
    """A real clone from github.com — public HTTPS, no credential."""
    engine_cls = GitEngine
    gh = GitHubEngine(git_cls=engine_cls)
    dest = tmp / "hello-world"
    outcome = gh.clone("https://github.com/octocat/Hello-World.git", dest)
    ok = (dest / "README").exists() and len(outcome.commit) == 40
    record("16.2 clone: real github.com clone (public)", ok, outcome.commit[:12])


def rung_3_lifecycle_over_bare(tmp: Path) -> None:
    """The full §16.3 pipeline over a real bare mirror of the clone."""
    seed = tmp / "hello-world"
    if not seed.exists():
        record("16.3 lifecycle: skipped (no clone)", False, "clone failed upstream")
        return
    bare = tmp / "mirror.git"
    git(tmp, "clone", "--bare", str(seed), str(bare))

    def discover() -> dict[str, str]:
        return {"name": "mirror", "clone_url": str(bare), "license": "MIT"}

    def modifier(engine: GitEngine) -> tuple[str, ...]:
        note = engine.repo / "NEXUS-LIFECYCLE-PROOF.md"
        note.write_text("lifecycle proof\n", encoding="utf-8")
        return ("NEXUS-LIFECYCLE-PROOF.md",)

    def reviewer(bundle: dict) -> bool:
        return bool(bundle["trail"])

    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp / "ws",
        discover=discover,
        modifier=modifier,
        reviewer=reviewer,
        test_command="",
        pusher=lambda engine, branch: engine.push(remote="origin", branch=branch),
    )
    report = lifecycle.run()
    ok = report.ok and report.reached == "push"
    details = " ".join(f"{s.stage}={s.state.value}" for s in report.stages)
    record("16.3 lifecycle: all eight stages OK", ok, details)
    assert report.stage("push").state is StageState.OK


def main() -> int:
    print("=" * 66)
    print("PHASE 16 LIVE PROOF — real binary · real network · real stages")
    print("=" * 66)
    if shutil.which("git") is None:
        print("FATAL: git not found — the engine's honesty would be tested, not the phase")
        return 2
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        rung_1_git_engine_roundtrip(tmp)
        rung_2_real_github_clone(tmp)
        rung_3_lifecycle_over_bare(tmp)
    print("-" * 66)
    failed = [r for r in RESULTS if not r[1]]
    print(f"LIVE PROOF: {len(RESULTS) - len(failed)}/{len(RESULTS)} rungs held")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
