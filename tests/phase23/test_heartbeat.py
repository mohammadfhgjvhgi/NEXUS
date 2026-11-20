"""§23.1 Heartbeat — the seven watch targets owe the monitor a beat."""

from __future__ import annotations

import pytest
from conftest import FakeClock

from nexus.health import (
    ComponentStatus,
    HealthError,
    HealthVerdict,
    HeartbeatMonitor,
    MonitoredComponent,
    UnknownComponentError,
)

FRESH, STALE = 30.0, 90.0


def monitor(clock: FakeClock, **kwargs: float) -> HeartbeatMonitor:
    return HeartbeatMonitor(
        fresh_after_seconds=kwargs.get("fresh", FRESH),
        stale_after_seconds=kwargs.get("stale", STALE),
        clock=clock,
    )


def test_all_seven_components_registered() -> None:
    m = monitor(FakeClock())
    assert tuple(c.value for c in m.watched) == (
        "core", "agent", "model", "tool", "browser", "computer", "task",
    )


def test_fresh_beat_is_alive() -> None:
    clock = FakeClock()
    m = monitor(clock)
    m.beat("core", detail="boot done")
    hb = m.check("core")
    assert hb.status is ComponentStatus.ALIVE
    assert hb.seq == 1 and hb.age_seconds == 0.0
    assert hb.last_beat_utc is not None


def test_late_beat_degrades_before_silence() -> None:
    clock = FakeClock()
    m = monitor(clock)
    m.beat("agent")
    clock.advance(FRESH + 1)
    assert m.check("agent").status is ComponentStatus.DEGRADED
    clock.advance(STALE - FRESH)
    assert m.check("agent").status is ComponentStatus.SILENT


def test_silence_overrides_everything() -> None:
    clock = FakeClock()
    m = monitor(clock)
    m.beat("tool")
    m.mark_stalled("tool")
    clock.advance(STALE + 1)
    assert m.check("tool").status is ComponentStatus.SILENT


def test_never_beat_is_silent_from_birth() -> None:
    m = monitor(FakeClock())
    hb = m.check("model")
    assert hb.status is ComponentStatus.SILENT
    assert hb.age_seconds is None and hb.seq == 0


def test_reported_degradation_persists_while_fresh() -> None:
    clock = FakeClock()
    m = monitor(clock)
    m.beat("browser", status=ComponentStatus.DEGRADED, detail="slow navigation")
    assert m.check("browser").status is ComponentStatus.DEGRADED
    m.beat("browser")  # a clean beat clears it
    assert m.check("browser").status is ComponentStatus.ALIVE


def test_acknowledged_stall_holds_until_a_beat_clears_it() -> None:
    clock = FakeClock()
    m = monitor(clock)
    m.beat("task")
    m.mark_stalled("task", detail="same_action ×3")
    assert m.check("task").status is ComponentStatus.STALLED
    m.beat("task")  # the component proves recovery by beating
    assert m.check("task").status is ComponentStatus.ALIVE


def test_sequence_advances_and_accepts_explicit() -> None:
    clock = FakeClock()
    m = monitor(clock)
    assert m.beat("computer") == 1
    assert m.beat("computer") == 2
    assert m.beat("computer", seq=10) == 10
    assert m.beat("computer") == 11


def test_unknown_component_refused() -> None:
    m = monitor(FakeClock())
    with pytest.raises(UnknownComponentError):
        m.beat("workflow-engine")
    with pytest.raises(UnknownComponentError):
        m.check("workflow-engine")
    with pytest.raises(UnknownComponentError):
        m.mark_stalled("workflow-engine")


def test_snapshot_verdict_takes_the_worst_sign() -> None:
    clock = FakeClock()
    m = monitor(clock)
    assert m.snapshot().verdict is HealthVerdict.STALLED  # seven silent births
    for name in m.watched:
        m.beat(name)
    assert m.snapshot().verdict is HealthVerdict.HEALTHY
    clock.advance(FRESH + 1)  # everyone is late now, nobody silent yet
    assert m.snapshot().verdict is HealthVerdict.DEGRADED
    m.beat(MonitoredComponent.TOOL)  # fresh again…
    m.mark_stalled(MonitoredComponent.TOOL)  # …then named by a finding
    assert m.snapshot().verdict is HealthVerdict.STALLED


def test_config_rejects_stale_before_fresh() -> None:
    with pytest.raises(HealthError):
        HeartbeatMonitor(fresh_after_seconds=10.0, stale_after_seconds=5.0)
