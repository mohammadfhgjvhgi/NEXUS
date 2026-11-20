"""Phase 16 — §16.1 the Git Engine: eight operations over the real binary.

Every test here runs a real ``git`` binary against a real temporary
repository — the binary is the judge (the Speed Rules), and the CI
runner's git is as real as the user's box's git.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import git, init_repo

from nexus.events import EventBus
from nexus.git import (
    GIT_OPERATIONS,
    GitBinaryMissingError,
    GitEngine,
    GitEngineError,
    GitOperationKind,
    InvalidRepoError,
    MergeConflictError,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


@pytest.fixture()
def engine(repo: Path) -> GitEngine:
    return GitEngine(repo)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


# ------------------------------------------------------------------ vocabulary


def test_the_eight_operations_verbatim() -> None:
    assert GIT_OPERATIONS == (
        "status",
        "diff",
        "branch",
        "worktree",
        "commit",
        "merge",
        "tag",
        "rollback",
    )
    assert len(GitOperationKind) == 8


def test_operation_kind_coercion() -> None:
    assert GitOperationKind.from_value("STATUS") is GitOperationKind.STATUS
    assert GitOperationKind.from_value("worktree") is GitOperationKind.WORKTREE
    with pytest.raises(GitEngineError):
        GitOperationKind.from_value("rebase")


def test_missing_binary_is_honest(tmp_path: Path) -> None:
    with pytest.raises(GitBinaryMissingError):
        GitEngine(tmp_path, git_executable="definitely-not-a-git-binary-xyz")


def test_non_repo_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(InvalidRepoError):
        GitEngine(empty).status()


# -------------------------------------------------------------------- status


def test_status_clean_then_dirty(repo: Path, engine: GitEngine) -> None:
    status = engine.status()
    assert status.clean is True
    assert status.branch == "main"
    assert len(status.head_sha) == 40

    (repo / "new.txt").write_text("hello", encoding="utf-8")
    status = engine.status()
    assert status.clean is False
    assert "new.txt" in status.untracked


def test_status_buckets_staged_modified(repo: Path, engine: GitEngine) -> None:
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "staged.txt")
    status = engine.status()
    assert "staged.txt" in status.staged
    assert "README.md" in status.modified


# ---------------------------------------------------------------------- diff


def test_diff_counts_lines(repo: Path, engine: GitEngine) -> None:
    (repo / "README.md").write_text("line1\nline2\n", encoding="utf-8")
    diff = engine.diff()
    assert diff.files == ("README.md",)
    assert diff.insertions == 2
    assert diff.deletions == 1  # the seeded line replaced


def test_diff_staged_and_patch(repo: Path, engine: GitEngine) -> None:
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", ".")
    diff = engine.diff(staged=True, with_patch=True)
    assert "f.txt" in diff.files
    assert "diff --git" in diff.patch


# -------------------------------------------------------------------- branch


def test_branch_create_list_checkout(repo: Path, engine: GitEngine) -> None:
    ref = engine.create_branch("feature/x")
    assert ref.current is True
    assert engine.current_branch() == "feature/x"
    names = [b.name for b in engine.branches()]
    assert set(names) >= {"main", "feature/x"}
    engine.checkout("main")
    assert engine.current_branch() == "main"


def test_branch_name_validation(repo: Path, engine: GitEngine) -> None:
    with pytest.raises(GitEngineError):
        engine.create_branch("bad branch name!")


def test_checkout_refuses_dirty_tree(repo: Path, engine: GitEngine) -> None:
    engine.create_branch("feature/y")
    (repo / "dirty.txt").write_text("unsaved\n", encoding="utf-8")
    with pytest.raises(GitEngineError, match="refusing"):
        engine.checkout("main")


# ------------------------------------------------------------------ worktree


def test_worktree_add_list_remove(repo: Path, engine: GitEngine, tmp_path: Path) -> None:
    wt_path = tmp_path / "fleet" / "agent-a"
    entry = engine.add_worktree(wt_path, new_branch="agent/a")
    assert entry.branch == "agent/a"
    assert (wt_path / "README.md").exists()

    entries = engine.worktrees()
    assert len(entries) == 2  # main + linked
    linked = [e for e in entries if e.path != str(repo)]
    assert linked[0].branch == "agent/a"

    engine.remove_worktree(wt_path)
    assert len(engine.worktrees()) == 1


def test_worktree_path_must_be_empty(repo: Path, engine: GitEngine, tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(GitEngineError):
        engine.add_worktree(occupied, new_branch="agent/b")


# -------------------------------------------------------------------- commit


def test_commit_records_sha_and_files(repo: Path, engine: GitEngine) -> None:
    (repo / "feature.txt").write_text("f\n", encoding="utf-8")
    result = engine.commit("feat: add feature", paths=(".",))
    assert len(result.sha) == 40
    assert "feature.txt" in result.files
    log = engine.log(limit=1)
    assert log[0].sha == result.sha


def test_commit_requires_message(repo: Path, engine: GitEngine) -> None:
    with pytest.raises(GitEngineError, match="message"):
        engine.commit("   ")


# --------------------------------------------------------------------- merge


def test_merge_fast_forward(repo: Path, engine: GitEngine) -> None:
    engine.create_branch("ff/branch")
    (repo / "ff.txt").write_text("ff\n", encoding="utf-8")
    engine.commit("feat: ff branch work", paths=(".",))
    engine.checkout("main")
    result = engine.merge("ff/branch")
    assert result.merged is True
    assert result.fast_forward is True


def test_merge_conflict_surfaces_honestly(repo: Path, engine: GitEngine) -> None:
    engine.create_branch("side")
    (repo / "README.md").write_text("side version\n", encoding="utf-8")
    engine.commit("feat: side edit", paths=(".",))
    engine.checkout("main")
    (repo / "README.md").write_text("main version\n", encoding="utf-8")
    engine.commit("feat: main edit", paths=(".",))
    with pytest.raises(MergeConflictError):
        engine.merge("side")


# ----------------------------------------------------------------------- tag


def test_tag_light_and_annotated(repo: Path, engine: GitEngine) -> None:
    light = engine.tag("v0-light")
    assert light.annotated is False
    heavy = engine.tag("v1-heavy", message="first release")
    assert heavy.annotated is True
    assert heavy.message == "first release"
    names = [t.name for t in engine.tags()]
    assert "v0-light" in names and "v1-heavy" in names


def test_tag_name_validation(repo: Path, engine: GitEngine) -> None:
    with pytest.raises(GitEngineError):
        engine.tag("bad tag!")


# ------------------------------------------------------------------ rollback


def test_rollback_mixed_keeps_work(repo: Path, engine: GitEngine) -> None:
    first = engine.head()
    (repo / "second.txt").write_text("2\n", encoding="utf-8")
    engine.commit("feat: second", paths=(".",))
    result = engine.rollback(first)
    assert result.to_sha == first
    assert result.hard is False
    # mixed reset keeps the file in the work tree, unstaged
    assert (repo / "second.txt").exists()


def test_rollback_hard_saves_safety_branch(repo: Path, engine: GitEngine) -> None:
    first = engine.head()
    (repo / "risky.txt").write_text("risky\n", encoding="utf-8")
    engine.commit("feat: risky", paths=(".",))
    result = engine.rollback(first, hard=True)
    assert result.safety_branch is not None
    names = [b.name for b in engine.branches()]
    assert result.safety_branch in names
    assert not (repo / "risky.txt").exists()


def test_rollback_unborn_head_refused(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git(fresh, "init", "-b", "main")
    with pytest.raises(GitEngineError, match="unborn"):
        GitEngine(fresh).rollback("HEAD~1")


# ----------------------------------------------------------------- clone/log


def test_clone_from_local_bare(tmp_path: Path) -> None:
    seed = init_repo(tmp_path / "seed")
    bare = tmp_path / "seed.git"
    git(tmp_path, "clone", "--bare", str(seed), str(bare))
    engine = GitEngine.clone(str(bare), tmp_path / "cloned")
    assert (tmp_path / "cloned" / "README.md").exists()
    assert engine.status().clean


def test_clone_refuses_dirty_destination(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "f.txt").write_text("x", encoding="utf-8")
    with pytest.raises(GitEngineError, match="destination"):
        GitEngine.clone(str(tmp_path), occupied)


def test_log_limit(repo: Path, engine: GitEngine) -> None:
    for i in range(3):
        (repo / f"f{i}.txt").write_text("x\n", encoding="utf-8")
        engine.commit(f"feat: c{i}", paths=(".",))
    entries = engine.log(limit=2)
    assert len(entries) == 2


# -------------------------------------------------------------------- events


def test_events_are_canonical(repo: Path, bus: EventBus) -> None:
    engine = GitEngine(repo, bus=bus)
    engine.status()
    engine.tag("evt-tag")
    seen = {e.name for e in bus.history_snapshot()}
    assert seen <= {"tool.called", "tool.completed"}
    assert bus.published_count >= 4
