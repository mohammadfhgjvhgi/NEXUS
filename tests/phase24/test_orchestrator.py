"""Phase 24 orchestrator — the §24.1 law, real waves, §6.6 coordination."""

from __future__ import annotations

import threading
import time

import pytest

from nexus.agents import MASTER_AGENT_ID
from nexus.orchestration import (
    AgentResult,
    DispatchRequest,
    MasterOnlyChannelError,
    MasterOrchestrator,
    OrchestrationError,
    OrchestrationReport,
    SpecialistTeam,
)


def make_orch(registry, ownership, team=None, **kwargs) -> MasterOrchestrator:
    if team is None:
        team = SpecialistTeam.build(registry, "orch task")
    return MasterOrchestrator(team, registry, ownership, **kwargs)


def test_empty_goal_refused(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    with pytest.raises(OrchestrationError):
        orch.submit_user_goal("   ", [])


def test_independent_handlers_run_parallel_and_succeed(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    team = orch.team

    def handler(request: DispatchRequest) -> AgentResult:
        return AgentResult(
            request_id=request.request_id,
            agent_id=team.get(request.role).agent_id,
            role=request.role,
            ok=True,
            detail=f"done: {request.payload}",
        )

    for role in ("planner", "researcher", "coder", "tester"):
        team.get(role).bind_handler(handler)

    report = orch.submit_user_goal(
        "ship the feature",
        [
            DispatchRequest(request_id="r1", task_id="t1", role="planner", payload="plan"),
            DispatchRequest(request_id="r2", task_id="t2", role="coder", payload="code"),
            DispatchRequest(request_id="r3", task_id="t3", role="tester", payload="test"),
        ],
    )
    assert report.ok
    assert report.wave_count == 1
    assert all(o.ran_parallel for o in report.outcomes)
    assert report.user_delivered
    assert report.master_id == MASTER_AGENT_ID


def test_real_concurrency_proven_with_a_barrier(registry, ownership) -> None:
    """Two handlers meet at a threading.Barrier — only real side-by-side
    execution lets both through (a sequential runner would time out)."""
    orch = make_orch(registry, ownership)
    team = orch.team
    barrier = threading.Barrier(2, timeout=5.0)

    def meeting(request: DispatchRequest) -> AgentResult:
        arrived = barrier.wait()
        return AgentResult(
            request_id=request.request_id,
            agent_id=team.get(request.role).agent_id,
            role=request.role,
            ok=True,
            detail=f"met at the barrier (index {arrived})",
        )

    team.get("coder").bind_handler(meeting)
    team.get("tester").bind_handler(meeting)

    report = orch.submit_user_goal(
        "meet in the middle",
        [
            DispatchRequest(request_id="m1", task_id="t1", role="coder"),
            DispatchRequest(request_id="m2", task_id="t2", role="tester"),
        ],
    )
    assert report.ok, report.field_notes
    assert all("met at the barrier" in o.result.detail for o in report.outcomes)


def test_sequential_when_gates_deny_and_order_holds(registry, ownership) -> None:
    # two specialists, both scoped to the same work dir — the shared
    # file is inside BOTH scopes, so only the §24.3 gate splits them
    team = SpecialistTeam.build(
        registry, "sequential task",
        scopes={"coder": ("work/",), "tester": ("work/",)},
    )
    orch = make_orch(registry, ownership, team=team)
    order: list[str] = []
    lock = threading.Lock()

    def handler(request: DispatchRequest) -> AgentResult:
        with lock:
            order.append(f"start:{request.request_id}")
            time.sleep(0.05)
            order.append(f"end:{request.request_id}")
        return AgentResult(
            request_id=request.request_id, agent_id="x", role=request.role,
            ok=True, detail="ok",
        )

    team.get("coder").bind_handler(handler)
    team.get("tester").bind_handler(handler)

    report = orch.submit_user_goal(
        "one file, two claimants",
        [
            DispatchRequest(request_id="s1", task_id="t1", role="coder", files=("work/f.py",)),
            DispatchRequest(request_id="s2", task_id="t2", role="tester", files=("work/f.py",)),
        ],
    )
    assert report.ok
    assert report.wave_count == 2  # the shared file split them
    assert all(not o.ran_parallel for o in report.outcomes)
    assert order.index("end:s1") < order.index("start:s2")  # strictly ordered


def test_ownership_conflict_is_a_result_not_an_overwrite(registry, ownership) -> None:
    ownership.acquire("printer", owner="the-previous-holder")
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "print something",
        [DispatchRequest(request_id="p1", task_id="t1", role="coder", resources=("printer",))],
    )
    (outcome,) = report.outcomes
    assert not outcome.result.ok
    assert "ownership conflict" in outcome.result.detail
    assert "the-previous-holder" in outcome.result.detail
    # the honest world: the earlier holder still owns the printer
    assert ownership.owner_of("printer") == "the-previous-holder"


def test_resources_are_released_after_the_wave(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "hold and let go",
        [DispatchRequest(request_id="h1", task_id="t1", role="coder", resources=("camera",))],
    )
    (outcome,) = report.outcomes
    assert outcome.result.ok is False  # no handler bound — but the claim was honored
    assert ownership.owner_of("camera") is None  # and returned afterwards


def test_scope_violation_surfaces_honestly(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "touch what is not ours",
        [DispatchRequest(request_id="v1", task_id="t1", role="tester",
                         files=("nexus/agents/agent.py",))],
    )
    (outcome,) = report.outcomes
    assert not outcome.result.ok
    assert "§24.4" in outcome.result.detail


def test_unhandled_role_is_honest(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "nobody home",
        [DispatchRequest(request_id="n1", task_id="t1", role="learning")],
    )
    (outcome,) = report.outcomes
    assert not outcome.result.ok
    assert "no handler bound" in outcome.result.detail


def test_user_channel_law_holds_through_the_orchestrator(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    with pytest.raises(MasterOnlyChannelError):
        orch.team.get("reviewer").try_user_channel("bypass the master")
    # and the master's own voice still works
    orch.channel.write(MASTER_AGENT_ID, "status: all clear")
    assert orch.channel.transcript()[-1]["from"] == MASTER_AGENT_ID


def test_heartbeat_rides_along(registry, ownership) -> None:
    from nexus.health import HeartbeatMonitor

    monitor = HeartbeatMonitor(fresh_after_seconds=30.0, stale_after_seconds=90.0)
    for name in monitor.watched:
        monitor.beat(name)  # the boot beat
    orch = make_orch(registry, ownership, heartbeat=monitor)
    orch.submit_user_goal(
        "stay observed",
        [
            DispatchRequest(request_id="h1", task_id="t1", role="coder"),
            DispatchRequest(request_id="h2", task_id="t2", role="tester"),
        ],
    )
    agent_seq = monitor.check("agent").seq
    task_seq = monitor.check("task").seq
    assert agent_seq > 1  # every dispatch beat the agent component
    assert task_seq > 1  # the completed wave beat the task component


def test_summary_tells_the_truth(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "say it plainly",
        [DispatchRequest(request_id="z1", task_id="t1", role="coder")],
    )
    assert "0/1" in report.summary  # no handler — the summary does not lie
    assert "1 wave" in report.summary
    assert report.field_notes  # the failure is on the record


def test_report_roundtrips(registry, ownership) -> None:
    orch = make_orch(registry, ownership)
    report = orch.submit_user_goal(
        "round trip",
        [DispatchRequest(request_id="rt1", task_id="t1", role="coder")],
    )
    assert OrchestrationReport.from_dict(report.as_dict()) == report
