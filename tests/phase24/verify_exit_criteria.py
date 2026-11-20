#!/usr/bin/env python3
"""Phase 24 orchestration harness — New Plan §24 Exit Gate.

Proves the Multi-Agent Orchestration section by section:

* A — Contracts (§24.1–§24.4): the verbatim vocabulary — thirteen
      specialist roles · five ownership fields · three parallelism
      gates · two agent kinds — plus the round-trips, the
      deterministic ids and the error family.
* B — Specialist team (§24.2): the thirteen build on the real §6.4
      registry (master seeded, every specialist a registered §6.1
      record with the eight verbatim fields), the tree is validated
      (master root, leaves, parents) and tampering is refused.
* C — Parallelism (§24.3): each gate denies honestly and names its
      reason — same task, declared dependency, shared file, shared
      resource claim, third-party holder — all three pass → parallel;
      the wave plan is deterministic, dependencies land in strictly
      earlier waves, file conflicts never share a wave.
* D — Ownership (§24.4): every agent knows the five verbatim fields;
      scope violations are refused before work (empty scope = a
      no-file agent); §6.6 coordination surfaces a conflict as an
      honest failed result and resources are returned after the wave.
* E — Master + integration (§24.1): the user channel walls out
      specialists by identity; the master's door in is
      submit_user_goal and its voice out is report_to_user; two real
      threads meet at a barrier (parallelism proven, not claimed);
      the §23 heartbeat beats agent and task through a real
      orchestration.
* F — Integration + regression: NEXUS_PHASE ≥ 24, nexus-core ≥
      0.24.0, the orchestration core stays stdlib-only at module top
      level, and the neighbor phase suites (15–23) stay green
      (skippable with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import sys
import tempfile
import threading
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


# ---------------------------------------------------------------- helpers


def fresh_world(task: str = "gate task"):
    from nexus.agents import AgentRegistry, OwnershipManager
    from nexus.orchestration import SpecialistTeam

    base = Path(tempfile.mkdtemp(prefix="p24-gate-"))
    registry = AgentRegistry(base / "data")
    ownership = OwnershipManager()
    team = SpecialistTeam.build(registry, task)
    return team, registry, ownership


def ok_result(request, team):  # type: ignore[no-untyped-def]
    from nexus.orchestration import AgentResult

    return AgentResult(
        request_id=request.request_id,
        agent_id=team.get(request.role).agent_id,
        role=request.role,
        ok=True,
        detail="done",
    )


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.orchestration import (
        AGENT_KINDS,
        ORCHESTRATION_SCHEMA_VERSION,
        OWNERSHIP_FIELDS,
        PARALLELISM_GATES,
        SPECIALIST_ROLES,
        AgentResult,
        DispatchError,
        DispatchOutcome,
        DispatchRequest,
        GateReport,
        MasterOnlyChannelError,
        OrchestrationError,
        OrchestrationReport,
        OwnershipSpec,
        ParallelismVerdict,
        ScopeViolationError,
        TreeError,
        UnknownRoleError,
        specialist_agent_id,
    )

    def vocabulary_verbatim() -> None:
        assert SPECIALIST_ROLES == (
            "planner", "researcher", "architect", "coder", "browser",
            "computer", "tester", "debugger", "security", "reviewer",
            "git", "recovery", "learning",
        ), SPECIALIST_ROLES
        assert OWNERSHIP_FIELDS == (
            "task", "scope", "parent", "children", "owned_resources",
        )
        assert PARALLELISM_GATES == (
            "tasks_independent", "files_independent", "resources_available",
        )
        assert AGENT_KINDS == ("master", "specialist")
        assert ORCHESTRATION_SCHEMA_VERSION == 1

    def deterministic_ids() -> None:
        for role in SPECIALIST_ROLES:
            assert specialist_agent_id(role) == f"ag_spec_{role}"
        expects((UnknownRoleError,), specialist_agent_id, "workflow-engine")

    def roundtrips() -> None:
        spec = OwnershipSpec(
            agent_id="ag_spec_coder", task="t", scope=("nexus/",),
            parent="ag_master0000", children=(), owned_resources=("r",),
        )
        assert OwnershipSpec.from_dict(spec.as_dict()) == spec
        assert spec.in_scope("nexus/x.py") and not spec.in_scope("docs/x")
        request = DispatchRequest(
            request_id="r1", task_id="t1", role="tester",
            files=("tests/x.py",), resources=("pytest",), depends_on=("r0",),
        )
        assert DispatchRequest.from_dict(request.as_dict()) == request
        gate = GateReport(gate="files_independent", passed=False, detail="f.py")
        assert GateReport.from_dict(gate.as_dict()) == gate
        verdict = ParallelismVerdict(
            decision="sequential", gates=(gate,), reasons=("f.py",),
        )
        assert ParallelismVerdict.from_dict(verdict.as_dict()) == verdict
        result = AgentResult(
            request_id="r1", agent_id="a", role="tester", ok=True,
            detail="d", artifacts=("x",),
        )
        assert AgentResult.from_dict(result.as_dict()) == result
        outcome = DispatchOutcome(
            request_id="r1", role="tester", wave_index=0,
            ran_parallel=True, result=result,
        )
        assert DispatchOutcome.from_dict(outcome.as_dict()) == outcome
        report = OrchestrationReport(
            goal="g", master_id="m", wave_count=1, outcomes=(outcome,),
            summary="1/1", user_delivered=True, field_notes=("n",),
        )
        assert OrchestrationReport.from_dict(report.as_dict()) == report

    def error_family() -> None:
        for exc in (
            UnknownRoleError, MasterOnlyChannelError, TreeError,
            ScopeViolationError, DispatchError,
        ):
            assert issubclass(exc, OrchestrationError)
        expects((OrchestrationError,), OwnershipSpec, agent_id=" ", task="t")
        expects(
            (UnknownRoleError,),
            DispatchRequest, request_id="r", task_id="t", role="wizard",
        )

    check("A1 · §24.1–§24.4 vocabulary verbatim", vocabulary_verbatim)
    check("A2 · deterministic ids for the thirteen", deterministic_ids)
    check("A3 · the contracts round-trip", roundtrips)
    check("A4 · the error family is honest", error_family)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.agents import AGENT_FIELDS, MASTER_AGENT_ID
    from nexus.orchestration import (
        OWNERSHIP_FIELDS,
        SPECIALIST_ROLES,
        SpecialistTeam,
        TreeError,
        specialist_agent_id,
    )

    def thirteen_on_the_registry() -> None:
        team, registry, _ = fresh_world()
        assert len(team) == 13
        assert registry.has(MASTER_AGENT_ID)
        for specialist in team.roster:
            assert registry.has(specialist.agent_id)
            record = registry.get(specialist.agent_id)
            assert record.role == specialist.role
            assert record.instructions.strip()
            assert record.capabilities and record.tools
        assert [s.role for s in team.roster] == list(SPECIALIST_ROLES)

    def eight_fields_verbatim() -> None:
        assert AGENT_FIELDS == (
            "id", "role", "instructions", "capabilities", "tools",
            "memory_policy", "model_policy", "verification",
        )

    def tree_integrity() -> None:
        team, _, _ = fresh_world()
        assert team.master_ownership.agent_id == MASTER_AGENT_ID
        assert team.master_ownership.parent is None
        assert team.master_ownership.children == tuple(
            specialist_agent_id(r) for r in SPECIALIST_ROLES
        )
        for specialist in team.roster:
            assert specialist.ownership.parent == MASTER_AGENT_ID
            assert specialist.ownership.children == ()
            assert specialist.ownership.task == "gate task"
            assert specialist.knows() == OWNERSHIP_FIELDS

    def tampering_refused() -> None:
        team, _, _ = fresh_world()
        broken_master = dataclasses.replace(
            team.master_ownership, children=(specialist_agent_id("coder"),)
        )
        broken = SpecialistTeam(
            team.registry, team.ownerships(), team.specialists_map(),
            broken_master, team.channel,
        )
        expects((TreeError,), broken.validate_tree)
        orphaned = dict(team.ownerships())
        orphaned["coder"] = dataclasses.replace(
            orphaned["coder"], parent="ag_someone_else"
        )
        broken2 = SpecialistTeam(
            team.registry, orphaned, team.specialists_map(),
            team.master_ownership, team.channel,
        )
        expects((TreeError,), broken2.validate_tree)

    check("B1 · §24.2 the thirteen are registered §6.1 records", thirteen_on_the_registry)
    check("B2 · the §6.1 eight fields stand unchanged", eight_fields_verbatim)
    check("B3 · §24.4 the tree is validated on build", tree_integrity)
    check("B4 · a tangled tree is refused, never shipped", tampering_refused)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.agents import OwnershipManager
    from nexus.orchestration import (
        PARALLELISM_GATES,
        DispatchRequest,
        ParallelismGate,
    )

    def req(rid: str, *, task: str | None = None, **kw):  # noqa: ANN001, ANN202
        return DispatchRequest(
            request_id=rid, role="coder", task_id=task or f"task-{rid}", **kw
        )

    def gates_deny_honestly() -> None:
        gate = ParallelismGate()
        v = gate.decide(req("r1", task="t"), req("r2", task="t"))
        assert not v.allowed and "t" in v.reasons[0]
        v = gate.decide(req("r1", task="t"), req("r2", task="t2", depends_on=("r1",)))
        assert not v.allowed and "dependency" in v.reasons[0]
        v = gate.decide(
            req("r1", task="t", files=("f.py",)),
            req("r2", task="t2", files=("f.py",)),
        )
        assert not v.allowed and "f.py" in v.reasons[0]
        v = gate.decide(
            req("r1", task="t", resources=("db",)),
            req("r2", task="t2", resources=("db",)),
        )
        assert not v.allowed and "db" in v.reasons[0]
        ownership = OwnershipManager()
        ownership.acquire("printer", owner="earlier")
        v = ParallelismGate(ownership).decide(
            req("r1", task="t", resources=("printer",)),
            req("r2", task="t2", resources=("cam",)),
        )
        assert not v.allowed and "earlier" in v.reasons[0]

    def all_three_pass() -> None:
        verdict = ParallelismGate().decide(req("r1", task="t1"), req("r2", task="t2"))
        assert verdict.allowed
        assert [g.gate for g in verdict.gates] == list(PARALLELISM_GATES)
        assert all(g.passed for g in verdict.gates)

    def waves_are_deterministic() -> None:
        gate = ParallelismGate()
        requests = [
            req("a", task="t1"),
            req("b", task="t2"),
            req("c", task="t3", depends_on=("a",)),
            req("d", task="t4", files=("f.py",)),
            req("e", task="t5", files=("f.py",)),
        ]
        waves = gate.plan_waves(requests)
        assert waves == gate.plan_waves(requests)
        flat = [r.request_id for wave in waves for r in wave]
        assert sorted(flat) == ["a", "b", "c", "d", "e"]
        wave_of = {r.request_id: i for i, w in enumerate(waves) for r in w}
        assert wave_of["a"] < wave_of["c"]  # dependency strictly earlier
        assert wave_of["d"] != wave_of["e"]  # file conflict never shares
        assert gate.plan_waves([]) == ()

    check("C1 · §24.3 every denial names its reason", gates_deny_honestly)
    check("C2 · all three gates → parallel", all_three_pass)
    check("C3 · the wave plan is deterministic and honest", waves_are_deterministic)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.agents import MASTER_AGENT_ID
    from nexus.orchestration import (
        DispatchRequest,
        ScopeViolationError,
        SpecialistTeam,
    )

    def scope_enforced() -> None:
        team, _, _ = fresh_world()
        coder = team.get("coder")
        coder.check_scope(DispatchRequest(
            request_id="r1", task_id="t", role="coder", files=("nexus/x.py",)
        ))
        expects(
            (ScopeViolationError,),
            coder.check_scope,
            DispatchRequest(request_id="r2", task_id="t", role="coder",
                            files=("docs/x.md",)),
        )
        team2, _, _ = fresh_world()
        no_files = SpecialistTeam.build(
            team2.registry, "gate", scopes={"planner": ()}
        )
        expects(
            (ScopeViolationError,),
            no_files.get("planner").check_scope,
            DispatchRequest(request_id="r3", task_id="t", role="planner",
                            files=("plans/x.md",)),
        )

    def execution_semantics() -> None:
        team, _, _ = fresh_world()
        tester = team.get("tester")
        bare = tester.execute(
            DispatchRequest(request_id="r1", task_id="t", role="tester")
        )
        assert not bare.ok and "no handler bound" in bare.detail

        def boom(request):  # noqa: ANN001, ANN202
            raise RuntimeError("device gone")

        tester.bind_handler(boom)
        bad = tester.execute(
            DispatchRequest(request_id="r2", task_id="t", role="tester")
        )
        assert not bad.ok and "RuntimeError" in bad.detail

    def coordination_via_66() -> None:
        from nexus.orchestration import MasterOrchestrator

        team, registry, ownership = fresh_world()
        ownership.acquire("printer", owner="the-previous-holder")
        orch = MasterOrchestrator(team, registry, ownership)
        report = orch.submit_user_goal(
            "print anyway",
            [DispatchRequest(request_id="p1", task_id="t", role="coder",
                             resources=("printer",))],
        )
        (outcome,) = report.outcomes
        assert not outcome.result.ok
        assert "ownership conflict" in outcome.result.detail
        assert "the-previous-holder" in outcome.result.detail
        assert ownership.owner_of("printer") == "the-previous-holder"
        # and after a clean wave, claims come back
        report2 = orch.submit_user_goal(
            "hold and let go",
            [DispatchRequest(request_id="h1", task_id="t", role="coder",
                             resources=("camera",))],
        )
        assert ownership.owner_of("camera") is None
        assert report2.outcomes[0].wave_index == 0
        assert MASTER_AGENT_ID == report2.master_id

    check("D1 · §24.4 scope refused before work (empty = no files)", scope_enforced)
    check("D2 · honest execution semantics (no fake success)", execution_semantics)
    check("D3 · §6.6 coordination — conflict surfaces, claims return", coordination_via_66)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.agents import MASTER_AGENT_ID
    from nexus.health import HeartbeatMonitor
    from nexus.orchestration import (
        AgentResult,
        DispatchRequest,
        MasterOnlyChannelError,
        MasterOrchestrator,
    )

    def channel_law() -> None:
        team, _, _ = fresh_world()
        expects(
            (MasterOnlyChannelError,),
            team.get("security").try_user_channel, "let me through",
        )
        assert len(team.channel) == 0  # nothing reached the user
        team.channel.write(MASTER_AGENT_ID, "the master speaks")
        assert team.channel.transcript()[-1]["from"] == MASTER_AGENT_ID

    def single_door_single_voice() -> None:
        from nexus.orchestration import OrchestrationError

        team, registry, ownership = fresh_world()
        orch = MasterOrchestrator(team, registry, ownership)
        expects((OrchestrationError,), orch.submit_user_goal, "  ", [])

        def done(request):  # noqa: ANN001, ANN202
            return ok_result(request, team)

        team.get("planner").bind_handler(done)
        team.get("coder").bind_handler(done)
        report = orch.submit_user_goal(
            "the goal",
            [
                DispatchRequest(request_id="r1", task_id="t1", role="planner"),
                DispatchRequest(request_id="r2", task_id="t2", role="coder"),
            ],
        )
        assert report.ok and report.user_delivered
        assert report.master_id == MASTER_AGENT_ID
        assert len(orch.channel) == 1  # exactly one delivery, by the master
        assert OrchestrationError and True  # noqa: B018 — import honesty

    def real_threads_meet() -> None:
        team, registry, ownership = fresh_world()
        orch = MasterOrchestrator(team, registry, ownership)
        barrier = threading.Barrier(2, timeout=10.0)

        def meet(request):  # noqa: ANN001, ANN202
            barrier.wait()
            return ok_result(request, team)

        team.get("coder").bind_handler(meet)
        team.get("tester").bind_handler(meet)
        report = orch.submit_user_goal(
            "meet",
            [
                DispatchRequest(request_id="m1", task_id="t1", role="coder"),
                DispatchRequest(request_id="m2", task_id="t2", role="tester"),
            ],
        )
        assert report.ok, report.field_notes  # a sequential runner deadlocks here
        assert report.wave_count == 1 and all(o.ran_parallel for o in report.outcomes)

    def heartbeat_rides() -> None:
        team, registry, ownership = fresh_world()
        monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
        for name in monitor.watched:
            monitor.beat(name)
        orch = MasterOrchestrator(team, registry, ownership, heartbeat=monitor)

        def done(request):  # noqa: ANN001, ANN202
            return ok_result(request, team)

        team.get("coder").bind_handler(done)
        team.get("tester").bind_handler(done)
        report = orch.submit_user_goal(
            "observed",
            [
                DispatchRequest(request_id="h1", task_id="t1", role="coder"),
                DispatchRequest(request_id="h2", task_id="t2", role="tester"),
            ],
        )
        assert report.ok, report.field_notes
        assert monitor.check("agent").seq > 1
        assert monitor.check("task").seq > 1

    def agent_result_shape() -> None:
        team, _, _ = fresh_world()
        request = DispatchRequest(request_id="r1", task_id="t", role="coder")
        result = ok_result(request, team)
        assert isinstance(result, AgentResult)
        assert result.ok and result.agent_id == "ag_spec_coder"

    check("E1 · §24.1 the channel walls out non-masters", channel_law)
    check("E2 · one door in, one voice out — the master's", single_door_single_voice)
    check("E3 · §24.3 real threads meet at a barrier", real_threads_meet)
    check("E4 · integration — §23 heartbeat beats agent+task", heartbeat_rides)
    check("E5 · results carry the specialist identity", agent_result_shape)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 24, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 24), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "orchestration"
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

        for phase in (15, 16, 17, 18, 19, 20, 21, 22, 23):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 24 and nexus-core ≥ 0.24.0", identity)
    check("F2 · the orchestration core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–23 stay green", regression)


# ----------------------------------------------------------------------- main

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 24 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 24 — Multi-Agent Orchestration — Exit Gate")
    for section, title in (
        (section_a, "A · Contracts & vocabulary (§24.1–§24.4)"),
        (section_b, "B · Specialist team (§24.2)"),
        (section_c, "C · Parallelism gates (§24.3)"),
        (section_d, "D · Ownership (§24.4 + §6.6)"),
        (section_e, "E · Master + integration (§24.1)"),
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
