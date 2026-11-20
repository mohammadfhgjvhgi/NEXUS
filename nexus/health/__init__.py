"""NEXUS Health System (New Plan §23 — PHASE 23).

*منع التوقف الصامت.*
(Prevent the silent stall.)

The three sections::

    23.1  Heartbeat        — يراقب: Core · Agent · Model · Tool ·
                             Browser · Computer · Task
    23.2  Stall Detection  — يبحث عن: same action · same error ·
                             same state · no progress
    23.3  Recovery         — detect → diagnose → retry → alternate
                             method → replan

The §23.1 law is structural: health is time-based before it is
exception-based — :class:`HeartbeatMonitor` derives silence from the
clock, and the :class:`HealthSupervisor` turns both silence and the
four §23.2 loop shapes into findings that walk the §23.3 ladder one
observable rung at a time.  Every world-mutating rung (retry ·
alternate method) is announced through the §22.2 BEFORE_RISKY_CHANGE
trigger first — recovery never mutates the world without a
checkpoint.

Stdlib only.
"""

from __future__ import annotations

from .contracts import (
    HEALTH_SCHEMA_VERSION,
    MONITORED_COMPONENTS,
    RECOVERY_LADDER,
    STALL_SIGNALS,
    ComponentStatus,
    Diagnosis,
    HealthError,
    HealthReport,
    HealthVerdict,
    Heartbeat,
    LadderOutcome,
    MonitoredComponent,
    Observation,
    RecoveryResolution,
    StallFinding,
    StallSignal,
    SupervisorReport,
    UnknownComponentError,
)
from .engine import (
    DEFAULT_CAUSES,
    HealthSupervisor,
    RecoveryLadder,
    stalled_components,
    worst_verdict,
)
from .heartbeat import HeartbeatMonitor
from .stall import StallDetector

__all__ = [
    "DEFAULT_CAUSES",
    "HEALTH_SCHEMA_VERSION",
    "MONITORED_COMPONENTS",
    "RECOVERY_LADDER",
    "STALL_SIGNALS",
    "ComponentStatus",
    "Diagnosis",
    "HealthError",
    "HealthReport",
    "HealthSupervisor",
    "HealthVerdict",
    "Heartbeat",
    "HeartbeatMonitor",
    "LadderOutcome",
    "MonitoredComponent",
    "Observation",
    "RecoveryLadder",
    "RecoveryResolution",
    "StallDetector",
    "StallFinding",
    "StallSignal",
    "SupervisorReport",
    "UnknownComponentError",
    "stalled_components",
    "worst_verdict",
]
