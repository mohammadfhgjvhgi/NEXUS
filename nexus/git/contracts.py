"""Git-engine contracts (New Plan §16.1 · §16.3 · §16.4).

The phase thesis — GitHub stops being a storage place and becomes part
of the NEXUS runtime. §16.1 fixes the Git Engine vocabulary — eight
operations, verbatim::

    status   diff   branch   worktree   commit   merge   tag   rollback

§16.3 fixes the repository lifecycle — eight stages, this exact order::

    Discover → Clone → Index → Modify → Test → Commit → Review → Push

§16.4 fixes the parallel-agent strategy (Spec §123, verbatim mapping)::

    Small change    → direct commit
    Major feature   → feature branch
    Parallel agents → worktrees / isolated branches
    Risky refactor  → checkpoint + branch
    Release         → tests + review + tag/release

NEXUS owns the git semantics (Plan §61): the engine drives the real
``git`` binary through a bounded subprocess surface, reports the
binary's absence honestly (the Core stays stdlib-only — no git-python),
and publishes only the canonical §2.2 events.

عقود محرك Git — ثماني عمليات ومسار ثماني مراحل وخمس استراتيجيات
موازية بهذا الترتيب حرفيًا؛ الثنائية الحقيقية حَكَم والغياب يُعلن بصدق.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ------------------------------------------------------------- §16.1 kinds


class GitEngineError(Exception):
    """Git-engine misuse or operation failure."""


class InvalidRepoError(GitEngineError):
    """The target path is not a working git repository."""


class GitBinaryMissingError(GitEngineError):
    """The ``git`` executable is absent — reported honestly, never faked."""


class DirtyRepoError(GitEngineError):
    """A destructive action (rollback/checkout) would lose uncommitted work."""


class MergeConflictError(GitEngineError):
    """A merge stopped with real conflicts — NEXUS never auto-solves them."""


#: §16.1 — the eight operations, verbatim (the plan's snake_case names).
GIT_OPERATIONS: tuple[str, ...] = (
    "status",
    "diff",
    "branch",
    "worktree",
    "commit",
    "merge",
    "tag",
    "rollback",
)


class GitOperationKind(Enum):
    """The §16.1 operation vocabulary — exactly eight members."""

    STATUS = "status"
    DIFF = "diff"
    BRANCH = "branch"
    WORKTREE = "worktree"
    COMMIT = "commit"
    MERGE = "merge"
    TAG = "tag"
    ROLLBACK = "rollback"

    @classmethod
    def from_value(cls, value: str | GitOperationKind) -> GitOperationKind:
        """Coerce a plan name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        for member in cls:
            if member.value == name:
                return member
        raise GitEngineError(f"unknown git operation: {value!r}")


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds."""
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------- §16.1 result shapes


@dataclass(frozen=True, slots=True)
class StatusReport:
    """The ``status`` answer — branch, divergence, and the three buckets."""

    branch: str
    head_sha: str
    clean: bool
    staged: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    untracked: tuple[str, ...] = ()
    ahead: int = 0
    behind: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "head_sha": self.head_sha,
            "clean": self.clean,
            "staged": list(self.staged),
            "modified": list(self.modified),
            "untracked": list(self.untracked),
            "ahead": self.ahead,
            "behind": self.behind,
        }


@dataclass(frozen=True, slots=True)
class DiffSummary:
    """The ``diff`` answer — which files, how many lines, optional patch."""

    files: tuple[str, ...]
    insertions: int
    deletions: int
    patch: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "insertions": self.insertions,
            "deletions": self.deletions,
            "patch": self.patch,
        }


@dataclass(frozen=True, slots=True)
class BranchRef:
    """One local or remote branch."""

    name: str
    current: bool
    commit: str
    remote: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current": self.current,
            "commit": self.commit,
            "remote": self.remote,
        }


@dataclass(frozen=True, slots=True)
class WorktreeEntry:
    """One ``worktree`` entry — the main tree or a linked one."""

    path: str
    head: str
    branch: str | None
    bare: bool = False
    detached: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "head": self.head,
            "branch": self.branch,
            "bare": self.bare,
            "detached": self.detached,
        }


@dataclass(frozen=True, slots=True)
class CommitResult:
    """The ``commit`` answer — the new sha and what it carried."""

    sha: str
    short_sha: str
    message: str
    files: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "message": self.message,
            "files": list(self.files),
        }


@dataclass(frozen=True, slots=True)
class MergeResult:
    """The ``merge`` answer — fast-forward, merge-commit, or conflict."""

    merged: bool
    fast_forward: bool
    conflicted: tuple[str, ...] = ()
    sha: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "merged": self.merged,
            "fast_forward": self.fast_forward,
            "conflicted": list(self.conflicted),
            "sha": self.sha,
        }


@dataclass(frozen=True, slots=True)
class TagRecord:
    """The ``tag`` answer — a lightweight or annotated tag."""

    name: str
    commit: str
    annotated: bool
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "commit": self.commit,
            "annotated": self.annotated,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """The ``rollback`` answer — where HEAD moved and what was preserved."""

    from_sha: str
    to_sha: str
    safety_branch: str | None = None
    hard: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_sha": self.from_sha,
            "to_sha": self.to_sha,
            "safety_branch": self.safety_branch,
            "hard": self.hard,
        }


#: Every §16.1 operation returns one of these shapes (or a tuple of them).
RESULT_KINDS: Mapping[str, tuple[type[Any], ...]] = {
    "status": (StatusReport,),
    "diff": (DiffSummary,),
    "branch": (BranchRef,),
    "worktree": (WorktreeEntry,),
    "commit": (CommitResult,),
    "merge": (MergeResult,),
    "tag": (TagRecord,),
    "rollback": (RollbackResult,),
}

# --------------------------------------------------------- §16.3 lifecycle


#: §16.3 — the eight lifecycle stages, verbatim, in order.
LIFECYCLE_STAGES: tuple[str, ...] = (
    "discover",
    "clone",
    "index",
    "modify",
    "test",
    "commit",
    "review",
    "push",
)


class LifecycleError(GitEngineError):
    """A lifecycle stage failed or the pipeline was misused."""


class ReviewRejectedError(LifecycleError):
    """The reviewer said no — the pipeline stops honestly, never spins."""


class StageState(Enum):
    """Per-stage outcome — the lifecycle never lies about a stage."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class StageResult:
    """One stage of the §16.3 lifecycle."""

    stage: str
    state: StageState = StageState.PENDING
    started_at: str = ""
    finished_at: str = ""
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def mark(self, state: StageState, detail: str = "") -> None:
        self.state = state
        self.detail = detail
        self.finished_at = utc_now_iso()

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "detail": self.detail,
            "data": self.data,
        }


@dataclass(slots=True)
class LifecycleReport:
    """The full §16.3 pipeline answer — eight stages in order."""

    stages: list[StageResult] = field(default_factory=list)
    repo_path: str = ""
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = ""

    def stage(self, name: str) -> StageResult:
        for entry in self.stages:
            if entry.stage == name:
                return entry
        raise LifecycleError(f"unknown stage: {name!r}")

    @property
    def ok(self) -> bool:
        return all(
            entry.state in (StageState.OK, StageState.SKIPPED)
            for entry in self.stages
        )

    @property
    def reached(self) -> str:
        """The last stage that finished (ok or failed) — honest progress."""
        for entry in reversed(self.stages):
            if entry.state is not StageState.PENDING:
                return entry.stage
        return ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reached": self.reached,
            "repo_path": self.repo_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stages": [entry.as_dict() for entry in self.stages],
        }


# ------------------------------------------------------- §16.4 parallel §123


#: §16.4 / Spec §123 — the task-size vocabulary, verbatim concepts.
TASK_KINDS: tuple[str, ...] = (
    "small_change",
    "major_feature",
    "parallel_agents",
    "risky_refactor",
    "release",
)


class TaskKind(Enum):
    """The §123 strategy input — exactly five members."""

    SMALL_CHANGE = "small_change"
    MAJOR_FEATURE = "major_feature"
    PARALLEL_AGENTS = "parallel_agents"
    RISKY_REFACTOR = "risky_refactor"
    RELEASE = "release"

    @classmethod
    def from_value(cls, value: str | TaskKind) -> TaskKind:
        """Coerce a plan name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        for member in cls:
            if member.value == name:
                return member
        raise GitEngineError(f"unknown task kind: {value!r}")


class StrategyAction(Enum):
    """What the strategy will do — one action per §123 row."""

    DIRECT_COMMIT = "direct_commit"
    FEATURE_BRANCH = "feature_branch"
    WORKTREE_FLEET = "worktree_fleet"
    CHECKPOINT_BRANCH = "checkpoint_branch"
    TAG_RELEASE = "tag_release"


@dataclass(frozen=True, slots=True)
class StrategyPlan:
    """The §123 answer for one task kind."""

    kind: TaskKind
    action: StrategyAction
    branch: str | None = None
    checkpoint_tag: str | None = None
    worktree_root: str | None = None
    requires_tests: bool = False
    requires_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "action": self.action.value,
            "branch": self.branch,
            "checkpoint_tag": self.checkpoint_tag,
            "worktree_root": self.worktree_root,
            "requires_tests": self.requires_tests,
            "requires_review": self.requires_review,
        }


@dataclass(frozen=True, slots=True)
class WorktreeFleet:
    """One worktree per parallel agent — branch → path, never overlapping."""

    root: str
    entries: tuple[tuple[str, str], ...]  # (branch, path)

    def as_dict(self) -> dict[str, Any]:
        return {"root": self.root, "entries": [{"branch": b, "path": p} for b, p in self.entries]}


#: §16.4 / §123 — the five task kinds map 1:1 onto the five actions.
STRATEGY_CARDINALITY: Mapping[str, int] = {
    "task_kinds": len(TASK_KINDS),
    "strategy_actions": 5,
}
