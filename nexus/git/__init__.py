"""NEXUS Git Engine package (New Plan §16 — PHASE 16).

GitHub stops being a storage place and becomes part of the runtime.

=========================  =======================================  ==================
Component                  Plan source                              Module
=========================  =======================================  ==================
Git Engine (8 ops)         §16.1 (status · diff · branch ·          contracts · engine
                           worktree · commit · merge · tag ·
                           rollback)
Repository Lifecycle       §16.3 (Discover → Clone → Index →        lifecycle
                           Modify → Test → Commit → Review → Push)
Parallel Agents            §16.4 / Spec §123 (feature branch ·      parallel
                           worktree · checkpoint — بحسب المهمة)
=========================  =======================================  ==================

The engine drives the real ``git`` binary through a bounded subprocess
surface (Spec §198 includes push/pull as network helpers); its absence
is reported honestly, conflicts surface instead of being auto-solved,
and every rollback saves the work it would destroy.  The lifecycle is
the §16.3 eight-stage pipeline with a verdict per stage — the review
gate stops on rejection, never spins.  The strategy is §123 as
executable law: direct commit / feature branch / worktree fleet /
checkpoint + branch / tag release.

محرك Git — الثنائية الحقيقية حَكَم، والتقرير لا يكذب أبدًا.

Stdlib only.
"""

from .contracts import (
    GIT_OPERATIONS,
    LIFECYCLE_STAGES,
    RESULT_KINDS,
    STRATEGY_CARDINALITY,
    TASK_KINDS,
    BranchRef,
    CommitResult,
    DiffSummary,
    DirtyRepoError,
    GitBinaryMissingError,
    GitEngineError,
    GitOperationKind,
    InvalidRepoError,
    LifecycleError,
    LifecycleReport,
    MergeConflictError,
    MergeResult,
    ReviewRejectedError,
    RollbackResult,
    StageResult,
    StageState,
    StatusReport,
    StrategyAction,
    StrategyPlan,
    TagRecord,
    TaskKind,
    WorktreeEntry,
    WorktreeFleet,
)
from .engine import GitEngine
from .lifecycle import RepoLifecycle, detect_stack
from .parallel import ParallelRepoStrategy

__all__ = [
    "GIT_OPERATIONS",
    "LIFECYCLE_STAGES",
    "RESULT_KINDS",
    "STRATEGY_CARDINALITY",
    "TASK_KINDS",
    "BranchRef",
    "CommitResult",
    "DiffSummary",
    "DirtyRepoError",
    "GitBinaryMissingError",
    "GitEngine",
    "GitEngineError",
    "GitOperationKind",
    "InvalidRepoError",
    "LifecycleError",
    "LifecycleReport",
    "MergeConflictError",
    "MergeResult",
    "ParallelRepoStrategy",
    "RepoLifecycle",
    "ReviewRejectedError",
    "RollbackResult",
    "StageResult",
    "StageState",
    "StatusReport",
    "StrategyAction",
    "StrategyPlan",
    "TagRecord",
    "TaskKind",
    "WorktreeEntry",
    "WorktreeFleet",
    "detect_stack",
]
