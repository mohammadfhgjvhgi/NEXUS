"""§22.2 — the six trigger events and the periodic interval policy."""

from __future__ import annotations

from pathlib import Path

from nexus.recovery import (
    TRIGGER_EVENTS,
    CheckpointManager,
    DiskCheckpointStore,
    TriggerEvent,
    TriggerPolicy,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _manager(tmp_path: Path, repo: Path, policy: TriggerPolicy) -> CheckpointManager:
    return CheckpointManager(
        DiskCheckpointStore(tmp_path / "checkpoints"),
        repo,
        version="0.22.0",
        phase=22,
        triggers=policy,
        expectations_provider=lambda: ((), (), ()),
    )


def test_six_events_verbatim(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo, TriggerPolicy(min_interval_seconds=0))
    for event in TriggerEvent:
        manifest = manager.on_event(event, label=f"trigger:{event.value}")
        assert manifest is not None, event
        assert manifest.trigger is event
    assert len(manager.created) == len(TriggerEvent) == 6
    assert {m.trigger.value for m in manager.created} == set(TRIGGER_EVENTS)


def test_non_periodic_always_allowed(tmp_path: Path, repo: Path) -> None:
    policy = TriggerPolicy(min_interval_seconds=3600.0)
    manager = _manager(tmp_path, repo, policy)
    for _ in range(3):
        assert manager.on_event(TriggerEvent.BEFORE_RISKY_CHANGE) is not None


def test_periodic_gated_by_interval(tmp_path: Path, repo: Path) -> None:
    clock = FakeClock()
    policy = TriggerPolicy(min_interval_seconds=300.0, clock=clock)
    manager = _manager(tmp_path, repo, policy)
    first = manager.on_event(TriggerEvent.PERIODIC)
    assert first is not None
    clock.advance(10.0)
    assert manager.on_event(TriggerEvent.PERIODIC) is None  # suppressed
    clock.advance(291.0)  # 301s total — interval elapsed
    third = manager.on_event(TriggerEvent.PERIODIC)
    assert third is not None
    assert manager.store.latest("task").checkpoint_id == third.checkpoint_id


def test_zero_interval_periodic_always_allowed(tmp_path: Path, repo: Path) -> None:
    clock = FakeClock()
    manager = _manager(
        tmp_path, repo, TriggerPolicy(min_interval_seconds=0.0, clock=clock)
    )
    clock.advance(0.001)
    assert manager.on_event(TriggerEvent.PERIODIC) is not None
    clock.advance(0.001)
    assert manager.on_event(TriggerEvent.PERIODIC) is not None


def test_event_labels_and_task_state_ride(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo, TriggerPolicy())
    manifest = manager.on_event(
        TriggerEvent.PHASE_COMPLETE,
        label="phase 17 closed",
        task_state={"task": "research", "step": 9},
    )
    assert manifest is not None
    assert manifest.label == "phase 17 closed"
    assert manifest.state["task_state"] == {"task": "research", "step": 9}
