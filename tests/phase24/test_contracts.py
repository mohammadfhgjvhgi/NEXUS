"""Phase 24 contracts — the §24.1–§24.4 vocabulary, verbatim."""

from __future__ import annotations

import pytest

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


def test_specialist_roles_thirteen_verbatim() -> None:
    assert SPECIALIST_ROLES == (
        "planner",
        "researcher",
        "architect",
        "coder",
        "browser",
        "computer",
        "tester",
        "debugger",
        "security",
        "reviewer",
        "git",
        "recovery",
        "learning",
    )
    assert len(SPECIALIST_ROLES) == 13


def test_ownership_fields_five_verbatim() -> None:
    assert OWNERSHIP_FIELDS == (
        "task",
        "scope",
        "parent",
        "children",
        "owned_resources",
    )


def test_parallelism_gates_three_verbatim() -> None:
    assert PARALLELISM_GATES == (
        "tasks_independent",
        "files_independent",
        "resources_available",
    )


def test_agent_kinds_and_schema() -> None:
    assert AGENT_KINDS == ("master", "specialist")
    assert ORCHESTRATION_SCHEMA_VERSION == 1


def test_specialist_agent_id_deterministic() -> None:
    for role in SPECIALIST_ROLES:
        assert specialist_agent_id(role) == f"ag_spec_{role}"
    assert specialist_agent_id("planner") == specialist_agent_id("planner")
    with pytest.raises(UnknownRoleError):
        specialist_agent_id("workflow-engine")


def test_ownership_spec_roundtrip_and_scope() -> None:
    spec = OwnershipSpec(
        agent_id="ag_spec_coder",
        task="ship the feature",
        scope=("nexus/", "src/"),
        parent="ag_master0000",
        children=(),
        owned_resources=("file:nexus/x.py",),
    )
    assert OwnershipSpec.from_dict(spec.as_dict()) == spec
    assert spec.knows("task") and spec.knows("owned_resources")
    assert not spec.knows("budget")
    assert spec.in_scope("nexus/deep/module.py")
    assert spec.in_scope("src/main.py")
    assert not spec.in_scope("docs/readme.md")


def test_empty_scope_is_a_no_file_agent() -> None:
    spec = OwnershipSpec(agent_id="ag_x", task="t")
    assert spec.scope == ()
    assert not spec.in_scope("anything.txt")


def test_ownership_spec_with_resources_is_a_copy() -> None:
    spec = OwnershipSpec(agent_id="ag_x", task="t")
    held = spec.with_resources(("r1", "r2"))
    assert held.owned_resources == ("r1", "r2")
    assert spec.owned_resources == ()
    assert held.scope == spec.scope


def test_ownership_spec_validation() -> None:
    with pytest.raises(OrchestrationError):
        OwnershipSpec(agent_id="  ", task="t")
    with pytest.raises(OrchestrationError):
        OwnershipSpec(agent_id="ag_x", task="")


def test_dispatch_request_roundtrip_and_refusals() -> None:
    request = DispatchRequest(
        request_id="r1",
        task_id="task-9",
        role="tester",
        payload="run the suite",
        files=("tests/x.py",),
        resources=("pytest",),
        depends_on=("r0",),
    )
    assert DispatchRequest.from_dict(request.as_dict()) == request
    with pytest.raises(UnknownRoleError):
        DispatchRequest(request_id="r2", task_id="t", role="wizard")
    with pytest.raises(DispatchError):
        DispatchRequest(request_id="", task_id="t", role="tester")
    with pytest.raises(DispatchError):
        DispatchRequest(request_id="r3", task_id="", role="tester")


def test_gate_report_and_verdict_roundtrips() -> None:
    gate = GateReport(gate="files_independent", passed=False, detail="shared x.py")
    assert GateReport.from_dict(gate.as_dict()) == gate
    with pytest.raises(OrchestrationError):
        GateReport(gate="vibes", passed=True)

    verdict = ParallelismVerdict(
        decision="sequential",
        gates=(GateReport(gate="tasks_independent", passed=True), gate),
        reasons=("shared x.py",),
    )
    assert ParallelismVerdict.from_dict(verdict.as_dict()) == verdict
    assert not verdict.allowed
    assert ParallelismVerdict(decision="parallel").allowed
    with pytest.raises(OrchestrationError):
        ParallelismVerdict(decision="maybe")


def test_result_outcome_report_roundtrips() -> None:
    result = AgentResult(
        request_id="r1", agent_id="ag_spec_tester", role="tester",
        ok=True, detail="12 passed", artifacts=("tests/x.py",),
    )
    assert AgentResult.from_dict(result.as_dict()) == result

    outcome = DispatchOutcome(
        request_id="r1", role="tester", wave_index=0,
        ran_parallel=True, result=result,
    )
    assert DispatchOutcome.from_dict(outcome.as_dict()) == outcome

    report = OrchestrationReport(
        goal="ship it",
        master_id="ag_master0000",
        wave_count=2,
        outcomes=(outcome,),
        summary="1/1 ok",
        user_delivered=True,
        field_notes=("wave 1 held a dependency",),
    )
    assert OrchestrationReport.from_dict(report.as_dict()) == report
    assert report.ok


def test_report_ok_is_honest() -> None:
    ok_result = AgentResult(request_id="r1", agent_id="a", role="tester", ok=True)
    bad_result = AgentResult(request_id="r2", agent_id="a", role="coder", ok=False)
    assert not OrchestrationReport(
        goal="g", master_id="m", wave_count=1, outcomes=()
    ).ok  # nothing dispatched — nothing claimed
    assert OrchestrationReport(
        goal="g", master_id="m", wave_count=1,
        outcomes=(DispatchOutcome("r1", "tester", 0, False, ok_result),),
    ).ok
    assert not OrchestrationReport(
        goal="g", master_id="m", wave_count=1,
        outcomes=(DispatchOutcome("r2", "coder", 0, False, bad_result),),
    ).ok


def test_error_family() -> None:
    for exc in (
        UnknownRoleError,
        MasterOnlyChannelError,
        TreeError,
        ScopeViolationError,
        DispatchError,
    ):
        assert issubclass(exc, OrchestrationError)
