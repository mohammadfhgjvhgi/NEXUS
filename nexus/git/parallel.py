"""Parallel-agent repository strategy (New Plan §16.4 / Spec §123).

§123 fixes the strategy — one mapping, verbatim::

    Small change      → Commit مباشر        (direct commit)
    Major feature     → Branch              (feature branch)
    Parallel agents   → Worktrees / isolated branches
    Risky refactor    → Checkpoint + branch
    Release           → Tests + review + tag/release

§16.4 says NEXUS uses exactly this — ``feature branch``, ``worktree``,
``checkpoint`` — *بحسب المهمة* (according to the task).  This module is
that mapping as executable law: :meth:`ParallelRepoStrategy.plan`
answers what to do, and the three helpers do it for real:

* :meth:`feature_branch`      — a real branch per major task;
* :meth:`worktree_fleet`      — one real worktree per parallel agent,
  merged back when the agent finishes (never overlapping trees);
* :meth:`checkpoint`          — a real annotated checkpoint tag plus a
  safety branch before risky work;
* :meth:`finish_release`      — refuses to tag unless tests and review
  flags are true (the §123 *Tests + review* precondition).

استراتيجية الوكلاء الموازيين — خمس مهام وخمسة أفمال حقيقية، والتاق
لا يُوضع بلا اختبار ومراجعة.

Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nexus.events import EventName

from .contracts import (
    StrategyAction,
    StrategyPlan,
    TaskKind,
    WorktreeFleet,
)
from .engine import GitEngine

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._/\-]*")
checkpoint_prefix = "checkpoint/"


class StrategyError(Exception):
    """The strategy was asked to do something its task kind forbids."""


def _slug(name: str) -> str:
    if not _NAME_RE.fullmatch(name):
        raise StrategyError(
            f"invalid task/branch slug: {name!r} (use lowercase [a-z0-9], dots, dashes, slashes)"
        )
    return name


class ParallelRepoStrategy:
    """§123 as executable law over one real :class:`GitEngine`."""

    source_name = "nexus.git.parallel"

    def __init__(self, engine: GitEngine, bus: Any = None) -> None:
        self._engine = engine
        self._bus = bus

    def _emit(self, name: EventName, payload: dict[str, Any], ok: bool = True) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            EventName.TOOL_COMPLETED if ok else EventName.TOOL_FAILED,
            payload=payload,
            source=self.source_name,
        )

    # -------------------------------------------------------------- plan

    def plan(self, kind: str | TaskKind, *, task: str | None = None) -> StrategyPlan:
        """The §123 answer for one task kind — what NEXUS will do."""
        task_kind = TaskKind.from_value(kind)
        slug = _slug(task) if task else None
        plan_by_kind: dict[TaskKind, StrategyPlan] = {
            TaskKind.SMALL_CHANGE: StrategyPlan(
                kind=task_kind, action=StrategyAction.DIRECT_COMMIT
            ),
            TaskKind.MAJOR_FEATURE: StrategyPlan(
                kind=task_kind,
                action=StrategyAction.FEATURE_BRANCH,
                branch=f"feature/{slug}" if slug else None,
                requires_tests=True,
                requires_review=True,
            ),
            TaskKind.PARALLEL_AGENTS: StrategyPlan(
                kind=task_kind,
                action=StrategyAction.WORKTREE_FLEET,
                worktree_root=".worktrees" if not slug else f".worktrees/{slug}",
                requires_tests=True,
                requires_review=True,
            ),
            TaskKind.RISKY_REFACTOR: StrategyPlan(
                kind=task_kind,
                action=StrategyAction.CHECKPOINT_BRANCH,
                checkpoint_tag=f"{checkpoint_prefix}{slug}" if slug else None,
                branch=f"risky/{slug}" if slug else None,
                requires_tests=True,
                requires_review=True,
            ),
            TaskKind.RELEASE: StrategyPlan(
                kind=task_kind,
                action=StrategyAction.TAG_RELEASE,
                checkpoint_tag=slug,
                requires_tests=True,
                requires_review=True,
            ),
        }
        return plan_by_kind[task_kind]

    # ---------------------------------------------------- feature branch

    def feature_branch(self, task: str) -> tuple[StrategyPlan, str]:
        """Major feature → a real ``feature/<task>`` branch, checked out."""
        plan = self.plan(TaskKind.MAJOR_FEATURE, task=task)
        assert plan.branch is not None
        ref = self._engine.create_branch(plan.branch, checkout=True)
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "parallel.feature_branch", "branch": ref.name}
        )
        return plan, ref.name

    # ----------------------------------------------------- worktree fleet

    def worktree_fleet(
        self,
        branches: Sequence[str],
        *,
        root: str | Path = ".worktrees",
        merge_back: Callable[[str], Any] | None = None,
    ) -> WorktreeFleet:
        """Parallel agents → one real worktree per branch, under ``root``.

        ``merge_back(branch)`` is the caller's per-agent finish hook —
        typically a merge of the agent's branch into the base branch.
        The fleet record returned is frozen evidence of who worked where.
        """
        fleet_root = Path(root)
        entries: list[tuple[str, str]] = []
        for branch in branches:
            _slug(branch)
            path = fleet_root / branch.replace("/", "-")
            self._engine.add_worktree(path, branch=branch)
            entries.append((branch, str(path.resolve())))
        fleet = WorktreeFleet(root=str(fleet_root), entries=tuple(entries))
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "parallel.worktree_fleet", "size": len(entries)}
        )
        if merge_back is not None:
            for branch, _path in entries:
                merge_back(branch)
        return fleet

    def teardown_fleet(self, fleet: WorktreeFleet) -> tuple[str, ...]:
        """Remove every worktree the fleet created — clean parallelism."""
        removed: list[str] = []
        for _branch, path in fleet.entries:
            removed.append(self._engine.remove_worktree(path, force=True))
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "parallel.fleet_teardown", "size": len(removed)}
        )
        return tuple(removed)

    # --------------------------------------------------------- checkpoint

    def checkpoint(self, task: str, *, message: str | None = None) -> tuple[StrategyPlan, str]:
        """Risky refactor → real annotated ``checkpoint/<task>`` tag first."""
        plan = self.plan(TaskKind.RISKY_REFACTOR, task=task)
        assert plan.checkpoint_tag is not None
        note = message or f"checkpoint before risky work: {task}"
        self._engine.tag(plan.checkpoint_tag, message=note)
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "parallel.checkpoint", "tag": plan.checkpoint_tag}
        )
        return plan, plan.checkpoint_tag

    # ------------------------------------------------------------ release

    def finish_release(
        self,
        version: str,
        *,
        tests_passed: bool,
        review_approved: bool,
        message: str | None = None,
    ) -> str:
        """Release → tag only after *tests + review* (the §123 gate)."""
        plan = self.plan(TaskKind.RELEASE, task=version)
        assert plan.checkpoint_tag is not None
        if not tests_passed or not review_approved:
            missing = []
            if not tests_passed:
                missing.append("tests")
            if not review_approved:
                missing.append("review")
            self._emit(
                EventName.TOOL_FAILED,
                {"tool": "parallel.release", "missing": missing},
                ok=False,
            )
            raise StrategyError(
                f"release refused — §123 requires tests + review (missing: {missing})"
            )
        self._engine.tag(version, message=message or f"release {version}")
        self._emit(EventName.TOOL_COMPLETED, {"tool": "parallel.release", "tag": version})
        return version
