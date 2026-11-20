"""NEXUS Recovery System (New Plan §22 — PHASE 22).

*أي Task كبيرة يجب أن تكون قابلة للاستعادة.*
(Any large Task must be recoverable.)

The four sections::

    22.1  Checkpoint Manager   — Task · Project · Git · State
    22.2  Trigger Events       — task start · phase complete · major
                                 change · critical test · before
                                 risky change · periodic
    22.3  Recovery             — Crash → Checkpoint → Actual
                                 environment → Reconciliation →
                                 Resume
    22.4  No Blind Resume      — لا يعتمد على الذاكرة. يفحص:
                                 Files · Git · Processes · Windows ·
                                 Browser · Task state

The §22.4 law is structural: :class:`RecoveryEngine.reconcile` probes
the actual machine live and :meth:`RecoveryEngine.resume` raises
:class:`NoBlindResumeError` unless all six surfaces passed — there is
no code path in this package that resumes on drift.

Stdlib only.
"""

from __future__ import annotations

from .checkpoint import CheckpointManager, TriggerPolicy
from .contracts import (
    CHECKPOINT_SCOPES,
    RECOVERY_CHAIN,
    RECOVERY_SCHEMA_VERSION,
    TRIGGER_EVENTS,
    VERIFICATION_SURFACES,
    CheckpointManifest,
    CheckpointNotFoundError,
    CheckpointScope,
    CorruptCheckpointError,
    Drift,
    DriftKind,
    DriftSeverity,
    EnvironmentFacts,
    FileEntry,
    NoBlindResumeError,
    ReconciliationReport,
    RecoveryAction,
    RecoveryError,
    RecoveryOutcome,
    RecoveryVerdict,
    TriggerEvent,
    VerificationSurface,
)
from .engine import RecoveryEngine, verify_tree
from .probes import (
    BROWSER_MARKERS,
    CompositeProbe,
    FilesProbe,
    GitProbe,
    ProcessProbe,
    TaskStateProbe,
    WindowProbe,
    browser_markers,
    capture_expectations,
    inventory_files,
)
from .store import DiskCheckpointStore, new_checkpoint_id

__all__ = [
    "CHECKPOINT_SCOPES",
    "RECOVERY_CHAIN",
    "RECOVERY_SCHEMA_VERSION",
    "TRIGGER_EVENTS",
    "VERIFICATION_SURFACES",
    "BROWSER_MARKERS",
    "CheckpointManager",
    "CheckpointManifest",
    "CheckpointNotFoundError",
    "CheckpointScope",
    "CompositeProbe",
    "CorruptCheckpointError",
    "DiskCheckpointStore",
    "Drift",
    "DriftKind",
    "DriftSeverity",
    "EnvironmentFacts",
    "FileEntry",
    "FilesProbe",
    "GitProbe",
    "NoBlindResumeError",
    "ProcessProbe",
    "ReconciliationReport",
    "RecoveryAction",
    "RecoveryEngine",
    "RecoveryError",
    "RecoveryOutcome",
    "RecoveryVerdict",
    "TaskStateProbe",
    "TriggerEvent",
    "TriggerPolicy",
    "VerificationSurface",
    "WindowProbe",
    "browser_markers",
    "capture_expectations",
    "inventory_files",
    "new_checkpoint_id",
    "verify_tree",
]
