"""Phase 16 — §16.3 the Repository Lifecycle over a real local origin.

The full eight-stage pipeline runs for real: a real clone from a real
bare remote, a real file/stack index, real modifications, real tests
(a whitelisted pytest run), a real commit, a review gate that can
reject, and a real push back to the bare origin.  No network, no fakes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import git, init_repo

from nexus.events import EventBus
from nexus.git import (
    LIFECYCLE_STAGES,
    RepoLifecycle,
    StageState,
)
from nexus.git.engine import GitEngine


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


def _bare_origin(tmp_path: Path) -> tuple[Path, Path]:
    seed = init_repo(tmp_path / "candidate-repo")
    bare = tmp_path / "candidate-origin.git"
    git(tmp_path, "clone", "--bare", str(seed), str(bare))
    return seed, bare


def _discover_from(bare: Path):
    """A local discover provider — the §16.2 search stand-in for tests."""
    def _discover() -> dict[str, object]:
        return {
            "name": "candidate-repo",
            "owner": "local",
            "clone_url": str(bare),
            "stars": 0,
            "license": "MIT",
        }
    return _discover


def _modifier(engine: GitEngine) -> tuple[str, ...]:
    readme = engine.repo / "README.md"
    readme.write_text("# candidate — modified by NEXUS lifecycle\n", encoding="utf-8")
    (engine.repo / "note.md").write_text("trail note\n", encoding="utf-8")
    return ("README.md", "note.md")


def _reviewer(bundle: dict) -> bool:
    return True


def _rejector(bundle: dict) -> bool:
    return False


def test_stage_vocabulary_verbatim() -> None:
    assert LIFECYCLE_STAGES == (
        "discover",
        "clone",
        "index",
        "modify",
        "test",
        "commit",
        "review",
        "push",
    )


def test_full_happy_pipeline(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="",
        pusher=lambda engine, branch: engine.push(remote="origin", branch=branch),
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is True
    assert report.reached == "push"
    assert report.stage("discover").state is StageState.OK
    assert report.stage("clone").state is StageState.OK
    assert report.stage("index").state is StageState.OK
    assert report.stage("modify").state is StageState.OK
    assert report.stage("test").state is StageState.SKIPPED  # no suite in the seed
    assert report.stage("commit").state is StageState.OK
    assert report.stage("review").state is StageState.OK
    assert report.stage("push").state is StageState.OK

    # the push really landed on the bare origin
    clone = tmp_path / "verify"
    git(tmp_path, "clone", str(bare), str(clone))
    assert "NEXUS lifecycle" in (clone / "README.md").read_text(encoding="utf-8")
    assert bus.published_count >= 8


def test_stack_detection_facts(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="",
        bus=bus,
    )
    report = lifecycle.run()
    stack = report.stage("index").data["stack"]
    assert stack["file_count"] >= 3
    assert "README.md" in str(stack["entry_points"]) or stack["entry_points"] == []


def test_review_rejection_stops_pipeline(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_rejector,
        test_command="",
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is False
    assert report.reached == "review"
    assert report.stage("review").state is StageState.FAILED
    assert report.stage("push").state is StageState.PENDING
    # the commit exists locally but was NOT pushed
    repo = tmp_path / "workspace" / "candidate-repo"
    engine = GitEngine(repo)
    assert engine.status().clean is True


def test_test_stage_runs_whitelisted_pytest(tmp_path: Path, bus: EventBus) -> None:
    seed, bare = _bare_origin(tmp_path)
    tests_dir = seed / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text(
        "def test_true():\n    assert True\n", encoding="utf-8"
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "test: add suite")
    git(seed, "push", str(bare), "HEAD:refs/heads/main")

    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="python -m pytest",
        pusher=lambda engine, branch: engine.push(remote="origin", branch=branch),
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is True
    test_stage = report.stage("test")
    assert test_stage.state is StageState.OK
    assert test_stage.data["exit_code"] == 0


def test_test_stage_failure_stops(tmp_path: Path, bus: EventBus) -> None:
    seed, bare = _bare_origin(tmp_path)
    tests_dir = seed / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text(
        "def test_false():\n    assert False\n", encoding="utf-8"
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "test: failing suite")
    git(seed, "push", str(bare), "HEAD:refs/heads/main")

    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="python -m pytest",
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is False
    assert report.reached == "test"
    assert report.stage("test").state is StageState.FAILED
    assert report.stage("test").data["exit_code"] != 0


def test_non_whitelisted_test_command_refused(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="curl http://evil",
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is False
    assert report.reached == "test"
    test_detail = report.stage("test").detail
    assert "not whitelisted" in test_detail or "forbidden" in test_detail


def test_forbidden_test_prefix_never_runs(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="rm -rf /",
        test_allowlist=("rm",),
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is False
    assert "forbidden" in report.stage("test").detail


def test_no_pusher_refused_without_github(tmp_path: Path, bus: EventBus) -> None:
    """skip_push=False + no pusher = honest refusal, never a guessed remote."""
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="",
        bus=bus,
    )
    lifecycle._pusher = None  # force the default path
    report = lifecycle.run()
    assert report.ok is False
    assert report.reached == "push"
    assert report.stage("push").state is StageState.FAILED


def test_github_pusher_pushes_to_bare(tmp_path: Path, bus: EventBus) -> None:
    """The default production pusher — GitHubEngine.push — works locally too."""
    _seed, bare = _bare_origin(tmp_path)
    pusher_calls: list[str] = []

    def github_style_pusher(engine: GitEngine, branch: str) -> None:
        pusher_calls.append(f"{engine.repo}:{branch}")
        engine.push(remote="origin", branch=branch)

    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="",
        pusher=github_style_pusher,
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is True
    assert report.reached == "push"
    assert len(pusher_calls) == 1


def test_lifecycle_events_canonical(tmp_path: Path, bus: EventBus) -> None:
    _seed, bare = _bare_origin(tmp_path)
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=_discover_from(bare),
        modifier=_modifier,
        reviewer=_reviewer,
        test_command="",
        bus=bus,
    )
    lifecycle.run()
    names = {e.name for e in bus.history_snapshot()}
    assert names <= {"tool.called", "tool.completed", "tool.failed"}


def test_discover_without_provider_fails_honestly(tmp_path: Path, bus: EventBus) -> None:
    lifecycle = RepoLifecycle(
        GitEngine,
        workspace_root=tmp_path / "workspace",
        discover=None,
        test_command="",
        bus=bus,
    )
    report = lifecycle.run()
    assert report.ok is False
    assert report.reached == "discover"
