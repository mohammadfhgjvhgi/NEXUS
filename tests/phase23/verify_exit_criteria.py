#!/usr/bin/env python3
"""Phase 23 health harness — New Plan §23 Exit Gate.

Proves the Heartbeat + Health section by section:

* A — Contracts (§23.1–§23.3): the verbatim vocabulary — the seven
      watch targets · the four stall signals · the five-rung ladder —
      plus the round-trips and the error family.
* B — Heartbeat (§23.1): all seven components owe the monitor a
      beat; status derived from the clock (fresh → alive · late →
      degraded · stale → silent — التوقف الصامت — · acknowledged →
      stalled until a fresh beat clears it); unknown components
      refused; the worst sign wins the snapshot.
* C — Stall Detection (§23.2): same action · same error · same
      state · no progress each fire from real observation runs;
      empty fields never judged; one fire per evidence; reset
      re-arms; a fully frozen loop traces all four shapes at once.
* D — Recovery (§23.3): the ladder detect → diagnose → retry →
      alternate method → replan walked rung by rung — retry
      resolves, a failed retry climbs to the alternate method, both
      fail → replan; a refuted finding ends honestly at detect;
      absent rungs climb past honestly; a raising rung escalates
      without dying; a failed §22 announcement refuses the rung.
* E — Supervisor + the §22 law: silence becomes a no_progress
      finding; a confirmed loop walks the ladder and marks the
      component STALLED until it beats again; a resolved outcome
      resets the private detector; a real CheckpointManager captures
      BEFORE_RISKY_CHANGE checkpoints before every mutating rung.
* F — Integration + regression: NEXUS_PHASE ≥ 23, nexus-core ≥
      0.23.0, the health core stays stdlib-only at module top level,
      and the neighbor phase suites (15–22) stay green (skippable
      with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
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


class Clock:
    """A hand-driven monotonic clock — time is a variable here."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.health import (
        HEALTH_SCHEMA_VERSION,
        MONITORED_COMPONENTS,
        RECOVERY_LADDER,
        STALL_SIGNALS,
        ComponentStatus,
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

    def vocabulary_verbatim() -> None:
        assert MONITORED_COMPONENTS == (
            "core", "agent", "model", "tool", "browser", "computer", "task",
        )
        assert STALL_SIGNALS == (
            "same_action", "same_error", "same_state", "no_progress",
        )
        assert RECOVERY_LADDER == (
            "detect", "diagnose", "retry", "alternate_method", "replan",
        )
        assert {c.value for c in MonitoredComponent} == set(MONITORED_COMPONENTS)
        assert {s.value for s in StallSignal} == set(STALL_SIGNALS)
        assert {v.value for v in HealthVerdict} == {
            "healthy", "degraded", "stalled",
        }
        assert {r.value for r in RecoveryResolution} == {
            "not_confirmed", "resolved", "replan_needed",
        }
        assert {c.value for c in ComponentStatus} == {
            "alive", "degraded", "stalled", "silent",
        }
        assert HEALTH_SCHEMA_VERSION == 1

    def roundtrips() -> None:
        hb = Heartbeat(
            component=MonitoredComponent.COMPUTER,
            status=ComponentStatus.DEGRADED, seq=7, age_seconds=41.5,
        )
        assert Heartbeat.from_dict(hb.as_dict()) == hb
        never = Heartbeat(
            component=MonitoredComponent.MODEL,
            status=ComponentStatus.SILENT, seq=0, age_seconds=None,
        )
        assert Heartbeat.from_dict(never.as_dict()).age_seconds is None
        report = HealthReport(verdict=HealthVerdict.STALLED, components=(hb,))
        assert HealthReport.from_dict(report.as_dict()) == report
        obs = Observation(action="click", state="h", progress="p")
        assert Observation.from_dict(obs.as_dict()) == obs
        finding = StallFinding(
            signal=StallSignal.SAME_ERROR, repeats=3, detail="loop",
            component=MonitoredComponent.TOOL,
        )
        assert StallFinding.from_dict(finding.as_dict()) == finding
        outcome = LadderOutcome(
            finding=finding, resolution=RecoveryResolution.REPLAN_NEEDED,
            rungs=RECOVERY_LADDER, stopped_at="replan",
        )
        assert LadderOutcome.from_dict(outcome.as_dict()) == outcome
        sup = SupervisorReport(health=report, findings=(finding,), outcomes=(outcome,))
        assert SupervisorReport.from_dict(sup.as_dict()) == sup

    def error_family() -> None:
        assert issubclass(UnknownComponentError, HealthError)
        expects((HealthError,), bad_monitor_config)

    def bad_monitor_config() -> None:
        from nexus.health import HeartbeatMonitor

        HeartbeatMonitor(fresh_after_seconds=10.0, stale_after_seconds=5.0)

    check("A1 · §23.1–§23.3 vocabulary verbatim", vocabulary_verbatim)
    check("A2 · the contracts round-trip (never-beat age stays None)", roundtrips)
    check("A3 · the error family is honest", error_family)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.health import (
        ComponentStatus,
        HealthVerdict,
        HeartbeatMonitor,
        MonitoredComponent,
        UnknownComponentError,
    )

    fresh, stale = 30.0, 90.0

    def monitor(clock: Clock) -> HeartbeatMonitor:
        return HeartbeatMonitor(
            fresh_after_seconds=fresh, stale_after_seconds=stale, clock=clock
        )

    def seven_owe_a_beat() -> None:
        clock = Clock()
        m = monitor(clock)
        assert tuple(c.value for c in m.watched) == (
            "core", "agent", "model", "tool", "browser", "computer", "task",
        )
        m.beat("core", detail="boot")
        hb = m.check("core")
        assert hb.status is ComponentStatus.ALIVE and hb.seq == 1
        clock.advance(fresh + 1)
        assert m.check("core").status is ComponentStatus.DEGRADED
        clock.advance(stale - fresh)
        assert m.check("core").status is ComponentStatus.SILENT

    def never_and_refusals() -> None:
        m = monitor(Clock())
        hb = m.check("model")
        assert hb.status is ComponentStatus.SILENT and hb.age_seconds is None
        expects((UnknownComponentError,), m.beat, "workflow-engine")
        expects((UnknownComponentError,), m.check, "workflow-engine")
        expects((UnknownComponentError,), m.mark_stalled, "workflow-engine")

    def stalls_and_clearing() -> None:
        clock = Clock()
        m = monitor(clock)
        for name in m.watched:
            m.beat(name)  # the boot beat — nobody is silent from birth here
        m.beat("task")
        m.mark_stalled("task", detail="same_action ×3")
        assert m.check("task").status is ComponentStatus.STALLED
        m.beat("task")  # the component proves recovery by beating
        assert m.check("task").status is ComponentStatus.ALIVE
        assert m.snapshot().verdict is HealthVerdict.HEALTHY
        m.beat(MonitoredComponent.TOOL)
        m.mark_stalled(MonitoredComponent.TOOL)
        assert m.snapshot().verdict is HealthVerdict.STALLED

    check("B1 · §23.1 seven watch targets · fresh → late → silent", seven_owe_a_beat)
    check("B2 · never-beat is silent from birth · unknowns refused", never_and_refusals)
    check("B3 · an acknowledged stall holds until a beat clears it", stalls_and_clearing)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.health import Observation, StallDetector, StallSignal

    repeat = 3

    def four_shapes() -> None:
        d = StallDetector(repeat_threshold=repeat)
        assert d.observe(Observation(action="click", state="s1", progress="p1")) == ()
        assert d.observe(Observation(action="click", state="s2", progress="p2")) == ()
        (finding,) = d.observe(Observation(action="click", state="s3", progress="p3"))
        assert finding.signal is StallSignal.SAME_ACTION

        d2 = StallDetector(repeat_threshold=repeat)
        for _ in range(repeat - 1):
            assert d2.observe(Observation(error="E:timeout")) == ()
        (err,) = d2.observe(Observation(error="E:timeout"))
        assert err.signal is StallSignal.SAME_ERROR

        d3 = StallDetector(repeat_threshold=repeat)
        for i in range(repeat - 1):
            assert d3.observe(Observation(action=f"a{i}", state="dead")) == ()
        (st,) = d3.observe(Observation(action="aN", state="dead"))
        assert st.signal is StallSignal.SAME_STATE

        d4 = StallDetector(repeat_threshold=5, progress_window=4)
        for _ in range(3):
            assert d4.observe(Observation(state="frozen", progress="")) == ()
        (np,) = d4.observe(Observation(state="frozen", progress=""))
        assert np.signal is StallSignal.NO_PROGRESS

    def discipline() -> None:
        d = StallDetector(repeat_threshold=repeat)
        for _ in range(repeat):
            d.observe(Observation(action="click", state="s1", progress="p1"))
        assert d.observe(Observation(action="click", state="s1", progress="p1")) == ()
        d.reset()
        assert d.depth == 0
        d2 = StallDetector(repeat_threshold=repeat, progress_window=3)
        frozen = Observation(action="click", error="E", state="s1", progress="p1")
        d2.observe(frozen)
        d2.observe(frozen)
        signals = {f.signal for f in d2.observe(frozen)}
        assert signals == set(StallSignal), signals

    check("C1 · §23.2 the four loop shapes fire from real runs", four_shapes)
    check("C2 · one fire per evidence · reset re-arms · all four at once", discipline)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.health import (
        RECOVERY_LADDER,
        RecoveryLadder,
        RecoveryResolution,
        StallFinding,
        StallSignal,
    )

    def finding() -> StallFinding:
        return StallFinding(signal=StallSignal.SAME_ACTION, repeats=3, detail="loop")

    def resolutions() -> None:
        out = RecoveryLadder(retry=lambda f: True).handle(finding())
        assert out.resolution is RecoveryResolution.RESOLVED
        assert out.rungs == ("detect", "diagnose", "retry")
        out = RecoveryLadder(
            retry=lambda f: False, alternate=lambda f: True
        ).handle(finding())
        assert out.resolution is RecoveryResolution.RESOLVED
        assert out.stopped_at == "alternate_method"
        out = RecoveryLadder(
            retry=lambda f: False, alternate=lambda f: False
        ).handle(finding())
        assert out.resolution is RecoveryResolution.REPLAN_NEEDED
        assert out.rungs == RECOVERY_LADDER

    def honest_climbs() -> None:
        out = RecoveryLadder(confirm=lambda f: False, retry=lambda f: True).handle(finding())
        assert out.resolution is RecoveryResolution.NOT_CONFIRMED
        assert out.rungs == ("detect",)

        def boom(f: StallFinding) -> bool:
            raise RuntimeError("device gone")

        out = RecoveryLadder(retry=boom, alternate=lambda f: True).handle(finding())
        assert out.resolution is RecoveryResolution.RESOLVED
        assert "raised RuntimeError" in out.detail

        bare = RecoveryLadder().handle(finding())
        assert bare.resolution is RecoveryResolution.REPLAN_NEEDED
        assert bare.rungs == RECOVERY_LADDER

    def the_22_gate() -> None:
        def no_checkpoint(rung: str, f: StallFinding) -> None:
            raise RuntimeError("§22 store unavailable")

        out = RecoveryLadder(retry=lambda f: True, before_rung=no_checkpoint).handle(finding())
        assert out.resolution is RecoveryResolution.REPLAN_NEEDED
        assert "retry" not in out.rungs  # the rung never fired
        assert "REFUSED" in out.detail

    check("D1 · §23.3 retry resolves · alternate resolves · replan ends", resolutions)
    check("D2 · refuted ends at detect · raising climbs · absent climbs", honest_climbs)
    check("D3 · a failed §22 announcement refuses the risky rung", the_22_gate)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.health import (
        ComponentStatus,
        HealthSupervisor,
        HeartbeatMonitor,
        MonitoredComponent,
        Observation,
        RecoveryLadder,
        RecoveryResolution,
        StallSignal,
    )

    def supervisor(clock: Clock, **ladder_kwargs):  # noqa: ANN202
        mon = HeartbeatMonitor(
            fresh_after_seconds=10.0, stale_after_seconds=30.0, clock=clock
        )
        for name in mon.watched:
            mon.beat(name)  # the boot beat — the world starts alive
        return HealthSupervisor(
            mon, RecoveryLadder(**ladder_kwargs), repeat_threshold=3, progress_window=4
        )

    def loop_obs(i: int) -> Observation:
        return Observation(action="click", state=f"state-{i}", progress=f"prog-{i}")

    def loop_walks_the_ladder() -> None:
        clock = Clock()
        sup = supervisor(clock, retry=lambda f: True)
        sup.monitor.beat(MonitoredComponent.AGENT)
        assert sup.poll({MonitoredComponent.AGENT: loop_obs(1)}).findings == ()
        assert sup.poll({MonitoredComponent.AGENT: loop_obs(2)}).findings == ()
        report = sup.poll({MonitoredComponent.AGENT: loop_obs(3)})
        (finding,) = report.findings
        assert finding.signal is StallSignal.SAME_ACTION
        (outcome,) = report.outcomes
        assert outcome.resolution is RecoveryResolution.RESOLVED
        assert sup.detector(MonitoredComponent.AGENT).depth == 0  # reset on resolve
        late = sup.poll({MonitoredComponent.AGENT: loop_obs(4)})
        hb = late.health.component(MonitoredComponent.AGENT)
        assert hb is not None and hb.status is ComponentStatus.STALLED

    def silence_becomes_a_finding() -> None:
        clock = Clock()
        sup = supervisor(clock, retry=lambda f: True)
        sup.monitor.beat(MonitoredComponent.BROWSER)
        clock.advance(31.0)
        report = sup.poll()
        silent = [
            f for f in report.findings if f.component is MonitoredComponent.BROWSER
        ]
        assert silent and silent[0].signal is StallSignal.NO_PROGRESS
        assert "التوقف الصامت" in silent[0].detail
        again = sup.poll()
        assert not [
            f for f in again.findings if f.component is MonitoredComponent.BROWSER
        ]

    def real_checkpoints_before_rungs() -> None:
        from nexus.recovery import (
            CheckpointManager,
            DiskCheckpointStore,
            TriggerEvent,
            TriggerPolicy,
        )

        base = Path(tempfile.mkdtemp(prefix="p23-gate-22-"))
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), base / "repo",
            version="0.23.0", phase=23,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )

        def announce(rung: str, finding) -> None:  # noqa: ANN001, ANN202
            made = manager.on_event(
                TriggerEvent.BEFORE_RISKY_CHANGE, label=f"§23.3 {rung}"
            )
            assert made is not None

        clock = Clock()
        sup = supervisor(
            clock, retry=lambda f: False, alternate=lambda f: True,
            before_rung=announce,
        )
        sup.monitor.beat(MonitoredComponent.TOOL)
        for i in range(3):
            sup.poll({MonitoredComponent.TOOL: loop_obs(i)})
        triggers = [m.trigger.value for m in manager.store.list()]
        assert triggers.count("before_risky_change") == 2, triggers

    check("E1 · a confirmed loop walks the ladder and marks STALLED", loop_walks_the_ladder)
    check("E2 · §23.1 silence becomes a no_progress finding",
          silence_becomes_a_finding)
    check("E3 · the §22 law — real BEFORE_RISKY_CHANGE checkpoints", real_checkpoints_before_rungs)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 23, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 23), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "health"
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

        for phase in (15, 16, 17, 18, 19, 20, 21, 22):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 23 and nexus-core ≥ 0.23.0", identity)
    check("F2 · the health core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–22 stay green", regression)


# ----------------------------------------------------------------------- main

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 23 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 23 — Heartbeat + Health — Exit Gate")
    for section, title in (
        (section_a, "A · Contracts & vocabulary (§23.1–§23.3)"),
        (section_b, "B · Heartbeat (§23.1)"),
        (section_c, "C · Stall Detection (§23.2)"),
        (section_d, "D · Recovery ladder (§23.3)"),
        (section_e, "E · Supervisor + the §22 law"),
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
