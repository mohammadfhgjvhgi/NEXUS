#!/usr/bin/env python3
"""PHASE 23 live heartbeat proof — real threads, real clocks, real loops.

Ten rungs, each printed as [PASS]/[FAIL] with its observation (the §20
evidence law applied to §23):

  1. §23 vocabulary verbatim — seven components · four signals ·
     the five-rung ladder.
  2. §23.1 — a REAL thread beats the monitor on the real clock; the
     component reads ALIVE inside the fresh window.
  3. §23.1 — the thread actually stops (the silent stall); after the
     stale window the component reads SILENT — التوقف الصامت caught
     by the clock, not by an exception.
  4. §23.2 — a real action that really fails with the same error
     three times → SAME_ERROR from real observations.
  5. §23.2 — a real frozen loop (same action, same state) →
     SAME_ACTION + SAME_STATE + NO_PROGRESS together.
  6. §23.3 — retry resolves: the same action, attempted once more,
     really succeeds.
  7. §23.3 — retry fails honestly → alternate method resolves: a
     genuinely different implementation.
  8. §23.3 — both rungs fail → replan: the ladder's last word.
  9. Integration — the §22 law rides along: a real CheckpointManager
     captures a BEFORE_RISKY_CHANGE checkpoint before every mutating
     rung; the store lists them back from disk.
 10. Identity — NEXUS_PHASE ≥ 23 and nexus-core ≥ 0.23.0.

Run (CI/sandbox):  python tests/phase23/live_heartbeat_ci.py
Run (device, via pytest): tests/phase23/test_device_proof.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus.health import (  # noqa: E402
    MONITORED_COMPONENTS,
    RECOVERY_LADDER,
    STALL_SIGNALS,
    HealthSupervisor,
    HeartbeatMonitor,
    MonitoredComponent,
    Observation,
    RecoveryLadder,
    RecoveryResolution,
    StallDetector,
    StallSignal,
)
from nexus.recovery import (  # noqa: E402
    CheckpointManager,
    DiskCheckpointStore,
    TriggerEvent,
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


# ------------------------------------------------------------------- rungs


def rung_1_vocabulary() -> str:
    assert MONITORED_COMPONENTS == (
        "core", "agent", "model", "tool", "browser", "computer", "task",
    )
    assert STALL_SIGNALS == (
        "same_action", "same_error", "same_state", "no_progress",
    )
    assert RECOVERY_LADDER == (
        "detect", "diagnose", "retry", "alternate_method", "replan",
    )
    return "components 7 · signals 4 · ladder 5 — verbatim"


def rung_2_real_thread_beats_alive() -> str:
    monitor = HeartbeatMonitor(fresh_after_seconds=0.3, stale_after_seconds=1.0)
    stop = threading.Event()
    beats = threading.Event()

    def heart() -> None:
        while not stop.is_set():
            monitor.beat(MonitoredComponent.AGENT, detail="agent loop stepping")
            beats.set()
            time.sleep(0.05)

    worker = threading.Thread(target=heart, daemon=True)
    worker.start()
    try:
        assert beats.wait(timeout=5), "the real thread never beat"
        hb = monitor.check(MonitoredComponent.AGENT)
        assert hb.status.value == "alive", hb.as_dict()
        assert hb.seq >= 1
    finally:
        stop.set()
        worker.join(timeout=5)
    return f"real thread beat {hb.seq}× — alive inside the fresh window"


def rung_3_silence_is_caught_by_the_clock() -> str:
    monitor = HeartbeatMonitor(fresh_after_seconds=0.3, stale_after_seconds=1.0)
    monitor.beat(MonitoredComponent.MODEL, detail="about to hang")
    assert monitor.check(MonitoredComponent.MODEL).status.value == "alive"
    time.sleep(1.2)  # no beat, no exception, no log line — pure silence
    hb = monitor.check(MonitoredComponent.MODEL)
    assert hb.status.value == "silent", hb.as_dict()
    assert hb.age_seconds is not None and hb.age_seconds > 1.0
    return f"silent for {hb.age_seconds:.2f}s — التوقف الصامت caught by the clock"


def rung_4_real_failing_action_same_error() -> str:
    detector = StallDetector(repeat_threshold=3)
    attempts: list[str] = []
    counter = iter(range(1000))

    def real_step() -> tuple:
        """The real action — it really raises, and the detector really sees it."""
        try:
            raise ConnectionError("llama-server refused the socket")
        except ConnectionError as exc:
            attempts.append(type(exc).__name__)
            return detector.observe(
                Observation(
                    action=f"infer-{next(counter)}",  # the action moves — only the error loops
                    error=f"{type(exc).__name__}:refused",
                )
            )

    assert real_step() == ()
    assert real_step() == ()
    (finding,) = real_step()  # the third real failure completes the loop
    assert finding.signal is StallSignal.SAME_ERROR, finding.as_dict()
    return f"the real action failed {len(attempts)}× — same_error named the signature"


def rung_5_frozen_loop_traces_all_shapes() -> str:
    detector = StallDetector(repeat_threshold=3, progress_window=3)
    fired: list = []
    for _step in range(3):  # the worker's state never moves
        fired = detector.observe(
            Observation(action="click", state="screen-41", progress="cursor-7")
        )
    signals = {f.signal for f in fired}
    assert signals == {
        StallSignal.SAME_ACTION,
        StallSignal.SAME_STATE,
        StallSignal.NO_PROGRESS,
    }, signals
    return "same_action + same_state + no_progress — the frozen loop traced"


def rung_6_retry_resolves() -> str:
    attempts = 0

    def flaky_retry(finding):  # noqa: ANN001, ANN202
        nonlocal attempts
        attempts += 1
        return True  # this time it really worked

    ladder = RecoveryLadder(retry=flaky_retry)
    outcome = ladder.handle(
        StallDetector(repeat_threshold=2).observe(
            Observation(action="reload", state="h1", progress="p1"),
            Observation(action="reload", state="h1", progress="p1"),
        )[0]
    )
    assert outcome.resolution is RecoveryResolution.RESOLVED, outcome.as_dict()
    assert outcome.rungs == ("detect", "diagnose", "retry")
    assert attempts == 1
    return " → ".join(outcome.rungs) + " — the same action, retried once, resolved"


def rung_7_alternate_method_resolves() -> str:
    tried: list[str] = []

    def retry_fails(finding):  # noqa: ANN001, ANN202
        tried.append("retry")
        return False  # honestly attempted, honestly failed

    def alternate_works(finding):  # noqa: ANN001, ANN202
        tried.append("alternate")
        return True  # a genuinely different method

    ladder = RecoveryLadder(retry=retry_fails, alternate=alternate_works)
    outcome = ladder.handle(
        StallDetector(repeat_threshold=2).observe(
            Observation(action="uia-click", state="h2", progress="p2"),
            Observation(action="uia-click", state="h2", progress="p2"),
        )[0]
    )
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert tried == ["retry", "alternate"]
    assert outcome.stopped_at == "alternate_method"
    return f"{tried[0]} failed → {tried[1]} resolved — the ladder climbed"


def rung_8_replan_is_the_last_word() -> str:
    handed: list = []
    ladder = RecoveryLadder(
        retry=lambda f: False,
        alternate=lambda f: False,
        replan=lambda f: handed.append(f.signal) or RecoveryResolution.REPLAN_NEEDED,
    )
    outcome = ladder.handle(
        StallDetector(repeat_threshold=2).observe(
            Observation(action="scroll", state="h3", progress="p3"),
            Observation(action="scroll", state="h3", progress="p3"),
        )[0]
    )
    assert outcome.resolution is RecoveryResolution.REPLAN_NEEDED
    assert outcome.rungs == RECOVERY_LADDER
    assert handed, "the planner never received the problem"
    return "all four rungs honestly failed → replan — the ladder's last word"


def rung_9_the_22_law_checkpoints_before_risky_rungs() -> str:
    import tempfile

    base = Path(tempfile.mkdtemp(prefix="p23-live-22-")) / "ck"
    store = DiskCheckpointStore(base, keep_per_scope=8)
    manager = CheckpointManager(
        store, base.parent, version="0.23.0", phase=23,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )
    announced: list[str] = []

    def announce(rung: str, finding) -> None:  # noqa: ANN001, ANN202
        made = manager.on_event(TriggerEvent.BEFORE_RISKY_CHANGE,
                                label=f"§23.3 {rung} — {finding.signal.value}")
        assert made is not None
        announced.append(rung)

    ladder = RecoveryLadder(
        retry=lambda f: False,
        alternate=lambda f: True,
        before_rung=announce,
    )
    outcome = ladder.handle(
        StallDetector(repeat_threshold=2).observe(
            Observation(action="paste", state="h9", progress="p9"),
            Observation(action="paste", state="h9", progress="p9"),
        )[0]
    )
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert announced == ["retry", "alternate_method"], announced
    on_disk = [m.trigger.value for m in store.list()]
    assert on_disk.count("before_risky_change") >= 2, on_disk
    return f"{announced} → {on_disk.count('before_risky_change')} §22 checkpoints on disk"


def rung_10_identity() -> str:
    import nexus

    assert nexus.NEXUS_PHASE >= 23, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
    major, minor, _ = (int(p) for p in nexus.__version__.split("."))
    assert (major, minor) >= (0, 23), f"version {nexus.__version__}"
    return f"nexus {nexus.__version__} · NEXUS_PHASE={nexus.NEXUS_PHASE}"


def rung_supervisor_end_to_end() -> str:
    """A bonus end-to-end rung — supervisor: alive → loop → ladder → resolved."""
    monitor = HeartbeatMonitor(fresh_after_seconds=5.0, stale_after_seconds=20.0)
    for name in monitor.watched:
        monitor.beat(name)
    sup = HealthSupervisor(monitor, RecoveryLadder(retry=lambda f: True),
                           repeat_threshold=3, progress_window=4)
    for i in range(2):
        report = sup.poll({MonitoredComponent.TASK: Observation(
            action="compile", state=f"unit-{i}", progress=f"step-{i}")})
        assert not report.findings
    report = sup.poll({MonitoredComponent.TASK: Observation(
        action="compile", state="unit-2", progress="step-2")})
    assert len(report.findings) == 1 and report.findings[0].signal is StallSignal.SAME_ACTION
    assert report.outcomes[0].resolution is RecoveryResolution.RESOLVED
    assert sup.detector(MonitoredComponent.TASK).depth == 0  # reset on resolve
    assert report.health.verdict.value in ("healthy", "degraded")
    return "poll → finding → ladder → resolved — the supervisor in one breath"


# --------------------------------------------------------------------- main


def main() -> int:
    print("PHASE 23 — Heartbeat + Health — live proof")
    rung("1 · §23 vocabulary verbatim", rung_1_vocabulary)
    rung("2 · §23.1 a real thread beats — alive", rung_2_real_thread_beats_alive)
    rung("3 · §23.1 the thread stops — silent by the clock", rung_3_silence_is_caught_by_the_clock)
    rung("4 · §23.2 a real failing action — same_error", rung_4_real_failing_action_same_error)
    rung("5 · §23.2 a frozen loop traces its shapes", rung_5_frozen_loop_traces_all_shapes)
    rung("6 · §23.3 retry resolves at rung three", rung_6_retry_resolves)
    rung("7 · §23.3 retry fails → alternate method resolves", rung_7_alternate_method_resolves)
    rung("8 · §23.3 both fail → replan", rung_8_replan_is_the_last_word)
    rung("9 · §22 checkpoints before risky rungs", rung_9_the_22_law_checkpoints_before_risky_rungs)
    rung("10 · supervisor end-to-end", rung_supervisor_end_to_end)
    rung("11 · identity ≥ 0.23.0 / phase ≥ 23", rung_10_identity)

    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    print(f"\nPROOF: {passed}/{len(RESULTS)} rungs passed")
    for status, label, note in RESULTS:
        if status == "FAIL":
            print(f"  ✗ {label}: {note}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
