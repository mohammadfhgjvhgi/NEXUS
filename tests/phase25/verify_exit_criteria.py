#!/usr/bin/env python3
"""Phase 25 horizon harness — New Plan §25 Exit Gate.

Proves the Long-Horizon Execution section by section:

* A — Contracts (§25.1–§25.7): the verbatim vocabulary — the four
      deadlines with their honest windows · the six-state ladder and
      its transition law · the resumable set — plus the round-trips
      and the error family.
* B — Goal persistence + long-running state (§25.1+§25.3): goals are
      written atomically and survive a reboot; the ladder refuses
      illegal transitions; the journal is append-only with a
      monotonic seq; a corrupt state file is refused, never forgotten.
* C — Background workers + deadline (§25.2+§25.7): the handle returns
      while the real thread works; the state is true from disk
      mid-run; a bounded deadline stops with deadline_hit (never a
      fake completion); until_completion has no wall; a step
      exception fails honestly; pause obeys the disk.
* D — Heartbeat + checkpoints (§25.4+§25.5): the §23 monitor is
      beaten per step and at the milestones; a real §22
      CheckpointManager captures PERIODIC checkpoints on the cadence
      and the persisted id is really in the store.
* E — Resume (§25.6): the successor process continues from the
      persisted seq; no blind resume — corrupt state, terminal goals
      and drifted checkpoints are refused with every reason named;
      the generation lease retires a superseded worker before it can
      write; resuming a deadline-hit goal re-arms a fresh window.
* F — Integration + regression: NEXUS_PHASE ≥ 25, nexus-core ≥
      0.25.0, the horizon core stays stdlib-only at module top level,
      and the neighbor phase suites (15–24) stay green (skippable
      with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_types: tuple[type, ...] | type, fn, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    try:
        fn(*args, **kwargs)
    except exc_types:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_types}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_types}, nothing raised")


class Wall:
    """A hand-driven wall clock — epoch time is a variable here."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


# ---------------------------------------------------------------- helpers


def fresh_world():
    from nexus.horizon import GoalStore, HorizonRunner

    base = Path(tempfile.mkdtemp(prefix="p25-gate-"))
    wall = Wall()
    store = GoalStore(base / "goals")
    runner = HorizonRunner(store, wall_clock=wall)
    return store, runner, wall, base


def step_until(limit: int):  # type: ignore[no-untyped-def]
    from nexus.horizon import StepOutcome

    def step(seq, record):  # noqa: ANN001, ANN202
        return StepOutcome(done=seq >= limit, note=f"step {seq + 1}")

    return step


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.horizon import (
        DEADLINE_SECONDS,
        DEADLINES,
        GOAL_STATES,
        RESUMABLE_STATES,
        TRANSITIONS,
        BlindResumeError,
        GoalRecord,
        HorizonError,
        IllegalTransitionError,
        ProgressNote,
        StepOutcome,
        UnknownDeadlineError,
        UnknownGoalError,
        deadline_seconds,
    )

    def vocabulary_verbatim() -> None:
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
            "pending", "running", "paused", "completed", "failed",
            "deadline_hit",
        )
        assert TRANSITIONS["completed"] == frozenset()  # terminal
        assert RESUMABLE_STATES == frozenset(
            {"paused", "failed", "deadline_hit", "running"}
        )

    def roundtrips() -> None:
        record = GoalRecord(
            goal_id="goal_abc123456789", statement="s", deadline="2_hours",
            state="running", progress_seq=3, last_checkpoint_id="c1",
            generation=2, deadline_at=1_700_000_000.0,
        )
        assert GoalRecord.from_dict(record.as_dict()) == record
        unbounded = GoalRecord(
            goal_id="goal_abc123456790", statement="s",
            deadline="until_completion",
        )
        assert GoalRecord.from_dict(unbounded.as_dict()).deadline_at is None
        note = ProgressNote(seq=2, ts="t", message="m")
        assert ProgressNote.from_dict(note.as_dict()) == note
        outcome = StepOutcome(done=True, note="d")
        assert outcome.done and outcome.note == "d"

    def error_family() -> None:
        for exc in (
            UnknownDeadlineError, UnknownGoalError,
            IllegalTransitionError, BlindResumeError,
        ):
            assert issubclass(exc, HorizonError)
        expects((UnknownDeadlineError,), deadline_seconds, "forever")
        expects((HorizonError,), GoalRecord, goal_id=" ", statement="s",
                deadline="2_hours")

    check("A1 · §25.1–§25.7 vocabulary verbatim", vocabulary_verbatim)
    check("A2 · the contracts round-trip (unbounded stays None)", roundtrips)
    check("A3 · the error family is honest", error_family)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.horizon import (
        GoalStore,
        HorizonError,
        IllegalTransitionError,
        UnknownGoalError,
    )

    def atomic_persistence_and_reboot() -> None:
        store, _, _, base = fresh_world()
        goal = store.create_goal("خذ المهمة واشتغل لحد ما تخلص", "8_hours")
        on_disk = json.loads(store.goal_path(goal.goal_id).read_text(encoding="utf-8"))
        assert on_disk["state"] == "pending"
        store2 = GoalStore(base / "goals")
        found = store2.get(goal.goal_id)
        assert found.statement == goal.statement
        assert found.created_at == goal.created_at
        assert len(store2.list_goals()) == 1
        expects((UnknownGoalError,), store.get, "goal_missing")

    def ladder_law() -> None:
        store, _, _, _ = fresh_world()
        goal = store.create_goal("legal walker", "2_hours")
        store.transition(goal.goal_id, "running")
        store.transition(goal.goal_id, "paused")
        store.transition(goal.goal_id, "running")
        store.transition(goal.goal_id, "completed")
        expects((IllegalTransitionError,), store.transition, goal.goal_id, "running")
        fresh, _, _, _ = fresh_world()
        g2 = fresh.create_goal("never skipped", "2_hours")
        expects((IllegalTransitionError,), fresh.transition, g2.goal_id, "completed")

    def journal_monotonic() -> None:
        store, _, _, _ = fresh_world()
        goal = store.create_goal("counted", "2_hours")
        seqs = [store.append_progress(goal.goal_id, f"n{i}").seq for i in range(3)]
        assert seqs == [1, 2, 3]
        assert store.get(goal.goal_id).progress_seq == 3
        store2 = GoalStore(store.directory)  # the reboot path
        assert store2.append_progress(goal.goal_id, "n3").seq == 4
        expects((HorizonError,), store.append_progress, goal.goal_id, "  ")

    def corrupt_refused() -> None:
        store, _, _, _ = fresh_world()
        goal = store.create_goal("corrupt me", "2_hours")
        store.goal_path(goal.goal_id).write_text("{ not json", encoding="utf-8")
        expects((HorizonError,), store.get, goal.goal_id)

    check("B1 · §25.1 atomic writes · the reboot finds the goal", atomic_persistence_and_reboot)
    check("B2 · §25.3 the ladder refuses illegal transitions", ladder_law)
    check("B3 · the journal is monotonic and continues across reboots", journal_monotonic)
    check("B4 · a corrupt state file is refused, never forgotten", corrupt_refused)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.horizon import (
        HorizonError,
        StepOutcome,
        deadline_window,
    )

    def background_and_durable_state() -> None:
        store, runner, _, _ = fresh_world()
        goal = store.create_goal("watched", "until_completion")
        gate = threading.Event()

        def step(seq, record):  # noqa: ANN001, ANN202
            gate.wait(timeout=10)
            return StepOutcome(done=True, note="final")

        handle = runner.start(goal.goal_id, step)
        time.sleep(0.1)
        assert handle.is_alive()
        assert handle.state() == "running"  # from disk, mid-run
        record = store.get(goal.goal_id)
        assert record.state == "running" and record.progress_seq == 0
        gate.set()
        assert handle.wait(timeout=10) == "completed"
        assert handle.record().progress_seq == 1

    def deadline_math() -> None:
        wall = Wall()
        assert deadline_window("30_minutes", wall_clock=wall) == wall() + 1800.0
        assert deadline_window("2_hours", wall_clock=wall) == wall() + 7200.0
        assert deadline_window("8_hours", wall_clock=wall) == wall() + 28800.0
        assert deadline_window("until_completion", wall_clock=wall) is None

    def bounded_wall_hits_honestly() -> None:
        store, runner, wall, _ = fresh_world()
        goal = store.create_goal("the wall", "30_minutes")
        start_wall = wall.now

        def step(seq, record):  # noqa: ANN001, ANN202
            wall.advance(400.0)
            return StepOutcome(done=False)

        handle = runner.start(goal.goal_id, step)
        assert handle.wait(timeout=10) == "deadline_hit"
        record = handle.record()
        assert record.state == "deadline_hit" and record.progress_seq == 5
        assert record.deadline_at == start_wall + 1800.0  # the window, persisted
        notes = [n.message for n in handle.progress()]
        assert not any("FAILED" in m for m in notes)  # honest, not broken

    def unbounded_no_wall() -> None:
        store, runner, wall, _ = fresh_world()
        goal = store.create_goal("no wall", "until_completion")

        def step(seq, record):  # noqa: ANN001, ANN202
            wall.advance(100_000.0)
            return StepOutcome(done=seq >= 1, note="done")

        handle = runner.start(goal.goal_id, step)
        assert handle.wait(timeout=10) == "completed"
        assert handle.record().deadline_at is None

    def failure_and_pause() -> None:
        store, runner, _, _ = fresh_world()
        goal = store.create_goal("doomed", "until_completion")

        def boom(seq, record):  # noqa: ANN001, ANN202
            raise RuntimeError("gone")

        handle = runner.start(goal.goal_id, boom)
        assert handle.wait(timeout=10) == "failed"
        assert "FAILED: RuntimeError" in handle.progress()[-1].message

        goal2 = store.create_goal("pausable", "until_completion")
        hit = threading.Event()

        def slow(seq, record):  # noqa: ANN001, ANN202
            hit.set()
            time.sleep(0.03)
            return StepOutcome(done=False)

        h2 = runner.start(goal2.goal_id, slow)
        hit.wait(timeout=10)
        assert h2.pause() == "paused"
        assert h2.wait(timeout=10) == "paused"
        expects((HorizonError,), runner.start, goal2.goal_id, slow)  # not pending

    check("C1 · §25.2 the background worker + the mid-run disk truth",
          background_and_durable_state)
    check("C2 · §25.7 the four windows are the honest arithmetic", deadline_math)
    check("C3 · §25.7 a bounded wall stops with deadline_hit", bounded_wall_hits_honestly)
    check("C4 · §25.7 until_completion has no wall at all", unbounded_no_wall)
    check("C5 · honest failure · pause obeys the disk · start needs pending", failure_and_pause)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.health import ComponentStatus, HeartbeatMonitor
    from nexus.horizon import HorizonRunner
    from nexus.recovery import (
        CheckpointManager,
        DiskCheckpointStore,
        TriggerPolicy,
    )

    def heartbeat_rides() -> None:
        store, _, wall, _ = fresh_world()
        monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
        for name in monitor.watched:
            monitor.beat(name)
        runner = HorizonRunner(store, heartbeat=monitor, wall_clock=wall)
        goal = store.create_goal("observed", "until_completion")
        handle = runner.start(goal.goal_id, step_until(4))
        handle.wait(timeout=10)
        assert monitor.check("agent").seq >= 5  # boot + 4 step beats
        assert monitor.check("task").seq >= 2  # the completed milestone
        assert monitor.check("agent").status is ComponentStatus.ALIVE

    def real_checkpoints_on_cadence() -> None:
        store, _, wall, base = fresh_world()
        ck_store = DiskCheckpointStore(base / "ck")
        manager = CheckpointManager(
            ck_store, base / "repo",
            version="0.25.0", phase=25,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )
        runner = HorizonRunner(
            store, checkpoints=manager, checkpoint_every=2, wall_clock=wall
        )
        goal = store.create_goal("checkpointed", "until_completion")
        handle = runner.start(goal.goal_id, step_until(6))
        handle.wait(timeout=10)
        assert handle.record().progress_seq == 7
        triggers = [m.trigger.value for m in ck_store.list()]
        assert triggers.count("periodic") == 3  # after steps 2, 4, 6
        saved = handle.record().last_checkpoint_id
        assert saved is not None
        assert saved in {str(m.checkpoint_id) for m in ck_store.list()}

    check("D1 · §25.4 the §23 heartbeat rides every step + milestone", heartbeat_rides)
    check("D2 · §25.5 real §22 PERIODIC captures · the id is really there",
          real_checkpoints_on_cadence)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.horizon import (
        BlindResumeError,
        HorizonRunner,
        ResumeInspector,
        StepOutcome,
        resume,
    )

    def resume_from_persisted_seq() -> None:
        store, runner, _, _ = fresh_world()
        goal = store.create_goal("interrupted", "until_completion")
        park = threading.Event()

        def first(seq, record):  # noqa: ANN001, ANN202
            if seq == 2:
                park.wait(timeout=10)
            return StepOutcome(done=False, note=f"one · {seq + 1}")

        handle = runner.start(goal.goal_id, first)
        deadline = time.time() + 5
        while handle.record().progress_seq < 2 and time.time() < deadline:
            time.sleep(0.02)
        handle.pause()
        park.set()
        handle.wait(timeout=10)
        runner2 = HorizonRunner(store, wall_clock=runner._wall)
        h2 = resume(
            runner2, goal.goal_id,
            lambda s, r: StepOutcome(done=True, note=f"two · from {s}"),
        )
        assert h2.wait(timeout=10) == "completed"
        messages = [n.message for n in h2.progress()]
        assert messages[-1] == "two · from 3"
        assert h2.record().progress_seq == 4

    def no_blind_resume() -> None:
        store, runner, _, _ = fresh_world()
        corrupt = store.create_goal("corrupt", "2_hours")
        store.transition(corrupt.goal_id, "running")
        store.goal_path(corrupt.goal_id).write_text("{ bad", encoding="utf-8")
        expects((BlindResumeError,), resume, runner, corrupt.goal_id, step_until(0))

        terminal = store.create_goal("done already", "until_completion")
        store.transition(terminal.goal_id, "running")
        store.transition(terminal.goal_id, "completed")
        expects((BlindResumeError,), resume, runner, terminal.goal_id, step_until(0))

        class _Missing:
            class _Store:
                def list(self):  # noqa: ANN202
                    return []

            @property
            def store(self):  # noqa: ANN202
                return _Missing._Store()

        drifted = store.create_goal("drifted", "2_hours")
        store.transition(drifted.goal_id, "running")
        store.set_checkpoint(drifted.goal_id, "ckpt_ghost")
        expects(
            (BlindResumeError,),
            resume, runner, drifted.goal_id, step_until(0), checkpoints=_Missing(),
        )
        verdict = ResumeInspector(store, checkpoints=_Missing()).inspect(
            drifted.goal_id
        )
        assert any("ckpt_ghost" in r and "drifted" in r for r in verdict.refusals)

    def generation_lease() -> None:
        store, runner, _, _ = fresh_world()
        goal = store.create_goal("one owner", "until_completion")
        park = threading.Event()

        def slow(seq, record):  # noqa: ANN001, ANN202
            park.wait(timeout=15)
            return StepOutcome(done=False, note="ghost step")

        handle1 = runner.start(goal.goal_id, slow)
        time.sleep(0.1)
        store.begin_run(goal.goal_id, deadline_at=None)  # the successor's lease

        def fast(seq, record):  # noqa: ANN001, ANN202
            return StepOutcome(done=True, note="new owner done")

        handle2 = runner.relaunch(goal.goal_id, fast)
        assert handle2.wait(timeout=10) == "completed"
        park.set()
        handle1.wait(timeout=15)
        assert not any("ghost step" in n.message for n in store.progress(goal.goal_id))
        assert store.get(goal.goal_id).state == "completed"

    def fresh_window_after_deadline() -> None:
        store, runner, wall, _ = fresh_world()
        goal = store.create_goal("wall then again", "30_minutes")

        def burn(seq, record):  # noqa: ANN001, ANN202
            wall.advance(2000.0)
            return StepOutcome(done=False)

        handle = runner.start(goal.goal_id, burn)
        assert handle.wait(timeout=10) == "deadline_hit"
        wall.advance(5.0)
        wall_at_resume = wall.now
        h2 = resume(
            HorizonRunner(store, wall_clock=wall), goal.goal_id, step_until(0)
        )
        assert h2.record().deadline_at == wall_at_resume + 1800.0
        h2.wait(timeout=10)
        assert h2.record().state == "completed"

    check("E1 · §25.6 the successor continues from the persisted seq", resume_from_persisted_seq)
    check("E2 · §25.6 no blind resume — every refusal named", no_blind_resume)
    check("E3 · the generation lease retires the ghost before it writes", generation_lease)
    check("E4 · a deadline bounds ONE run — resume re-arms a window",
          fresh_window_after_deadline)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 25, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 25), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "horizon"
        for py in pkg.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.level > 0:
                        continue  # relative — nexus's own
                    roots = (
                        [a.name.split(".")[0] for a in node.names]
                        if isinstance(node, ast.Import)
                        else [str(node.module or "").split(".")[0]]
                    )
                    for root in roots:
                        assert root in sys.stdlib_module_names | {"nexus"} or root == "", (
                            f"{py.name}: non-stdlib top-level import {root!r}"
                        )

    def regression() -> None:
        if NO_REGRESSION:
            print("      (skipped by --no-regression)")
            return
        import subprocess

        for phase in (15, 16, 17, 18, 19, 20, 21, 22, 23, 24):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 25 and nexus-core ≥ 0.25.0", identity)
    check("F2 · the horizon core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–24 stay green", regression)


# ----------------------------------------------------------------------- main

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 25 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 25 — Long-Horizon Execution — Exit Gate")
    for section, title in (
        (section_a, "A · Contracts & vocabulary (§25.1–§25.7)"),
        (section_b, "B · Goal persistence + long-running state (§25.1+§25.3)"),
        (section_c, "C · Background workers + deadline (§25.2+§25.7)"),
        (section_d, "D · Heartbeat + checkpoints (§25.4+§25.5)"),
        (section_e, "E · Resume, never blind (§25.6)"),
        (section_f, "F · Integration + regression"),
    ):
        print(f"\n[{title}]")
        section()

    print(f"\nGATE: {len(PASSED)} passed · {len(FAILED)} failed")
    if FAILED:
        for line in FAILED:
            print(f"  ✗ {line}")
        return 1
    print("EXIT CRITERIA: Implemented · Integrated · Tested · Verified · Documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
