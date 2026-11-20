#!/usr/bin/env python3
"""PHASE 25 live horizon proof — real threads, real disks, real walls.

Eleven rungs, each printed as [PASS]/[FAIL] with its observation (the
§20 evidence law applied to §25):

  1. §25 vocabulary verbatim — four deadlines · the state ladder ·
     the honest windows (1800 · 7200 · 28800 · None).
  2. §25.1 — a goal persisted to the real disk; a fresh store (the
     reboot) finds it with its statement intact.
  3. §25.2 — a real background thread: the worker parks mid-step and
     the main thread keeps observing — the caller is not blocked.
  4. §25.3 — the state is true between steps: read from disk mid-run
     (running · seq from the file, not from memory).
  5. §25.4 — the §23 heartbeat rides every step; the monitor reads
     ALIVE while stepping and SILENT after the worker stops — derived
     from the real clock, never from an exception.
  6. §25.5 — a real §22 CheckpointManager captures PERIODIC
     checkpoints on the cadence; the store lists them from disk and
     the recorded id is really there.
  7. §25.7 — a bounded deadline hits honestly: the stepped wall
     advances past the 30-minute window and the run stops with
     deadline_hit — never a fake completion.
  8. §25.6 — crash and resume: two durable steps, the worker parked
     (the "dead" process), a successor store+runner resumes from the
     persisted seq and completes; the generation lease retires the
     ghost without letting it write.
  9. §25.6 — no blind resume: a corrupt state file is refused, a
     completed goal is refused, a recorded-but-missing checkpoint is
     refused — every reason named.
 10. Integration — the journal is the spine: seq strictly monotonic
     with no gaps across BOTH lives of the goal, and resuming a
     deadline-hit goal re-arms a fresh window (a deadline bounds one
     run, «اشتغل لحد ما تخلص» bounds the goal).
 11. Identity — NEXUS_PHASE ≥ 25 and nexus-core ≥ 0.25.0.

Run (CI/sandbox):  python tests/phase25/live_horizon_ci.py
Run (device, via pytest): tests/phase25/test_device_proof.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus.health import ComponentStatus, HeartbeatMonitor  # noqa: E402
from nexus.horizon import (  # noqa: E402
    DEADLINE_SECONDS,
    DEADLINES,
    GOAL_STATES,
    BlindResumeError,
    GoalStore,
    HorizonRunner,
    StepOutcome,
    resume,
)
from nexus.recovery import (  # noqa: E402
    CheckpointManager,
    DiskCheckpointStore,
    TriggerPolicy,
)

RESULTS: list[tuple[str, str, str]] = []


def rung(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        note = fn()
        RESULTS.append(("PASS", label, note or ""))
        print(f"[PASS] {label}" + (f" — {note}" if note else ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(("FAIL", label, f"{type(exc).__name__}: {exc}"))
        print(f"[FAIL] {label} — {type(exc).__name__}: {exc}")


class SteppedWall:
    """A wall clock the steps drive — epoch math is real, the pace is
    the test's (the §25.7 window arithmetic must be honest, the wait
    must not be)."""

    def __init__(self, start: float) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


def fresh_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="p25-live-"))


# ------------------------------------------------------------------- rungs


def rung_1_vocabulary() -> str:
    assert DEADLINES == (
        "30_minutes", "2_hours", "8_hours", "until_completion",
    )
    assert DEADLINE_SECONDS == {
        "30_minutes": 1800.0,
        "2_hours": 7200.0,
        "8_hours": 28800.0,
        "until_completion": None,
    }
    assert GOAL_STATES == (
        "pending", "running", "paused", "completed", "failed", "deadline_hit",
    )
    return "deadlines 4 · states 6 · windows honest — verbatim"


def rung_2_goal_persistence_reboot() -> str:
    base = fresh_dir()
    store = GoalStore(base / "goals")
    goal = store.create_goal("خذ المهمة واشتغل لحد ما تخلص", "8_hours")
    on_disk = json.loads(store.goal_path(goal.goal_id).read_text(encoding="utf-8"))
    assert on_disk["state"] == "pending"
    # the reboot: a fresh store over the same directory
    store2 = GoalStore(base / "goals")
    found = store2.get(goal.goal_id)
    assert found.statement == "خذ المهمة واشتغل لحد ما تخلص"
    assert found.deadline == "8_hours" and found.created_at == goal.created_at
    return f"goal {goal.goal_id[:12]}… survived the reboot from {base.name}"


def rung_3_background_worker_not_blocking() -> str:
    store = GoalStore(fresh_dir() / "goals")
    goal = store.create_goal("work while the caller lives", "until_completion")
    park = threading.Event()
    runner = HorizonRunner(store)

    def step(seq, record):
        if seq == 0:
            park.wait(timeout=15)  # the worker parks; the caller does not
        return StepOutcome(done=True, note="done after parking")

    handle = runner.start(goal.goal_id, step)
    time.sleep(0.1)  # the worker is parked inside step 0 right now
    assert handle.is_alive()
    assert handle.state() == "running"  # the caller kept living its life
    park.set()
    assert handle.wait(timeout=15) == "completed"
    return "worker parked mid-step · caller observed and moved on"


def rung_4_state_true_between_steps() -> str:
    store = GoalStore(fresh_dir() / "goals")
    goal = store.create_goal("durable between steps", "until_completion")
    gate = threading.Event()
    runner = HorizonRunner(store)

    def step(seq, record):
        gate.wait(timeout=15)  # hold the run open mid-step
        return StepOutcome(done=True, note="final")

    handle = runner.start(goal.goal_id, step)
    time.sleep(0.1)
    record = store.get(goal.goal_id)  # straight from the file
    assert record.state == "running" and record.progress_seq == 0
    gate.set()
    handle.wait(timeout=15)
    return "mid-run disk read: running · seq 0 — not a stale memory"


def rung_5_heartbeat_alive_then_silent() -> str:
    store = GoalStore(fresh_dir() / "goals")
    goal = store.create_goal("beating", "until_completion")
    monitor = HeartbeatMonitor(fresh_after_seconds=0.2, stale_after_seconds=0.6)
    for name in monitor.watched:
        monitor.beat(name)
    runner = HorizonRunner(store, heartbeat=monitor)

    def step(seq, record):
        time.sleep(0.05)
        return StepOutcome(done=seq >= 3, note=f"beat {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=15)
    agent = monitor.check("agent")
    assert agent.status is ComponentStatus.ALIVE and agent.seq >= 5  # boot + 4 beats
    time.sleep(0.7)  # past the stale window on the REAL clock
    silent = monitor.check("agent")
    assert silent.status is ComponentStatus.SILENT
    return f"agent seq={agent.seq} ALIVE while stepping · SILENT from the clock after"


def rung_6_real_checkpoints_on_cadence() -> str:
    base = fresh_dir()
    store = GoalStore(base / "goals")
    ck_store = DiskCheckpointStore(base / "ck")
    manager = CheckpointManager(
        ck_store, base / "repo",
        version="0.25.0", phase=25,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )
    runner = HorizonRunner(store, checkpoints=manager, checkpoint_every=2)
    goal = store.create_goal("checkpointed", "until_completion")

    def step(seq, record):
        return StepOutcome(done=seq >= 5, note=f"step {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    handle.wait(timeout=15)
    assert handle.record().progress_seq == 6
    saved = handle.record().last_checkpoint_id
    assert saved is not None
    listed = {str(m.checkpoint_id) for m in ck_store.list()}
    triggers = [m.trigger.value for m in ck_store.list()]
    assert triggers.count("periodic") == 3  # after steps 2, 4, 6
    assert saved in listed
    return "3 PERIODIC captures on disk · newest id really in the §22 store"


def rung_7_bounded_deadline_hits() -> str:
    store = GoalStore(fresh_dir() / "goals")
    goal = store.create_goal("the wall", "30_minutes")
    wall = SteppedWall(1_700_000_000.0)
    runner = HorizonRunner(store, wall_clock=wall)

    def step(seq, record):
        wall.advance(400.0)  # each step burns 400s of the 1800s window
        return StepOutcome(done=False, note=f"still working {seq + 1}")

    handle = runner.start(goal.goal_id, step)
    final = handle.wait(timeout=15)
    assert final == "deadline_hit"
    record = handle.record()
    assert record.state == "deadline_hit"
    assert record.deadline_at == 1_700_000_000.0 + 1800.0
    notes = [n.message for n in handle.progress()]
    assert not any("completed" in m.lower() for m in notes)  # no fake finish
    assert record.progress_seq == 5
    return "wall at +1800s · 5 honest steps · deadline_hit — never a fake completion"


def rung_8_crash_and_resume() -> str:
    base = fresh_dir()
    store = GoalStore(base / "goals")
    goal = store.create_goal("died then continued", "until_completion")
    park = threading.Event()
    runner1 = HorizonRunner(store)

    def first_life(seq, record):
        if seq == 2:
            park.wait(timeout=15)  # the "dead" process sits inside step 2
        return StepOutcome(done=False, note=f"life one · step {seq + 1}")

    handle1 = runner1.start(goal.goal_id, first_life)
    deadline = time.time() + 10
    while handle1.record().progress_seq < 2 and time.time() < deadline:
        time.sleep(0.02)
    # the successor process (fresh store + fresh runner — the reboot)
    store2 = GoalStore(base / "goals")
    runner2 = HorizonRunner(store2)

    def second_life(seq, record):
        return StepOutcome(done=True, note=f"life two finished from seq {seq}")

    handle2 = resume(runner2, goal.goal_id, second_life)
    assert handle2.wait(timeout=15) == "completed"
    park.set()  # the ghost wakes — the generation lease must retire it
    handle1.wait(timeout=15)
    notes = [n.message for n in store2.progress(goal.goal_id)]
    assert notes[0] == "life one · step 1" and notes[1] == "life one · step 2"
    # the takeover is on the record: the crash left state=running, so
    # the resume says RESUMED and the work continues from the new seq
    assert any("RESUMED after interrupted run" in m for m in notes)
    assert any("life two finished from seq 3" in m for m in notes)
    assert not any("life one · step 3" in m for m in notes)  # ghost wrote nothing
    return "resumed from persisted seq · takeover noted · ghost retired without writing"


class _MissingCkpt:
    class _Store:
        def list(self):  # noqa: ANN202
            return []

    @property
    def store(self):  # noqa: ANN202
        return _MissingCkpt._Store()


def rung_9_no_blind_resume() -> str:
    base = fresh_dir()
    store = GoalStore(base / "goals")
    runner = HorizonRunner(store)

    # corrupt state — refused, named
    corrupt = store.create_goal("corrupt me", "2_hours")
    store.transition(corrupt.goal_id, "running")
    store.goal_path(corrupt.goal_id).write_text("{ not json", encoding="utf-8")
    try:
        resume(runner, corrupt.goal_id, lambda s, r: StepOutcome(done=True))
    except BlindResumeError as exc:
        assert any("unreadable" in r for r in exc.refusals)
    else:
        raise AssertionError("corrupt state resumed — blind!")

    # completed — terminal, refused
    done_goal = store.create_goal("already finished", "until_completion")
    store.transition(done_goal.goal_id, "running")
    store.transition(done_goal.goal_id, "completed")
    try:
        resume(runner, done_goal.goal_id, lambda s, r: StepOutcome(done=True))
    except BlindResumeError as exc:
        assert any("not resumable" in r for r in exc.refusals)
    else:
        raise AssertionError("a completed goal resumed — blind!")

    # recorded checkpoint missing from the §22 store — drift, refused
    drifted = store.create_goal("drifted", "2_hours")
    store.transition(drifted.goal_id, "running")
    store.set_checkpoint(drifted.goal_id, "ckpt_ghost")
    try:
        resume(
            runner, drifted.goal_id, lambda s, r: StepOutcome(done=True),
            checkpoints=_MissingCkpt(),
        )
    except BlindResumeError as exc:
        assert any("ckpt_ghost" in r and "drifted" in r for r in exc.refusals)
    else:
        raise AssertionError("a drifted checkpoint resumed — blind!")

    return "corrupt refused · terminal refused · drifted refused — every reason named"


def rung_10_journal_spine_and_fresh_window() -> str:
    store = GoalStore(fresh_dir() / "goals")
    goal = store.create_goal("the spine", "30_minutes")
    wall = SteppedWall(1_800_000_000.0)
    runner = HorizonRunner(store, wall_clock=wall)

    def burn(seq, record):
        wall.advance(700.0)
        return StepOutcome(done=False, note=f"burn {seq + 1}")

    handle = runner.start(goal.goal_id, burn)
    assert handle.wait(timeout=15) == "deadline_hit"  # 1800/700 → 3 steps
    first_window = handle.record().deadline_at

    wall.advance(3.0)
    wall_at_resume = wall.now
    runner2 = HorizonRunner(store, wall_clock=wall)
    handle2 = resume(runner2, goal.goal_id, lambda s, r: StepOutcome(done=True, note="again"))
    second_window = handle2.record().deadline_at
    assert second_window == wall_at_resume + 1800.0  # a FRESH window from now
    assert second_window > first_window  # the old wall did not carry over
    handle2.wait(timeout=15)
    seqs = [n.seq for n in handle2.progress()]
    assert seqs == list(range(1, len(seqs) + 1))  # monotonic, no gaps
    assert handle2.record().state == "completed"
    return (
        f"journal seq 1..{seqs[-1]} no gaps across both lives ·"
        " resume re-armed the 30-minute window"
    )


def rung_11_identity() -> str:
    import nexus

    assert nexus.NEXUS_PHASE >= 25, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
    major, minor, _ = (int(p) for p in nexus.__version__.split("."))
    assert (major, minor) >= (0, 25), f"version {nexus.__version__}"
    return f"nexus {nexus.__version__} · phase {nexus.NEXUS_PHASE}"


# -------------------------------------------------------------------- main


def main() -> int:
    rungs = (
        ("1 · §25 vocabulary verbatim", rung_1_vocabulary),
        ("2 · §25.1 the goal survives the reboot", rung_2_goal_persistence_reboot),
        ("3 · §25.2 a real background worker, caller unblocked",
         rung_3_background_worker_not_blocking),
        ("4 · §25.3 the state is true between steps (from disk)", rung_4_state_true_between_steps),
        ("5 · §25.4 §23 heartbeat: ALIVE stepping · SILENT after",
         rung_5_heartbeat_alive_then_silent),
        ("6 · §25.5 real §22 checkpoints on the cadence", rung_6_real_checkpoints_on_cadence),
        ("7 · §25.7 a bounded deadline hits honestly", rung_7_bounded_deadline_hits),
        ("8 · §25.6 crash and resume from the persisted seq", rung_8_crash_and_resume),
        ("9 · §25.6 no blind resume — every refusal named", rung_9_no_blind_resume),
        ("10 · integration — the journal spine · a fresh window",
         rung_10_journal_spine_and_fresh_window),
        ("11 · identity — phase ≥ 25 · core ≥ 0.25.0", rung_11_identity),
    )
    for label, fn in rungs:
        rung(label, fn)

    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    print(f"\nPROOF: {passed}/{len(RESULTS)} rungs passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
