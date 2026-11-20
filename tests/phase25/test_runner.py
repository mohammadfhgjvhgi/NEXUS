"""Phase 25 runner — §25.2 background work · §25.4 heartbeat ·
§25.5 checkpoints · §25.7 the honest deadline."""

from __future__ import annotations

import threading
import time

import pytest

from nexus.horizon import (
    HorizonError,
    HorizonRunner,
    StepOutcome,
    deadline_window,
)


def test_background_worker_completes_and_returns_immediately(
    runner: HorizonRunner, store
) -> None:
    goal = store.create_goal("work in the background", "until_completion")

    def step(seq, record):
        return StepOutcome(done=seq >= 2, note=f"step {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    # the worker owns the goal in the background; observation is instant
    assert handle.is_alive() or handle.state() == "completed"
    final = handle.wait(timeout=10)
    assert final == "completed"
    assert handle.record().progress_seq == 3  # steps 0,1,2 → seq 3


def test_main_thread_lives_while_worker_works(runner: HorizonRunner, store) -> None:
    """§25.2 — real background: the caller is not blocked."""
    goal = store.create_goal("parallel lives", "until_completion")
    release = threading.Event()

    def step(seq, record):
        if seq == 0:
            release.wait(timeout=10)  # the worker parks; the caller doesn't
        return StepOutcome(done=True, note="done after parking")

    handle = runner.start(goal.goal_id, step)
    time.sleep(0.05)  # the worker is parked inside step 0 right now
    assert handle.state() == "running"  # the caller kept running
    assert handle.is_alive()
    release.set()
    assert handle.wait(timeout=10) == "completed"


def test_state_is_true_between_steps_from_disk(runner: HorizonRunner, store) -> None:
    """§25.3 — a mid-run reader sees the durable truth."""
    goal = store.create_goal("watched mid-run", "until_completion")
    gate = threading.Event()

    def step(seq, record):
        gate.wait(timeout=10)  # hold the run open mid-step
        return StepOutcome(done=True, note="final step")

    handle = runner.start(goal.goal_id, step)
    time.sleep(0.1)
    assert handle.state() == "running"  # read from disk mid-run
    assert handle.record().progress_seq == 0
    gate.set()
    assert handle.wait(timeout=10) == "completed"


def test_journal_and_seq_recorded(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("journalled run", "until_completion")

    def step(seq, record):
        return StepOutcome(done=seq >= 3, note=f"did work #{seq + 1}")

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=10)
    notes = handle.progress()
    assert [n.message for n in notes][:4] == [
        "did work #1", "did work #2", "did work #3", "did work #4",
    ]
    seqs = [n.seq for n in notes]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # monotonic


def test_bounded_deadline_hits_honestly(runner: HorizonRunner, store, wall) -> None:
    """§25.7 — the wall stops the run with deadline_hit, never a fake
    completion."""
    goal = store.create_goal("bounded", "30_minutes")
    start_wall = wall.now

    def step(seq, record):
        wall.advance(400.0)  # each step burns 400s of the 1800s window
        return StepOutcome(done=False, note=f"still working {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    final = handle.wait(timeout=10)
    assert final == "deadline_hit"
    record = handle.record()
    assert record.state == "deadline_hit"
    assert record.deadline_at == start_wall + 1800.0  # the window, persisted
    notes = handle.progress()
    assert not any(n.message.startswith("FAILED") for n in notes)
    # the deadline was respected: 1800s / 400s → five steps fit, the
    # sixth start attempt is the wall
    assert record.progress_seq == 5


def test_deadline_window_math(wall) -> None:
    assert deadline_window("30_minutes", wall_clock=wall) == wall() + 1800.0
    assert deadline_window("2_hours", wall_clock=wall) == wall() + 7200.0
    assert deadline_window("8_hours", wall_clock=wall) == wall() + 28800.0
    assert deadline_window("until_completion", wall_clock=wall) is None


def test_until_completion_has_no_wall(runner: HorizonRunner, store, wall) -> None:
    goal = store.create_goal("no wall at all", "until_completion")

    def step(seq, record):
        wall.advance(100_000.0)  # far beyond any bounded window
        return StepOutcome(done=seq >= 1, note="unbounded but finishing")

    handle = runner.start(goal.goal_id, step)
    assert handle.wait(timeout=10) == "completed"  # no deadline, work decides
    assert handle.record().deadline_at is None


def test_step_exception_fails_honestly(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("doomed step", "until_completion")

    def step(seq, record):
        if seq == 2:
            raise RuntimeError("the device vanished")
        return StepOutcome(done=False, note=f"ok {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    assert handle.wait(timeout=10) == "failed"
    record = handle.record()
    assert record.progress_seq == 3  # two honest steps + the FAILED note
    notes = handle.progress()
    honest = [n for n in notes if not n.message.startswith("FAILED")]
    assert len(honest) == 2
    assert notes[-1].message.startswith("FAILED: RuntimeError")
    assert "the device vanished" in notes[-1].message


def test_step_must_return_step_outcome(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("shape police", "until_completion")

    def step(seq, record):
        return "done"  # a lie of a shape

    handle = runner.start(goal.goal_id, step)
    assert handle.wait(timeout=10) == "failed"
    assert "not StepOutcome" in handle.progress()[-1].message


def test_start_requires_pending(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("started once", "until_completion")

    def step(seq, record):
        return StepOutcome(done=True)

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=10)
    with pytest.raises(HorizonError):
        runner.start(goal.goal_id, step)  # completed is not pending


def test_pause_stops_the_loop(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("pausable", "until_completion")
    hits = threading.Event()

    def step(seq, record):
        hits.set()
        time.sleep(0.05)
        return StepOutcome(done=False, note="still going")

    handle = runner.start(goal.goal_id, step)
    hits.wait(timeout=10)
    assert handle.pause() == "paused"
    assert handle.wait(timeout=10) == "paused"
    seq = handle.record().progress_seq
    time.sleep(0.15)  # nothing more may run
    assert handle.record().progress_seq == seq


def test_heartbeat_rides_every_step(store, wall) -> None:
    from nexus.health import HeartbeatMonitor

    monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
    for name in monitor.watched:
        monitor.beat(name)
    runner = HorizonRunner(store, heartbeat=monitor, wall_clock=wall)
    goal = store.create_goal("observed", "until_completion")

    def step(seq, record):
        return StepOutcome(done=seq >= 4, note=f"beat {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=10)
    agent = monitor.check("agent")
    assert agent.seq > 1 + 4  # the boot beat + at least five step beats
    task = monitor.check("task")
    assert task.seq >= 2  # the completed milestone beat
    assert agent.status.value == "alive"


def test_checkpoints_captured_on_cadence(store, wall, tmp_path) -> None:
    from nexus.recovery import (
        CheckpointManager,
        DiskCheckpointStore,
        TriggerPolicy,
    )

    ck_store = DiskCheckpointStore(tmp_path / "ck")
    manager = CheckpointManager(
        ck_store, tmp_path / "repo",
        version="0.25.0", phase=25,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )
    runner = HorizonRunner(
        store, checkpoints=manager, checkpoint_every=2, wall_clock=wall
    )
    goal = store.create_goal("checkpointed run", "until_completion")

    def step(seq, record):
        return StepOutcome(done=seq >= 6, note=f"step {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=10)
    assert handle.record().progress_seq == 7
    assert handle.record().last_checkpoint_id is not None
    listed = {str(m.checkpoint_id) for m in ck_store.list()}
    triggers = [m.trigger.value for m in ck_store.list()]
    assert triggers.count("periodic") == 3  # after steps 2, 4, 6
    assert handle.record().last_checkpoint_id in listed  # the newest is real


def test_superseded_worker_retires_itself(store, wall, runner: HorizonRunner) -> None:
    """The generation lease: a resumed goal is not fought over."""
    goal = store.create_goal("one owner at a time", "until_completion")
    park = threading.Event()

    def slow(seq, record):
        park.wait(timeout=15)  # worker #1 parks mid-step
        return StepOutcome(done=False, note="ghost step")

    handle1 = runner.start(goal.goal_id, slow)
    time.sleep(0.1)  # worker #1 is parked inside step 0

    # the successor runner re-opens the run (the resume path's lease)
    store.begin_run(goal.goal_id, deadline_at=None)  # generation bump

    def fast(seq, record):
        return StepOutcome(done=True, note="the new owner finished")

    handle2 = runner.relaunch(goal.goal_id, fast)
    assert handle2.wait(timeout=10) == "completed"
    park.set()  # let the ghost wake — it must retire, not write
    handle1.wait(timeout=15)
    # the ghost never clobbered the record: still completed, seq intact
    final = store.get(goal.goal_id)
    assert final.state == "completed"
    assert final.generation == 3  # start(1) + begin_run(2) + relaunch(3)
    assert not any("ghost step" in n.message for n in store.progress(goal.goal_id))
