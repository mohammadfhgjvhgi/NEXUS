"""The supervisor ties §23.1 + §23.2 + §23.3 — and the §22 law rides along."""

from __future__ import annotations

from conftest import FakeClock

from nexus.health import (
    ComponentStatus,
    HealthSupervisor,
    HeartbeatMonitor,
    MonitoredComponent,
    Observation,
    RecoveryLadder,
    RecoveryResolution,
    StallSignal,
    SupervisorReport,
)

FRESH, STALE = 10.0, 30.0
_TICK = iter(range(1_000_000))


def loop_obs() -> Observation:
    """A pinned action with varying state/progress — the same_action
    shape, isolated."""
    tick = next(_TICK)
    return Observation(action="click", state=f"state-{tick}", progress=f"prog-{tick}")


def supervisor(clock: FakeClock, **ladder_kwargs):  # noqa: ANN201
    monitor = HeartbeatMonitor(
        fresh_after_seconds=FRESH, stale_after_seconds=STALE, clock=clock
    )
    for name in monitor.watched:
        monitor.beat(name)  # the boot beat — the world starts alive
    ladder = RecoveryLadder(**ladder_kwargs)
    return HealthSupervisor(monitor, ladder, repeat_threshold=3, progress_window=4)


def test_healthy_beats_and_progress_report_healthy() -> None:
    clock = FakeClock()
    sup = supervisor(clock)
    for name in sup.monitor.watched:
        sup.monitor.beat(name)
    report = sup.poll()  # an empty observation map — pure heartbeat health
    assert report.health.verdict.value == "healthy"
    assert report.findings == () and report.outcomes == ()


def test_a_loop_becomes_a_finding_that_walks_the_ladder() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: True)
    sup.monitor.beat(MonitoredComponent.AGENT)
    assert sup.poll({MonitoredComponent.AGENT: loop_obs()}).findings == ()
    assert sup.poll({MonitoredComponent.AGENT: loop_obs()}).findings == ()
    report = sup.poll({MonitoredComponent.AGENT: loop_obs()})
    (finding,) = report.findings
    assert finding.signal is StallSignal.SAME_ACTION
    assert finding.component is MonitoredComponent.AGENT
    (outcome,) = report.outcomes
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert outcome.rungs == ("detect", "diagnose", "retry")


def test_a_confirmed_finding_marks_the_component_stalled() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: False, alternate=lambda f: False)
    sup.monitor.beat(MonitoredComponent.TOOL)
    for _ in range(3):
        sup.poll({MonitoredComponent.TOOL: loop_obs()})
    # the mark lands after the snapshot — the NEXT poll reports it
    report = sup.poll({MonitoredComponent.TOOL: loop_obs()})
    assert report.findings == ()  # the same evidence never re-fires
    hb = report.health.component(MonitoredComponent.TOOL)
    assert hb is not None and hb.status is ComponentStatus.STALLED
    sup.monitor.beat(MonitoredComponent.TOOL)  # the component proves recovery
    assert (
        sup.monitor.check(MonitoredComponent.TOOL).status is ComponentStatus.ALIVE
    )


def test_resolved_outcome_resets_the_private_detector() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: True)
    sup.monitor.beat(MonitoredComponent.TASK)
    for _ in range(3):
        sup.poll({MonitoredComponent.TASK: loop_obs()})
    assert sup.detector(MonitoredComponent.TASK).depth == 0


def test_silence_becomes_a_no_progress_finding() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: True)
    sup.monitor.beat(MonitoredComponent.BROWSER)
    clock.advance(STALE + 1)
    report = sup.poll()
    silent = [f for f in report.findings if f.component is MonitoredComponent.BROWSER]
    assert silent and silent[0].signal is StallSignal.NO_PROGRESS
    assert "التوقف الصامت" in silent[0].detail
    (outcome,) = [o for o in report.outcomes if o.finding.component is MonitoredComponent.BROWSER]
    assert outcome.resolution is RecoveryResolution.RESOLVED


def test_silence_is_reported_once_until_it_speaks_again() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: True)
    sup.monitor.beat(MonitoredComponent.MODEL)
    clock.advance(STALE + 1)
    first = sup.poll()
    second = sup.poll()  # still silent — no duplicate alarm
    assert len([f for f in first.findings if f.component is MonitoredComponent.MODEL]) == 1
    assert not [f for f in second.findings if f.component is MonitoredComponent.MODEL]
    sup.monitor.beat(MonitoredComponent.MODEL)
    clock.advance(STALE + 1)
    third = sup.poll()  # it spoke, then went silent again — report once more
    assert [f for f in third.findings if f.component is MonitoredComponent.MODEL]


def test_the_22_law_a_real_checkpoint_captures_before_each_rung() -> None:
    """before_rung → §22.2 BEFORE_RISKY_CHANGE — the cross-phase proof."""
    import tempfile
    from pathlib import Path

    from nexus.recovery import (
        CheckpointManager,
        DiskCheckpointStore,
        TriggerEvent,
        TriggerPolicy,
    )

    base = Path(tempfile.mkdtemp(prefix="p23-sup-22-"))
    repo = base / "repo"
    repo.mkdir()
    manager = CheckpointManager(
        DiskCheckpointStore(base / "ck"),
        repo,
        version="0.23.0",
        phase=23,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )

    def announce(rung: str, finding) -> None:  # noqa: ANN001
        made = manager.on_event(
            TriggerEvent.BEFORE_RISKY_CHANGE, label=f"§23.3 {rung}"
        )
        assert made is not None and made.trigger is TriggerEvent.BEFORE_RISKY_CHANGE

    clock = FakeClock()
    sup = supervisor(
        clock,
        retry=lambda f: False,
        alternate=lambda f: True,
        before_rung=announce,
    )
    sup.monitor.beat(MonitoredComponent.TOOL)
    for _ in range(3):
        sup.poll({MonitoredComponent.TOOL: loop_obs()})
    scopes = [m.trigger.value for m in manager.store.list()]
    assert scopes.count("before_risky_change") == 2  # retry + alternate_method


def test_supervisor_report_serializes_fully() -> None:
    clock = FakeClock()
    sup = supervisor(clock, retry=lambda f: True)
    sup.monitor.beat(MonitoredComponent.AGENT)
    for _ in range(3):
        report = sup.poll({MonitoredComponent.AGENT: loop_obs()})
    assert SupervisorReport.from_dict(report.as_dict()) == report
