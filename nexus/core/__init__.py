"""NEXUS Core (Final Build Plan §2 + §3).

Phase 1 (§2) — Core Foundation:

* ``nexus.core.config``      — typed configuration, environment
                                resolution, local paths, runtime
                                configuration (§2.1)
* ``nexus.core.engine``      — Task State Machine, 13 states (§2.4)
* ``nexus.core.persistence`` — Task persistence, 11 fields (§2.5)
* ``nexus.core.session``     — User → Conversation → Task → Session (§2.3)

Phase 2 (§3) — Workspace + Scope + Policy:

* ``nexus.core.workspace``   — workspace registry (§3.1)
* ``nexus.core.scope``       — six-dimension scope, resolution,
                                cross-workspace access (§3.2–§3.4)
* ``nexus.core.policy``      — task policies and decisions (§3.5)

``TaskEngine`` is imported from ``nexus.core.engine.machine`` (not
re-exported by the engine package) to keep the import graph acyclic —
see the docstring in :mod:`nexus.core.engine`.
"""

from .config import (
    ConfigError,
    NexusConfig,
    NexusPaths,
    NexusRuntime,
    load_config,
    resolve_paths,
)
from .engine.machine import TaskEngine
from .engine.states import (
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    TaskState,
    TransitionRecord,
    can_transition,
)
from .persistence import (
    PersistenceError,
    TaskRepository,
    TaskSummary,
    task_from_record,
    task_to_record,
)
from .policy import (
    POLICY_COMPONENTS,
    ActionType,
    AutonomyLevel,
    PolicyAction,
    PolicyDecision,
    PolicyEngine,
    TaskPolicy,
)
from .scope import (
    SCOPE_DIMENSIONS,
    CrossWorkspaceAccess,
    Scope,
    ScopeEngine,
    ScopeResolution,
    keywords_for,
    path_tokens,
)
from .session import (
    CheckpointRef,
    Conversation,
    PlanStep,
    ScopeMap,
    Session,
    SessionError,
    SessionManager,
    StepStatus,
    Task,
    TaskError,
    TaskPlan,
    TaskResult,
    User,
    VerificationCheck,
    VerificationRecord,
    VerificationStatus,
)
from .workspace import (
    REGISTRY_SCHEMA,
    REGISTRY_VERSION,
    Workspace,
    WorkspaceError,
    WorkspaceManager,
)

__all__ = [
    "POLICY_COMPONENTS",
    "REGISTRY_SCHEMA",
    "REGISTRY_VERSION",
    "SCOPE_DIMENSIONS",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "ActionType",
    "AutonomyLevel",
    "CheckpointRef",
    "ConfigError",
    "Conversation",
    "CrossWorkspaceAccess",
    "InvalidTransitionError",
    "NexusConfig",
    "NexusPaths",
    "NexusRuntime",
    "PersistenceError",
    "PlanStep",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "Scope",
    "ScopeEngine",
    "ScopeMap",
    "ScopeResolution",
    "Session",
    "SessionError",
    "SessionManager",
    "StepStatus",
    "Task",
    "TaskEngine",
    "TaskError",
    "TaskPlan",
    "TaskPolicy",
    "TaskRepository",
    "TaskResult",
    "TaskSummary",
    "TaskState",
    "TransitionRecord",
    "User",
    "VerificationCheck",
    "VerificationRecord",
    "VerificationStatus",
    "Workspace",
    "WorkspaceError",
    "WorkspaceManager",
    "can_transition",
    "keywords_for",
    "load_config",
    "path_tokens",
    "resolve_paths",
    "task_from_record",
    "task_to_record",
]
