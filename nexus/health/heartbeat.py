"""Heartbeat — §23.1: the seven watch targets owe the monitor a beat.

    يراقب: Core · Agent · Model · Tool · Browser · Computer · Task

The design law: health is *time-based before it is exception-based*.
Nothing here waits for an exception — an exception at least speaks.
A component that stops beating is the silent stall the section exists
to prevent, and silence is derived from the clock, not from memory of
what the component "was doing".

Status derivation per check (worst signal wins):

    age > stale window                     → SILENT   (التوقف الصامت)
    acknowledged stall, no clearing beat   → STALLED
    age > fresh window                     → DEGRADED (late, not dead)
    the component itself reported degraded → DEGRADED
    otherwise                              → ALIVE

A fresh beat clears an acknowledged stall — recovery must be
*proven by the component*, never granted by the monitor.

Stdlib only.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from .contracts import (
    MONITORED_COMPONENTS,
    ComponentStatus,
    HealthError,
    HealthReport,
    HealthVerdict,
    Heartbeat,
    MonitoredComponent,
    UnknownComponentError,
    utc_now_iso,
)

#: worst-first — the snapshot verdict takes the worst life sign present.
_STATUS_SEVERITY: tuple[ComponentStatus, ...] = (
    ComponentStatus.SILENT,
    ComponentStatus.STALLED,
    ComponentStatus.DEGRADED,
    ComponentStatus.ALIVE,
)


def _as_component(value: MonitoredComponent | str) -> MonitoredComponent:
    """Typed conversion — an unknown name is §23.1 refused, never a bare
    ``ValueError``."""
    try:
        return MonitoredComponent(value)
    except ValueError as exc:
        raise UnknownComponentError(
            f"§23.1 {value!r} is not one of the seven monitored components"
        ) from exc


class HeartbeatMonitor:
    """§23.1 — one monitor, seven components, one honest clock."""

    def __init__(
        self,
        components: tuple[str, ...] | list[str] | None = None,
        *,
        fresh_after_seconds: float = 30.0,
        stale_after_seconds: float = 90.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._fresh = float(fresh_after_seconds)
        self._stale = float(stale_after_seconds)
        if self._stale < self._fresh:
            raise HealthError(
                "stale_after_seconds must be ≥ fresh_after_seconds — "
                "a component cannot go silent before it is late"
            )
        self._clock: Callable[[], float] = clock or _monotonic
        self._lock = threading.RLock()
        # insertion-ordered — the §23.1 verbatim order survives snapshots
        self._known: dict[MonitoredComponent, None] = {}
        # component → (monotonic ts, seq, reported status, detail)
        self._beats: dict[MonitoredComponent, tuple[float, int, ComponentStatus, str]] = {}
        self._wall: dict[MonitoredComponent, str] = {}
        self._stalled: set[MonitoredComponent] = set()
        for name in components or MONITORED_COMPONENTS:
            self.register(name)

    # ------------------------------------------------------------ public

    def register(self, component: MonitoredComponent | str) -> None:
        """Add one watch target — idempotent, typed, honest."""
        name = _as_component(component)
        with self._lock:
            self._known[name] = None

    def beat(
        self,
        component: MonitoredComponent | str,
        *,
        status: ComponentStatus | str = ComponentStatus.ALIVE,
        seq: int | None = None,
        detail: str = "",
    ) -> int:
        """The component speaks — a fresh beat clears an old stall.

        Returns the recorded sequence number.  An unregistered
        component is refused — the monitor watches what it watches,
        never invents watchers.
        """
        name = _as_component(component)
        with self._lock:
            if name not in self._known:
                raise UnknownComponentError(
                    f"§23.1 {name.value!r} is not registered with this monitor"
                )
            now = self._clock()
            last = self._beats.get(name)
            nseq = int(seq) if seq is not None else ((last[1] + 1) if last else 1)
            self._beats[name] = (now, nseq, ComponentStatus(status), detail)
            self._wall[name] = utc_now_iso()
            self._stalled.discard(name)
            return nseq

    def mark_stalled(self, component: MonitoredComponent | str, detail: str = "") -> None:
        """Acknowledge a confirmed §23.2 finding — STALLED until the
        component proves otherwise with a fresh beat."""
        name = _as_component(component)
        with self._lock:
            if name not in self._known:
                raise UnknownComponentError(
                    f"§23.1 {name.value!r} is not registered with this monitor"
                )
            self._stalled.add(name)

    def check(self, component: MonitoredComponent | str) -> Heartbeat:
        """One component's life sign, derived from the clock right now."""
        name = _as_component(component)
        with self._lock:
            if name not in self._known:
                raise UnknownComponentError(
                    f"§23.1 {name.value!r} is not registered with this monitor"
                )
            beat = self._beats.get(name)
            if beat is None:
                return Heartbeat(
                    component=name,
                    status=ComponentStatus.SILENT,
                    seq=0,
                    age_seconds=None,
                    detail="never beat — the silent stall from birth",
                )
            ts, seq, reported, detail = beat
            age = self._clock() - ts
            if age > self._stale:
                derived = ComponentStatus.SILENT
            elif name in self._stalled:
                derived = ComponentStatus.STALLED
            elif age > self._fresh:
                derived = ComponentStatus.DEGRADED
            elif reported is ComponentStatus.DEGRADED:
                derived = ComponentStatus.DEGRADED
            else:
                derived = ComponentStatus.ALIVE
            return Heartbeat(
                component=name,
                status=derived,
                seq=seq,
                age_seconds=round(age, 6),
                detail=detail,
                last_beat_utc=self._wall.get(name),
            )

    def snapshot(self) -> HealthReport:
        """The §23.1 report — every watched component, worst sign wins."""
        with self._lock:
            lines = tuple(self.check(name) for name in self._known)
        statuses = [hb.status for hb in lines]
        for candidate in _STATUS_SEVERITY:
            if candidate in statuses:
                verdict = {
                    ComponentStatus.SILENT: HealthVerdict.STALLED,
                    ComponentStatus.STALLED: HealthVerdict.STALLED,
                    ComponentStatus.DEGRADED: HealthVerdict.DEGRADED,
                    ComponentStatus.ALIVE: HealthVerdict.HEALTHY,
                }[candidate]
                break
        else:  # pragma: no cover — the empty monitor is not a world
            verdict = HealthVerdict.HEALTHY
        return HealthReport(verdict=verdict, components=lines)

    @property
    def watched(self) -> tuple[MonitoredComponent, ...]:
        with self._lock:
            return tuple(self._known)


def _monotonic() -> float:
    import time

    return time.monotonic()
