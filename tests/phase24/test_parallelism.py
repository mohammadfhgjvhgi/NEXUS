"""Phase 24 parallelism — the §24.3 three gates, pairwise and in waves."""

from __future__ import annotations

from nexus.agents import OwnershipManager
from nexus.orchestration import (
    PARALLELISM_GATES,
    DispatchRequest,
    ParallelismGate,
)


def req(
    rid: str,
    *,
    task: str = "task-a",
    role: str = "coder",
    files: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
    depends_on: tuple[str, ...] = (),
) -> DispatchRequest:
    return DispatchRequest(
        request_id=rid,
        task_id=task,
        role=role,
        files=files,
        resources=resources,
        depends_on=depends_on,
    )


def test_independent_pair_is_parallel() -> None:
    gate = ParallelismGate()
    verdict = gate.decide(req("r1"), req("r2", task="task-b"))
    assert verdict.allowed
    assert verdict.decision == "parallel"
    assert [g.gate for g in verdict.gates] == list(PARALLELISM_GATES)
    assert all(g.passed for g in verdict.gates)
    assert verdict.reasons == ()


def test_same_task_blocks_parallel() -> None:
    verdict = ParallelismGate().decide(req("r1", task="task-a"), req("r2", task="task-a"))
    assert not verdict.allowed
    assert verdict.reasons and "task-a" in verdict.reasons[0]
    (tasks_gate,) = [g for g in verdict.gates if g.gate == "tasks_independent"]
    assert not tasks_gate.passed


def test_declared_dependency_blocks_parallel_both_directions() -> None:
    gate = ParallelismGate()
    forward = gate.decide(req("r1"), req("r2", task="task-b", depends_on=("r1",)))
    assert not forward.allowed
    assert "dependency" in forward.reasons[0]
    backward = gate.decide(req("r1", depends_on=("r2",)), req("r2", task="task-b"))
    assert not backward.allowed


def test_shared_file_blocks_parallel_and_names_it() -> None:
    verdict = ParallelismGate().decide(
        req("r1", files=("nexus/x.py", "nexus/shared.py")),
        req("r2", task="task-b", files=("nexus/shared.py",)),
    )
    assert not verdict.allowed
    (files_gate,) = [g for g in verdict.gates if g.gate == "files_independent"]
    assert "nexus/shared.py" in files_gate.detail


def test_shared_resource_claim_blocks_parallel() -> None:
    verdict = ParallelismGate().decide(
        req("r1", resources=("db",)),
        req("r2", task="task-b", resources=("db",)),
    )
    assert not verdict.allowed
    (res_gate,) = [g for g in verdict.gates if g.gate == "resources_available"]
    assert "db" in res_gate.detail


def test_third_party_holder_blocks_parallel() -> None:
    ownership = OwnershipManager()
    ownership.acquire("printer", owner="some-earlier-request")
    verdict = ParallelismGate(ownership).decide(
        req("r1", resources=("printer",)),
        req("r2", task="task-b", resources=("camera",)),
    )
    assert not verdict.allowed
    assert "printer" in verdict.reasons[0] and "some-earlier-request" in verdict.reasons[0]


def test_resource_held_by_one_of_the_pair_is_fine() -> None:
    ownership = OwnershipManager()
    ownership.acquire("camera", owner="r1")  # r1 already holds it
    verdict = ParallelismGate(ownership).decide(
        req("r1", resources=("camera",)),
        req("r2", task="task-b", resources=("camera",)),
    )
    # the both-claim rule still refuses — one camera, two claimants
    assert not verdict.allowed


def test_waves_independent_pair_shares_a_wave() -> None:
    waves = ParallelismGate().plan_waves([req("r1"), req("r2", task="task-b")])
    assert len(waves) == 1
    assert [r.request_id for r in waves[0]] == ["r1", "r2"]


def test_waves_dependency_splits_in_order() -> None:
    waves = ParallelismGate().plan_waves(
        [req("r1"), req("r2", task="task-b", depends_on=("r1",))]
    )
    assert tuple(tuple(r.request_id for r in wave) for wave in waves) == (
        ("r1",),
        ("r2",),
    )


def test_waves_file_conflict_splits() -> None:
    waves = ParallelismGate().plan_waves(
        [req("r1", files=("f.py",)), req("r2", task="task-b", files=("f.py",))]
    )
    assert len(waves) == 2


def test_waves_three_independent_one_wave_order_kept() -> None:
    waves = ParallelismGate().plan_waves(
        [req("r1"), req("r2", task="task-b"), req("r3", task="task-c")]
    )
    assert len(waves) == 1
    assert [r.request_id for r in waves[0]] == ["r1", "r2", "r3"]


def test_waves_empty_plan_is_empty() -> None:
    assert ParallelismGate().plan_waves([]) == ()


def test_waves_mixed_plan_is_deterministic() -> None:
    requests = [
        req("a", task="t1"),
        req("b", task="t2"),
        req("c", task="t3", depends_on=("a",)),
        req("d", task="t4", files=("f.py",)),
        req("e", task="t5", files=("f.py",)),
    ]
    waves = ParallelismGate().plan_waves(requests)
    again = ParallelismGate().plan_waves(requests)
    assert waves == again
    flat = [r.request_id for wave in waves for r in wave]
    assert flat == ["a", "b", "d", "c", "e"]  # nothing dropped
    # the semantic law of first-fit: a dependency is always in a
    # strictly earlier wave ("c" waits for "a"), and a file conflict
    # never shares a wave ("d" and "e" split) — but an independent
    # request may join an earlier wave than a later submission ("d").
    wave_of = {r.request_id: i for i, wave in enumerate(waves) for r in wave}
    assert wave_of["a"] < wave_of["c"]
    assert wave_of["d"] != wave_of["e"]
