"""Health-system contracts (New Plan §23.1–§23.3).

The plan's central claim, verbatim::

    منع التوقف الصامت.
    (Prevent the silent stall.)

The three sections, verbatim::

    23.1  Heartbeat        — يراقب: Core · Agent · Model · Tool ·
                             Browser · Computer · Task
    23.2  Stall Detection  — يبحث عن: same action · same error ·
                             same state · no progress
    23.3  Recovery         — detect → diagnose → retry → alternate
                             method → replan

The name of the section is the law: the *silent* stall — a component
that simply stops speaking is the one failure no exception ever
reports.  So health here is time-based before it is exception-based:
every monitored component owes the :class:`~nexus.health.heartbeat.
HeartbeatMonitor` a beat, and silence past the stale window is itself
a finding.  §23.2 names the four loop shapes a stuck worker traces;
§23.3 walks the ladder one rung at a time — every rung observable in
the returned :class:`LadderOutcome`, and every world-mutating rung
(retry · alternate method) announced to the §22 trigger events before
it fires.

عقود نظام النبضة والصحة — سبع مكونات مراقَبة، أربع بصمات تعطُّل،
وسلّم استرداد خماسي الدرجات. لا توقف صامت.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..verification.contracts import utc_now_iso

HEALTH_SCHEMA_VERSION = 1

# ----------------------------------------------------------------- errors


class HealthError(Exception):
    """Health-system misuse or operation failure."""


class UnknownComponentError(HealthError):
    """A beat or check addressed a component that was never registered."""


# ------------------------------------------------------- §23 vocabulary


class MonitoredComponent(StrEnum):
    """§23.1 — the seven watch targets, verbatim and in order."""

    CORE = "core"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    BROWSER = "browser"
    COMPUTER = "computer"
    TASK = "task"


class ComponentStatus(StrEnum):
    """The life sign of one component — derived, never invented.

    ``ALIVE`` beats inside the fresh window · ``DEGRADED`` is late but
    not yet silent (or said so itself) · ``STALLED`` was named by a
    confirmed §23.2 finding and stays so until the next beat ·
    ``SILENT`` — التوقف الصامت — no beat within the stale window.
    """

    ALIVE = "alive"
    DEGRADED = "degraded"
    STALLED = "stalled"
    SILENT = "silent"


class StallSignal(StrEnum):
    """§23.2 — the four loop shapes, verbatim and in order."""

    SAME_ACTION = "same_action"
    SAME_ERROR = "same_error"
    SAME_STATE = "same_state"
    NO_PROGRESS = "no_progress"


class HealthVerdict(StrEnum):
    """The snapshot verdict — the worst life sign wins."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALLED = "stalled"


class RecoveryResolution(StrEnum):
    """What the §23.3 ladder concluded."""

    NOT_CONFIRMED = "not_confirmed"
    RESOLVED = "resolved"
    REPLAN_NEEDED = "replan_needed"


#: §23.1 — the seven components, verbatim tuple form (the enum is the
#: typed twin; this tuple is the vocabulary the tests pin).
MONITORED_COMPONENTS: tuple[str, ...] = (
    "core",
    "agent",
    "model",
    "tool",
    "browser",
    "computer",
    "task",
)

#: §23.2 — the four stall signals, verbatim tuple form.
STALL_SIGNALS: tuple[str, ...] = (
    "same_action",
    "same_error",
    "same_state",
    "no_progress",
)

#: §23.3 — the recovery ladder, verbatim and in order.  ``handle``
#: walks it rung by rung and the outcome names where it stopped.
RECOVERY_LADDER: tuple[str, ...] = (
    "detect",
    "diagnose",
    "retry",
    "alternate_method",
    "replan",
)


# ---------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class Heartbeat:
    """One component's life sign as of one check."""

    component: MonitoredComponent
    status: ComponentStatus
    seq: int
    age_seconds: float | None  # None — it has never beaten
    detail: str = ""
    last_beat_utc: str | None = None
    checked_at_utc: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "status": self.status.value,
            "seq": self.seq,
            "age_seconds": self.age_seconds,
            "detail": self.detail,
            "last_beat_utc": self.last_beat_utc,
            "checked_at_utc": self.checked_at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Heartbeat:
        return cls(
            component=MonitoredComponent(str(data["component"])),
            status=ComponentStatus(str(data["status"])),
            seq=int(data["seq"]),
            age_seconds=(
                None if data.get("age_seconds") is None else float(data["age_seconds"])
            ),
            detail=str(data.get("detail", "")),
            last_beat_utc=data.get("last_beat_utc"),
            checked_at_utc=str(data.get("checked_at_utc", "")),
        )


@dataclass(frozen=True)
class HealthReport:
    """The §23.1 snapshot — one line per watched component."""

    verdict: HealthVerdict
    components: tuple[Heartbeat, ...] = ()
    checked_at_utc: str = field(default_factory=utc_now_iso)

    def component(self, which: MonitoredComponent | str) -> Heartbeat | None:
        name = MonitoredComponent(which)
        for hb in self.components:
            if hb.component is name:
                return hb
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "components": [hb.as_dict() for hb in self.components],
            "checked_at_utc": self.checked_at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HealthReport:
        return cls(
            verdict=HealthVerdict(str(data["verdict"])),
            components=tuple(
                Heartbeat.from_dict(hb) for hb in data.get("components", [])
            ),
            checked_at_utc=str(data.get("checked_at_utc", "")),
        )


@dataclass(frozen=True)
class Observation:
    """What the §23.2 detector consumes — one step of a worker's life.

    ``action`` what was just attempted · ``error`` the failure
    signature (empty when it worked) · ``state`` the observed state
    hash · ``progress`` the forward marker (task step id, cursor…).
    Empty fields are honestly skipped — nothing is judged on nothing.
    """

    action: str = ""
    error: str = ""
    state: str = ""
    progress: str = ""
    at_utc: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "error": self.error,
            "state": self.state,
            "progress": self.progress,
            "at_utc": self.at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Observation:
        return cls(
            action=str(data.get("action", "")),
            error=str(data.get("error", "")),
            state=str(data.get("state", "")),
            progress=str(data.get("progress", "")),
            at_utc=str(data.get("at_utc", "")),
        )


@dataclass(frozen=True)
class StallFinding:
    """One confirmed §23.2 loop shape — or one §23.1 silence."""

    signal: StallSignal
    repeats: int
    detail: str
    component: MonitoredComponent | None = None
    at_utc: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.value,
            "repeats": self.repeats,
            "detail": self.detail,
            "component": self.component.value if self.component else None,
            "at_utc": self.at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StallFinding:
        raw_component = data.get("component")
        return cls(
            signal=StallSignal(str(data["signal"])),
            repeats=int(data["repeats"]),
            detail=str(data.get("detail", "")),
            component=(
                MonitoredComponent(str(raw_component)) if raw_component else None
            ),
            at_utc=str(data.get("at_utc", "")),
        )


@dataclass(frozen=True)
class Diagnosis:
    """The §23.3 diagnose rung's answer — a cause, with a confidence."""

    signal: StallSignal
    cause: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.value,
            "cause": self.cause,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Diagnosis:
        return cls(
            signal=StallSignal(str(data["signal"])),
            cause=str(data["cause"]),
            confidence=float(data["confidence"]),
        )


@dataclass(frozen=True)
class LadderOutcome:
    """The §23.3 walk result — which rungs, where it stopped, why.

    ``rungs`` is the prefix of :data:`RECOVERY_LADDER` actually
    reached; ``resolution`` is the ladder's final word.
    """

    finding: StallFinding
    resolution: RecoveryResolution
    rungs: tuple[str, ...] = ()
    stopped_at: str = ""
    detail: str = ""
    diagnosis: Diagnosis | None = None

    @property
    def stages(self) -> tuple[str, ...]:
        """The walked prefix — the §23.3 ladder made observable."""
        return tuple(r for r in RECOVERY_LADDER if r in self.rungs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.as_dict(),
            "resolution": self.resolution.value,
            "rungs": list(self.rungs),
            "stopped_at": self.stopped_at,
            "detail": self.detail,
            "diagnosis": self.diagnosis.as_dict() if self.diagnosis else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LadderOutcome:
        raw_diagnosis = data.get("diagnosis")
        return cls(
            finding=StallFinding.from_dict(data["finding"]),
            resolution=RecoveryResolution(str(data["resolution"])),
            rungs=tuple(str(r) for r in data.get("rungs", [])),
            stopped_at=str(data.get("stopped_at", "")),
            detail=str(data.get("detail", "")),
            diagnosis=Diagnosis.from_dict(raw_diagnosis) if raw_diagnosis else None,
        )


@dataclass(frozen=True)
class SupervisorReport:
    """One poll of the supervisor — health, findings, ladder outcomes."""

    health: HealthReport
    findings: tuple[StallFinding, ...] = ()
    outcomes: tuple[LadderOutcome, ...] = ()
    at_utc: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "health": self.health.as_dict(),
            "findings": [f.as_dict() for f in self.findings],
            "outcomes": [o.as_dict() for o in self.outcomes],
            "at_utc": self.at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SupervisorReport:
        return cls(
            health=HealthReport.from_dict(data["health"]),
            findings=tuple(StallFinding.from_dict(f) for f in data.get("findings", [])),
            outcomes=tuple(
                LadderOutcome.from_dict(o) for o in data.get("outcomes", [])
            ),
            at_utc=str(data.get("at_utc", "")),
        )
