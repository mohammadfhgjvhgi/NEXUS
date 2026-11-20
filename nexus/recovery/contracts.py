"""Recovery-system contracts (New Plan §22.1–§22.4).

The plan's central claim, verbatim:

    أي Task كبيرة يجب أن تكون قابلة للاستعادة.
    (Any large Task must be recoverable.)

The four sections, verbatim::

    22.1  Checkpoint Manager   — Task · Project · Git · State
    22.2  Trigger Events       — task start · phase complete ·
                                 major change · critical test ·
                                 before risky change · periodic
    22.3  Recovery             — Crash → Checkpoint → Actual
                                 environment → Reconciliation →
                                 Resume
    22.4  No Blind Resume      — لا يعتمد على الذاكرة. يفحص:
                                 Files · Git · Processes · Windows ·
                                 Browser · Task state

The law of the section is §22.4: a resume decision is never made from
memory.  :meth:`RecoveryEngine.reconcile` re-probes the *actual*
environment through :class:`EnvironmentProbe` (disk · git · processes ·
windows · browser · task state) and compares it against the
:class:`CheckpointManifest` — the only resume that exists is the one
that survived reconciliation.  The §22.3 chain is a literal pipeline:
every stage of it is observable in the returned
:class:`RecoveryOutcome`.

عقود نظام الاستعادة والنقاط المرجعية — أربع نطاقات، ستة مشغلات،
سلسلة استعادة خماسية، وستة فحوص إلزامية قبل أي استئناف. لا استئناف
أعمى.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..verification.contracts import utc_now_iso

RECOVERY_SCHEMA_VERSION = 1

# ----------------------------------------------------------------- errors


class RecoveryError(Exception):
    """Recovery-system misuse or operation failure."""


class CheckpointNotFoundError(RecoveryError):
    """The requested checkpoint id does not exist in the store."""


class CorruptCheckpointError(RecoveryError):
    """A stored checkpoint exists but cannot be trusted (bad manifest)."""


class NoBlindResumeError(RecoveryError):
    """The §22.4 hard stop — resume demanded without reconciliation.

    There is no code path in this package that returns ``resume``
    unless every one of the six verification surfaces passed against a
    live probe.  Raising this is the structural proof of that law.
    """


# ------------------------------------------------------- §22 vocabulary


class CheckpointScope(StrEnum):
    """§22.1 — the four capture targets, verbatim and in order."""

    TASK = "task"
    PROJECT = "project"
    GIT = "git"
    STATE = "state"


class TriggerEvent(StrEnum):
    """§22.2 — the six trigger events, verbatim and in order."""

    TASK_START = "task_start"
    PHASE_COMPLETE = "phase_complete"
    MAJOR_CHANGE = "major_change"
    CRITICAL_TEST = "critical_test"
    BEFORE_RISKY_CHANGE = "before_risky_change"
    PERIODIC = "periodic"


class VerificationSurface(StrEnum):
    """§22.4 — the six mandatory checks before any resume, verbatim."""

    FILES = "files"
    GIT = "git"
    PROCESSES = "processes"
    WINDOWS = "windows"
    BROWSER = "browser"
    TASK_STATE = "task_state"


#: §22.3 — the recovery chain, verbatim and in order.  ``recover``
#: walks it stage by stage and the outcome names where it stopped.
RECOVERY_CHAIN: tuple[str, ...] = (
    "crash",
    "checkpoint",
    "actual_environment",
    "reconciliation",
    "resume",
)

#: §22.1 — the four scopes, verbatim tuple form (the enum is the typed
#: twin; this tuple is the verbatim vocabulary the tests pin).
CHECKPOINT_SCOPES: tuple[str, ...] = (
    "task",
    "project",
    "git",
    "state",
)

#: §22.2 — the six trigger events, verbatim tuple form.
TRIGGER_EVENTS: tuple[str, ...] = (
    "task_start",
    "phase_complete",
    "major_change",
    "critical_test",
    "before_risky_change",
    "periodic",
)

#: §22.4 — the six verification surfaces, verbatim tuple form.
VERIFICATION_SURFACES: tuple[str, ...] = (
    "files",
    "git",
    "processes",
    "windows",
    "browser",
    "task_state",
)


class DriftKind(StrEnum):
    """One named way the actual environment left the checkpoint."""

    FILE_MISSING = "file_missing"
    FILE_MODIFIED = "file_modified"
    FILE_EXTRA = "file_extra"
    GIT_DIVERGED = "git_diverged"
    GIT_DIRTY = "git_dirty"
    PROCESS_DEAD = "process_dead"
    WINDOW_CLOSED = "window_closed"
    BROWSER_CHANGED = "browser_changed"
    TASK_STATE_MISMATCH = "task_state_mismatch"


class DriftSeverity(StrEnum):
    """Errors block resume (§22.4); warnings only annotate."""

    ERROR = "error"
    WARNING = "warning"


class RecoveryVerdict(StrEnum):
    """The reconciliation verdict — the §22.3 gate word."""

    RESUME_READY = "resume_ready"
    DRIFT_DETECTED = "drift_detected"
    UNRECOVERABLE = "unrecoverable"


class RecoveryAction(StrEnum):
    """What the caller must do with the outcome."""

    RESUME = "resume"
    RESTART_TASK = "restart_task"
    ABORT = "abort"


# ---------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class FileEntry:
    """One inventoried file — path (posix-style, relative) + digest."""

    path: str
    sha256: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FileEntry:
        return cls(
            path=str(data["path"]),
            sha256=str(data["sha256"]),
            size=int(data["size"]),
        )


@dataclass(frozen=True)
class CheckpointManifest:
    """The checkpoint header — everything recovery is allowed to know.

    Written once at capture time, stored on disk (never memory), and
    the *only* thing §22.4 reconciliation compares the live probe
    against.  ``state`` carries the scope payload: ``task_state`` for
    Task scope, ``environment`` expectations (processes · windows ·
    browser) for every scope, the dirty flag for Git scope.
    """

    checkpoint_id: str
    scope: CheckpointScope
    trigger: TriggerEvent
    label: str
    created_at_utc: str
    nexus_version: str
    nexus_phase: int
    git_head: str | None = None
    git_branch: str | None = None
    files: tuple[FileEntry, ...] = ()
    state: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = RECOVERY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "scope": self.scope.value,
            "trigger": self.trigger.value,
            "label": self.label,
            "created_at_utc": self.created_at_utc,
            "nexus_version": self.nexus_version,
            "nexus_phase": self.nexus_phase,
            "git_head": self.git_head,
            "git_branch": self.git_branch,
            "files": [f.as_dict() for f in self.files],
            "state": dict(self.state),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CheckpointManifest:
        try:
            version = int(data["schema_version"])
            if version != RECOVERY_SCHEMA_VERSION:
                raise CorruptCheckpointError(
                    f"schema_version {version} != {RECOVERY_SCHEMA_VERSION}"
                )
            return cls(
                checkpoint_id=str(data["checkpoint_id"]),
                scope=CheckpointScope(str(data["scope"])),
                trigger=TriggerEvent(str(data["trigger"])),
                label=str(data.get("label", "")),
                created_at_utc=str(data["created_at_utc"]),
                nexus_version=str(data.get("nexus_version", "")),
                nexus_phase=int(data.get("nexus_phase", 0)),
                git_head=data.get("git_head"),
                git_branch=data.get("git_branch"),
                files=tuple(FileEntry.from_dict(f) for f in data.get("files", [])),
                state=dict(data.get("state", {})),
                schema_version=version,
            )
        except CorruptCheckpointError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise CorruptCheckpointError(f"bad manifest: {exc}") from exc


@dataclass(frozen=True)
class EnvironmentFacts:
    """The *actual* environment, probed live — never from memory.

    One fact per §22.4 surface: files (path → sha256) · git (head,
    branch, dirty) · processes (running names) · windows (visible
    titles) · browser (browser markers among the processes) ·
    task_state (the persisted task-state document).
    """

    files: Mapping[str, str] = field(default_factory=dict)
    git_head: str | None = None
    git_branch: str | None = None
    git_dirty: bool = False
    processes: tuple[str, ...] = ()
    windows: tuple[str, ...] = ()
    browser: tuple[str, ...] = ()
    task_state: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    probed_at_utc: str = field(default_factory=utc_now_iso)

    def surface(self, which: VerificationSurface) -> Any:
        """One surface's live fact — the §22.4 six, addressed by name."""
        return {
            VerificationSurface.FILES: self.files,
            VerificationSurface.GIT: (self.git_head, self.git_branch, self.git_dirty),
            VerificationSurface.PROCESSES: self.processes,
            VerificationSurface.WINDOWS: self.windows,
            VerificationSurface.BROWSER: self.browser,
            VerificationSurface.TASK_STATE: self.task_state,
        }[which]


@dataclass(frozen=True)
class Drift:
    """One observed difference between checkpoint and reality."""

    surface: VerificationSurface
    kind: DriftKind
    severity: DriftSeverity
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface.value,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ReconciliationReport:
    """The §22.3 reconciliation verdict over the six §22.4 surfaces."""

    checkpoint_id: str
    verdict: RecoveryVerdict
    matched: tuple[VerificationSurface, ...] = ()
    drift: tuple[Drift, ...] = ()
    checked_at_utc: str = field(default_factory=utc_now_iso)

    def ok(self) -> bool:
        return self.verdict is RecoveryVerdict.RESUME_READY

    def errors(self) -> tuple[Drift, ...]:
        return tuple(d for d in self.drift if d.severity is DriftSeverity.ERROR)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "verdict": self.verdict.value,
            "matched": [s.value for s in self.matched],
            "drift": [d.as_dict() for d in self.drift],
            "checked_at_utc": self.checked_at_utc,
        }


@dataclass(frozen=True)
class RecoveryOutcome:
    """The §22.3 chain result — where the walk stopped and why.

    ``stages`` lists the chain prefixes actually walked (crash →
    checkpoint → actual_environment → reconciliation, plus resume
    only when the verdict earned it).
    """

    checkpoint_id: str
    report: ReconciliationReport
    action: RecoveryAction
    detail: str = ""
    restored_files: int = 0
    at_utc: str = field(default_factory=utc_now_iso)

    @property
    def stages(self) -> tuple[str, ...]:
        walked: list[str] = list(RECOVERY_CHAIN[:4])
        if self.action is RecoveryAction.RESUME:
            walked.append("resume")
        return tuple(walked)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "action": self.action.value,
            "detail": self.detail,
            "restored_files": self.restored_files,
            "at_utc": self.at_utc,
            "stages": list(self.stages),
            "report": self.report.as_dict(),
        }
