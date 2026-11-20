"""Phase 16 — §16.4 Parallel Agents: §123 as executable law.

feature branch · worktree · checkpoint — بحسب المهمة.  Every assertion
below runs real git: real branches, real worktrees, real tags, and the
§123 release gate that refuses to tag without tests + review.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import git, init_repo

from nexus.events import EventBus
from nexus.git import (
    STRATEGY_CARDINALITY,
    TASK_KINDS,
    GitEngine,
    GitEngineError,
    ParallelRepoStrategy,
    StrategyAction,
    TaskKind,
)
from nexus.git.parallel import StrategyError


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


@pytest.fixture()
def engine(repo: Path) -> GitEngine:
    return GitEngine(repo)


@pytest.fixture()
def strategy(engine: GitEngine, bus: EventBus) -> ParallelRepoStrategy:
    return ParallelRepoStrategy(engine, bus=bus)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


# ------------------------------------------------------------- the §123 map


def test_five_kinds_map_to_five_actions_verbatim() -> None:
    assert TASK_KINDS == (
        "small_change",
        "major_feature",
        "parallel_agents",
        "risky_refactor",
        "release",
    )
    assert STRATEGY_CARDINALITY == {"task_kinds": 5, "strategy_actions": 5}
    kinds = [TaskKind(k) for k in TASK_KINDS]
    strategy = ParallelRepoStrategy.__new__(ParallelRepoStrategy)  # plan() is pure
    engine = None
    strategy._engine = engine  # noqa: SLF001 — plan() never touches it
    actions = {k: strategy.plan(k).action for k in kinds}
    assert actions[TaskKind.SMALL_CHANGE] is StrategyAction.DIRECT_COMMIT
    assert actions[TaskKind.MAJOR_FEATURE] is StrategyAction.FEATURE_BRANCH
    assert actions[TaskKind.PARALLEL_AGENTS] is StrategyAction.WORKTREE_FLEET
    assert actions[TaskKind.RISKY_REFACTOR] is StrategyAction.CHECKPOINT_BRANCH
    assert actions[TaskKind.RELEASE] is StrategyAction.TAG_RELEASE


def test_plan_carries_the_123_gates(strategy: ParallelRepoStrategy) -> None:
    release = strategy.plan("release", task="v0.16.0")
    assert release.requires_tests is True
    assert release.requires_review is True
    direct = strategy.plan("small_change")
    assert direct.requires_tests is False and direct.branch is None


# ------------------------------------------------------------ feature branch


def test_feature_branch_real_and_checked_out(
    strategy: ParallelRepoStrategy, engine: GitEngine
) -> None:
    plan, branch = strategy.feature_branch("add-github-engine")
    assert branch == "feature/add-github-engine"
    assert engine.current_branch() == "feature/add-github-engine"
    assert plan.action is StrategyAction.FEATURE_BRANCH


def test_feature_branch_slug_validated(strategy: ParallelRepoStrategy) -> None:
    with pytest.raises(StrategyError):
        strategy.feature_branch("Bad Branch!")


# ------------------------------------------------------------ worktree fleet


def test_worktree_fleet_one_tree_per_agent(
    strategy: ParallelRepoStrategy, engine: GitEngine, repo: Path, tmp_path: Path
) -> None:
    git(repo, "branch", "agent/alpha")
    git(repo, "branch", "agent/beta")
    fleet = strategy.worktree_fleet(
        ["agent/alpha", "agent/beta"],
        root=tmp_path / "fleet",
    )
    assert len(fleet.entries) == 2
    for _branch, path in fleet.entries:
        assert (Path(path) / "README.md").exists()  # real checkouts
    branches = {e.branch for e in engine.worktrees()}
    assert {"agent/alpha", "agent/beta"} <= branches

    removed = strategy.teardown_fleet(fleet)
    assert len(removed) == 2
    assert len(engine.worktrees()) == 1  # back to the main tree only


def test_fleet_merge_back_hook_runs(
    strategy: ParallelRepoStrategy, repo: Path, tmp_path: Path
) -> None:
    git(repo, "branch", "agent/gamma")
    merged: list[str] = []
    strategy.worktree_fleet(
        ["agent/gamma"],
        root=tmp_path / "fleet2",
        merge_back=lambda branch: merged.append(branch),
    )
    assert merged == ["agent/gamma"]


def test_fleet_refuses_occupied_path(
    strategy: ParallelRepoStrategy, repo: Path, tmp_path: Path
) -> None:
    git(repo, "branch", "agent/delta")
    # the fleet maps branch → root/agent-delta; occupy that final path
    occupied = tmp_path / "agent-delta"
    occupied.mkdir()
    (occupied / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(GitEngineError):
        strategy.worktree_fleet(["agent/delta"], root=tmp_path)


# ----------------------------------------------------------------- checkpoint


def test_checkpoint_tag_is_annotated_and_real(
    strategy: ParallelRepoStrategy, engine: GitEngine
) -> None:
    plan, tag = strategy.checkpoint("risky-parser-rewrite")
    assert tag == "checkpoint/risky-parser-rewrite"
    tags = {t.name: t for t in engine.tags()}
    assert tags[tag].annotated is True
    assert "risky-parser-rewrite" in tags[tag].message


# -------------------------------------------------------------------- release


def test_release_refused_without_tests_and_review(strategy: ParallelRepoStrategy) -> None:
    with pytest.raises(StrategyError, match="tests"):
        strategy.finish_release("v1.0.0", tests_passed=False, review_approved=True)
    with pytest.raises(StrategyError, match="review"):
        strategy.finish_release("v1.0.0", tests_passed=True, review_approved=False)
    with pytest.raises(StrategyError) as both:
        strategy.finish_release("v1.0.0", tests_passed=False, review_approved=False)
    assert "tests" in str(both.value) and "review" in str(both.value)


def test_release_tag_only_after_the_123_gate(
    strategy: ParallelRepoStrategy, engine: GitEngine
) -> None:
    strategy.finish_release(
        "v0.16.0",
        tests_passed=True,
        review_approved=True,
        message="PHASE 16 — Git / GitHub",
    )
    tags = {t.name: t for t in engine.tags()}
    assert "v0.16.0" in tags
    assert tags["v0.16.0"].message == "PHASE 16 — Git / GitHub"


# ------------------------------------------------------------------- events


def test_strategy_events_canonical(
    strategy: ParallelRepoStrategy, bus: EventBus, engine: GitEngine
) -> None:
    strategy.feature_branch("evt-task")
    strategy.checkpoint("evt-risky")
    names = {e.name for e in bus.history_snapshot()}
    assert names <= {"tool.called", "tool.completed"}
    assert bus.published_count >= 2
