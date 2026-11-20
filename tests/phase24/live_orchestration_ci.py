#!/usr/bin/env python3
"""PHASE 24 live orchestration proof — real threads, real walls, real waves.

Eleven rungs, each printed as [PASS]/[FAIL] with its observation (the
§20 evidence law applied to §24):

  1. §24 vocabulary verbatim — thirteen roles · five ownership fields
     · three parallelism gates · two agent kinds.
  2. §24.1 — a specialist's attempt at the user channel is refused by
     identity; the master's own voice passes and is on the transcript.
  3. §24.2 — the thirteen build on the real §6.4 registry: master as
     root, every specialist a leaf whose parent is the master,
     deterministic ids.
  4. §24.3 — two genuinely independent requests run PARALLEL on real
     threads and meet at a threading.Barrier (a sequential runner
     would deadlock the barrier — meeting is the proof).
  5. §24.3 — a shared file forces SEQUENTIAL and the strict order
     holds (wave 1 ends before wave 2 starts).
  6. §24.3 — resources_available: a third-party holder denies
     parallelism with the holder named; a both-claim denial too.
  7. §24.4 — a request outside the specialist's scope is refused
     before any work happens (the §24.4 detail on the result).
  8. §24.4 — §6.6 coordination: a pre-held resource surfaces as an
     honest failed result naming the holder; the holder keeps it.
  9. Integration — §23 rides along: agent and task components beat
     through a real orchestration (seq grows, nobody goes silent).
 10. Integration — §6.1/§6.4: every specialist IS a persisted Agent
     record; a fresh registry over the same data dir finds the roster.
 11. Identity — NEXUS_PHASE ≥ 24 and nexus-core ≥ 0.24.0.

Run (CI/sandbox):  python tests/phase24/live_orchestration_ci.py
Run (device, via pytest): tests/phase24/test_device_proof.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus.agents import (  # noqa: E402
    AGENT_FIELDS,
    MASTER_AGENT_ID,
    AgentRegistry,
    OwnershipManager,
)
from nexus.health import HeartbeatMonitor  # noqa: E402
from nexus.orchestration import (  # noqa: E402
    AGENT_KINDS,
    OWNERSHIP_FIELDS,
    PARALLELISM_GATES,
    SPECIALIST_ROLES,
    AgentResult,
    DispatchRequest,
    MasterOnlyChannelError,
    MasterOrchestrator,
    ParallelismGate,
    SpecialistTeam,
    specialist_agent_id,
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


def fresh_team(
    task: str = "live proof",
) -> tuple[SpecialistTeam, AgentRegistry, OwnershipManager, str]:
    base = Path(tempfile.mkdtemp(prefix="p24-live-"))
    registry = AgentRegistry(base / "data")
    ownership = OwnershipManager()
    team = SpecialistTeam.build(registry, task)
    return team, registry, ownership, str(base)


# ------------------------------------------------------------------- rungs


def rung_1_vocabulary() -> str:
    assert SPECIALIST_ROLES == (
        "planner", "researcher", "architect", "coder", "browser",
        "computer", "tester", "debugger", "security", "reviewer",
        "git", "recovery", "learning",
    )
    assert OWNERSHIP_FIELDS == (
        "task", "scope", "parent", "children", "owned_resources",
    )
    assert PARALLELISM_GATES == (
        "tasks_independent", "files_independent", "resources_available",
    )
    assert AGENT_KINDS == ("master", "specialist")
    return "roles 13 · ownership 5 · gates 3 · kinds 2 — verbatim"


def rung_2_user_channel_law() -> str:
    team, *_ = fresh_team()
    try:
        team.get("coder").try_user_channel("hello, user — from the coder")
    except MasterOnlyChannelError as exc:
        assert "§24.1" in str(exc)
        assert len(team.channel) == 0  # nothing reached the user
    else:
        raise AssertionError("the specialist walked through the wall")
    team.channel.write(MASTER_AGENT_ID, "goal accepted — three waves planned")
    transcript = team.channel.transcript()
    assert len(transcript) == 1 and transcript[0]["from"] == MASTER_AGENT_ID
    return "specialist refused · master's voice on the transcript"


def rung_3_team_on_the_registry() -> str:
    team, registry, _, _ = fresh_team()
    assert len(team) == 13
    assert [s.role for s in team.roster] == list(SPECIALIST_ROLES)
    assert registry.has(MASTER_AGENT_ID)
    for specialist in team.roster:
        assert registry.has(specialist.agent_id)
        assert specialist.ownership.parent == MASTER_AGENT_ID
        assert specialist.ownership.children == ()
        assert specialist.ownership.task == "live proof"
    assert team.master_ownership.children == tuple(
        specialist_agent_id(r) for r in SPECIALIST_ROLES
    )
    assert team.get("git").agent_id == "ag_spec_git"
    return "13/13 registered · master root · ids deterministic"


def rung_4_real_parallel_barrier() -> str:
    team, registry, ownership, _ = fresh_team()
    orch = MasterOrchestrator(team, registry, ownership)
    barrier = threading.Barrier(2, timeout=10.0)

    def meet(request: DispatchRequest) -> AgentResult:
        arrived = barrier.wait()
        return AgentResult(
            request_id=request.request_id,
            agent_id=team.get(request.role).agent_id,
            role=request.role, ok=True,
            detail=f"met at the barrier (index {arrived})",
        )

    team.get("coder").bind_handler(meet)
    team.get("tester").bind_handler(meet)
    report = orch.submit_user_goal(
        "prove side-by-side",
        [
            DispatchRequest(request_id="m1", task_id="t1", role="coder"),
            DispatchRequest(request_id="m2", task_id="t2", role="tester"),
        ],
    )
    assert report.ok, report.field_notes
    assert report.wave_count == 1
    assert all(o.ran_parallel for o in report.outcomes)
    return "two real threads met at the barrier — parallelism proven"


def rung_5_shared_file_forces_order() -> str:
    team, registry, ownership, _ = fresh_team()
    # both specialists scoped to the same work dir — only the §24.3
    # file gate should split them (the §24.4 scope must not interfere)
    team2 = SpecialistTeam.build(
        registry, "live proof",
        scopes={"coder": ("work/",), "tester": ("work/",)},
    )
    assert team2.get("coder").ownership.scope == ("work/",)
    _ = team
    orch = MasterOrchestrator(team2, registry, ownership)
    order: list[str] = []
    lock = threading.Lock()

    def work(request: DispatchRequest) -> AgentResult:
        with lock:
            order.append(f"start:{request.request_id}")
            time.sleep(0.05)
            order.append(f"end:{request.request_id}")
        return AgentResult(
            request_id=request.request_id, agent_id="x", role=request.role,
            ok=True, detail="ok",
        )

    team2.get("coder").bind_handler(work)
    team2.get("tester").bind_handler(work)
    report = orch.submit_user_goal(
        "one file, two claimants",
        [
            DispatchRequest(request_id="s1", task_id="t1", role="coder",
                            files=("work/f.py",)),
            DispatchRequest(request_id="s2", task_id="t2", role="tester",
                            files=("work/f.py",)),
        ],
    )
    assert report.ok, report.field_notes
    assert report.wave_count == 2
    assert all(not o.ran_parallel for o in report.outcomes)
    assert order.index("end:s1") < order.index("start:s2")
    return f"waves 2 · strict order held ({' → '.join(order)})"


def rung_6_resources_gate() -> str:
    team, registry, ownership, _ = fresh_team()
    gate = ParallelismGate(ownership)
    ownership.acquire("printer", owner="an-earlier-holder")
    a = DispatchRequest(request_id="a", task_id="t1", role="coder",
                        resources=("printer",))
    b = DispatchRequest(request_id="b", task_id="t2", role="tester",
                        resources=("camera",))
    verdict = gate.decide(a, b)
    assert not verdict.allowed
    assert "an-earlier-holder" in verdict.reasons[0]
    both = gate.decide(
        DispatchRequest(request_id="c", task_id="t3", role="coder",
                        resources=("db",)),
        DispatchRequest(request_id="d", task_id="t4", role="tester",
                        resources=("db",)),
    )
    assert not both.allowed
    (res_gate,) = [g for g in both.gates if g.gate == "resources_available"]
    assert "db" in res_gate.detail
    return "third-party holder named · both-claim refused"


def rung_7_scope_violation_refused() -> str:
    team, registry, ownership, _ = fresh_team()
    orch = MasterOrchestrator(team, registry, ownership)
    report = orch.submit_user_goal(
        "touch what is not ours",
        [DispatchRequest(request_id="v1", task_id="t1", role="tester",
                         files=("nexus/agents/agent.py",))],
    )
    (outcome,) = report.outcomes
    assert not outcome.result.ok
    assert "§24.4" in outcome.result.detail
    assert "tests/" in outcome.result.detail  # the actual scope, named
    return "refused before any work — scope named on the result"


def rung_8_ownership_coordination() -> str:
    team, registry, ownership, _ = fresh_team()
    ownership.acquire("printer", owner="the-previous-holder")
    orch = MasterOrchestrator(team, registry, ownership)
    report = orch.submit_user_goal(
        "print anyway",
        [DispatchRequest(request_id="p1", task_id="t1", role="coder",
                         resources=("printer",))],
    )
    (outcome,) = report.outcomes
    assert not outcome.result.ok
    assert "ownership conflict" in outcome.result.detail
    assert "the-previous-holder" in outcome.result.detail
    assert ownership.owner_of("printer") == "the-previous-holder"
    return "conflict surfaced as a result — the holder keeps the printer"


def rung_9_heartbeat_rides_along() -> str:
    team, registry, ownership, _ = fresh_team()
    monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
    for name in monitor.watched:
        monitor.beat(name)  # the boot beat
    orch = MasterOrchestrator(team, registry, ownership, heartbeat=monitor)

    def done(request: DispatchRequest) -> AgentResult:
        return AgentResult(
            request_id=request.request_id,
            agent_id=team.get(request.role).agent_id,
            role=request.role, ok=True, detail="done",
        )

    team.get("coder").bind_handler(done)
    team.get("tester").bind_handler(done)
    report = orch.submit_user_goal(
        "stay observed",
        [
            DispatchRequest(request_id="h1", task_id="t1", role="coder"),
            DispatchRequest(request_id="h2", task_id="t2", role="tester"),
        ],
    )
    assert report.ok, report.field_notes
    assert monitor.check("agent").seq > 1
    assert monitor.check("task").seq > 1
    return (
        f"agent seq={monitor.check('agent').seq} ·"
        f" task seq={monitor.check('task').seq}"
    )


def rung_10_records_persist() -> str:
    team, registry, _, base = fresh_team()
    data_dir = Path(base) / "data"
    # a fresh registry over the same data dir finds the whole roster
    rebooted = AgentRegistry(data_dir)
    assert rebooted.has(MASTER_AGENT_ID)
    found = sum(1 for s in team.roster if rebooted.has(s.agent_id))
    assert found == 13, f"only {found}/13 survived the reboot"
    record = rebooted.get("ag_spec_coder")
    assert record.role == "coder"
    assert record.instructions.strip()
    assert set(AGENT_FIELDS) == {
        "id", "role", "instructions", "capabilities", "tools",
        "memory_policy", "model_policy", "verification",
    }
    return "13/13 records persisted — the roster survives a reboot"


def rung_11_identity() -> str:
    import nexus

    assert nexus.NEXUS_PHASE >= 24, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
    major, minor, _ = (int(p) for p in nexus.__version__.split("."))
    assert (major, minor) >= (0, 24), f"version {nexus.__version__}"
    return f"nexus {nexus.__version__} · phase {nexus.NEXUS_PHASE}"


# -------------------------------------------------------------------- main


def main() -> int:
    rungs = (
        ("1 · §24 vocabulary verbatim", rung_1_vocabulary),
        ("2 · §24.1 the user channel walls out specialists", rung_2_user_channel_law),
        ("3 · §24.2 the thirteen on the real registry", rung_3_team_on_the_registry),
        ("4 · §24.3 real parallel threads meet at a barrier", rung_4_real_parallel_barrier),
        ("5 · §24.3 a shared file forces sequential order", rung_5_shared_file_forces_order),
        ("6 · §24.3 resources_available denies with reasons", rung_6_resources_gate),
        ("7 · §24.4 scope violation refused before work", rung_7_scope_violation_refused),
        ("8 · §24.4 §6.6 coordination, never an overwrite", rung_8_ownership_coordination),
        ("9 · integration — §23 heartbeat rides along", rung_9_heartbeat_rides_along),
        ("10 · integration — §6.1/§6.4 records persist", rung_10_records_persist),
        ("11 · identity — phase ≥ 24 · core ≥ 0.24.0", rung_11_identity),
    )
    for label, fn in rungs:
        rung(label, fn)

    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    print(f"\nPROOF: {passed}/{len(RESULTS)} rungs passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
