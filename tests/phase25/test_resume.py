"""Phase 25 resume — §25.6 continue from disk, never blindly (§22.4)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from nexus.horizon import (
    BlindResumeError,
    HorizonRunner,
    ResumeInspector,
    StepOutcome,
    resume,
)


def step_done(seq, record):
    return StepOutcome(done=True, note=f"resumed and finished at seq {seq}")


def test_resume_continues_from_persisted_progress(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("interrupted work", "until_completion")
    park = threading.Event()

    def first_run(seq, record):
        if seq == 2:
            park.wait(timeout=10)  # hold mid-step-2: steps 0 and 1 are durable
        return StepOutcome(done=False, note=f"first life step {seq + 1}")

    handle = runner.start(goal.goal_id, first_run)
    deadline = time.time() + 5
    while handle.record().progress_seq < 2 and time.time() < deadline:
        time.sleep(0.02)
    seq_before = handle.record().progress_seq
    assert seq_before == 2  # two steps survived on disk, worker parked
    handle.pause()          # paused while the worker sits inside step 2
    park.set()              # the worker finishes the step, then obeys the disk
    assert handle.wait(timeout=10) == "paused"

    # the successor process: fresh runner over the same store (reboot)
    runner2 = HorizonRunner(store, wall_clock=runner._wall)
    handle2 = resume(runner2, goal.goal_id, step_done)
    assert handle2.wait(timeout=10) == "completed"
    notes = handle2.progress()
    assert [n.message for n in notes] == [
        "first life step 1",
        "first life step 2",
        "first life step 3",
        "resumed and finished at seq 3",
    ]
    assert handle2.record().progress_seq == 4


def test_resume_after_failure(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("failed then fixed", "until_completion")

    def first_run(seq, record):
        raise RuntimeError("transient outage")

    handle = runner.start(goal.goal_id, first_run)
    assert handle.wait(timeout=10) == "failed"
    handle2 = resume(HorizonRunner(store, wall_clock=runner._wall), goal.goal_id, step_done)
    assert handle2.wait(timeout=10) == "completed"


def test_resume_after_deadline_rearms_fresh_window(store, wall) -> None:
    runner = HorizonRunner(store, wall_clock=wall)
    goal = store.create_goal("wall then again", "30_minutes")
    start_wall = wall.now

    def burn(seq, record):
        wall.advance(2000.0)
        return StepOutcome(done=False)

    handle = runner.start(goal.goal_id, burn)
    assert handle.wait(timeout=10) == "deadline_hit"

    wall.advance(5.0)
    runner2 = HorizonRunner(store, wall_clock=wall)
    handle2 = resume(runner2, goal.goal_id, step_done)
    record = handle2.record()
    assert record.deadline_at == start_wall + 2000.0 + 5.0 + 1800.0
    assert handle2.wait(timeout=10) == "completed"


def test_completed_goal_is_terminal(store) -> None:
    runner = HorizonRunner(store)
    goal = store.create_goal("already done", "until_completion")
    store.transition(goal.goal_id, "running")
    store.transition(goal.goal_id, "completed")
    with pytest.raises(BlindResumeError) as excinfo:
        resume(runner, goal.goal_id, step_done)
    assert "not resumable" in str(excinfo.value)


def test_unknown_goal_refused(runner: HorizonRunner, store) -> None:
    with pytest.raises(BlindResumeError) as excinfo:
        resume(runner, "goal_missing", step_done)
    assert "no goal persisted" in str(excinfo.value)


def test_corrupt_state_refuses_the_resume(store, tmp_path) -> None:
    runner = HorizonRunner(store)
    goal = store.create_goal("corrupted", "2_hours")
    store.transition(goal.goal_id, "running")
    store.goal_path(goal.goal_id).write_text("not json at all", encoding="utf-8")
    with pytest.raises(BlindResumeError) as excinfo:
        resume(runner, goal.goal_id, step_done)
    assert "unreadable" in str(excinfo.value)


def test_corrupt_deadline_vocabulary_refuses(store) -> None:
    runner = HorizonRunner(store)
    goal = store.create_goal("bad deadline on disk", "2_hours")
    store.transition(goal.goal_id, "running")
    # forge a corrupt deadline straight onto the disk (the honest way to
    # simulate drift: the file is the truth, so tamper with the file)
    path = store.goal_path(goal.goal_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["deadline"] = "whenever"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BlindResumeError) as excinfo:
        resume(runner, goal.goal_id, step_done)
    assert "whenever" in str(excinfo.value)


def test_missing_checkpoint_refuses_the_resume(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("drifted checkpoint", "2_hours")
    store.transition(goal.goal_id, "running")
    store.set_checkpoint(goal.goal_id, "ckpt_vanished")
    verdict = ResumeInspector(store, checkpoints=_FakeCheckpointStore()).inspect(
        goal.goal_id
    )
    assert not verdict.ok
    assert any("ckpt_vanished" in r for r in verdict.refusals)
    assert any("drifted" in r for r in verdict.refusals)
    with pytest.raises(BlindResumeError):
        resume(runner, goal.goal_id, step_done, checkpoints=_FakeCheckpointStore())


def test_present_checkpoint_passes_the_inspection(runner: HorizonRunner, store) -> None:
    goal = store.create_goal("honest checkpoint", "2_hours")
    store.transition(goal.goal_id, "running")
    store.set_checkpoint(goal.goal_id, "ckpt_here")
    verdict = ResumeInspector(
        store, checkpoints=_FakeCheckpointStore({"ckpt_here"})
    ).inspect(goal.goal_id)
    assert verdict.ok and verdict.refusals == ()


def test_inspector_collects_all_refusals(store) -> None:
    """§25.6 — the operator sees every reason, not just the first."""
    runner = HorizonRunner(store)
    goal = store.create_goal("multi-refused", "2_hours")
    store.transition(goal.goal_id, "running")
    store.set_checkpoint(goal.goal_id, "ckpt_gone")
    path = store.goal_path(goal.goal_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["deadline"] = "forever"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BlindResumeError) as excinfo:
        resume(runner, goal.goal_id, step_done, checkpoints=_FakeCheckpointStore())
    text = str(excinfo.value)
    assert "forever" in text and "ckpt_gone" in text


def test_resume_interrupted_running_state_notes_the_takeover(
    runner: HorizonRunner, store
) -> None:
    """A goal left ``running`` by a dead process resumes — with the
    takeover on the record (§25.3 meets §25.6)."""
    goal = store.create_goal("died mid-run", "until_completion")
    store.transition(goal.goal_id, "running")
    generation_before = store.get(goal.goal_id).generation

    handle = resume(HorizonRunner(store, wall_clock=runner._wall), goal.goal_id, step_done)
    assert handle.wait(timeout=10) == "completed"
    notes = [n.message for n in handle.progress()]
    assert any("RESUMED after interrupted run" in m for m in notes)
    assert store.get(goal.goal_id).generation == generation_before + 1


def test_resume_beats_and_persists(store) -> None:
    from nexus.health import HeartbeatMonitor

    monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
    for name in monitor.watched:
        monitor.beat(name)
    runner = HorizonRunner(store, heartbeat=monitor)
    goal = store.create_goal("resumed and observed", "2_hours")
    store.transition(goal.goal_id, "running")
    store.transition(goal.goal_id, "paused")

    handle = resume(runner, goal.goal_id, step_done)
    handle.wait(timeout=10)
    assert monitor.check("task").seq >= 2  # the completed milestone beat
    assert handle.record().state == "completed"


class _FakeCheckpointStore:
    """A §22-manager stand-in exposing only what the inspector reads."""

    def __init__(self, ids=("ckpt_here",)) -> None:
        self._ids = set(ids)

    class _Store:
        def __init__(self, ids) -> None:
            self._ids = ids

        def list(self):  # noqa: ANN202
            return [type("M", (), {"checkpoint_id": i}) for i in sorted(self._ids)]

    @property
    def store(self):  # noqa: ANN202 — the §22 manager's attribute name
        return _FakeCheckpointStore._Store(self._ids)
