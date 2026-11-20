"""Phase 15 — §15.1/§15.2/§15.6 contract shapes (pytest)."""

from __future__ import annotations

import json

import pytest

from nexus.coding import (
    CODING_LOOP_STAGES,
    CODING_OPERATION_KINDS,
    LOOP_STAGE_ORDER,
    SPECIALIST_ROLES,
    CodingError,
    CodingLoopStage,
    CodingOperationKind,
    CodingSessionRecord,
    DebugFinding,
    EditAction,
    InvalidCodingContractError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    PlanStep,
    ReviewCheck,
    ReviewVerdict,
    ToolCallRecord,
)

# ------------------------------------------------------------ verbatim sets


def test_operation_kinds_verbatim() -> None:
    """§15.1 — exactly seven operations, this order, these names."""
    assert [member.value for member in CodingOperationKind] == [
        "analyze",
        "plan",
        "edit",
        "run",
        "test",
        "debug",
        "review",
    ]
    assert tuple(kind.value for kind in CodingOperationKind) == CODING_OPERATION_KINDS


def test_specialist_roles_verbatim() -> None:
    """§15.2 — exactly ten roles, this order, these names."""
    assert SPECIALIST_ROLES == (
        "architect",
        "frontend",
        "backend",
        "database",
        "devops",
        "debugger",
        "tester",
        "security",
        "performance",
        "reviewer",
    )


def test_loop_stages_verbatim_order() -> None:
    """§15.6 — exactly eight stages, this exact order."""
    assert [member.value for member in CodingLoopStage] == [
        "understand",
        "plan",
        "edit",
        "build",
        "test",
        "debug",
        "retest",
        "review",
    ]
    assert tuple(stage.value for stage in CodingLoopStage) == CODING_LOOP_STAGES
    assert list(LOOP_STAGE_ORDER) == list(CodingLoopStage)


def test_kind_and_stage_coercion() -> None:
    """Plan names (any case) coerce; junk is refused honestly."""
    assert CodingOperationKind.from_value("ANALYZE") is CodingOperationKind.ANALYZE
    assert CodingOperationKind.from_value(CodingOperationKind.EDIT) is (
        CodingOperationKind.EDIT
    )
    assert CodingLoopStage.from_value("ReTest") is CodingLoopStage.RETEST
    with pytest.raises(InvalidCodingContractError):
        CodingOperationKind.from_value("deploy")
    with pytest.raises(InvalidCodingContractError):
        CodingLoopStage.from_value("deploy")


def test_operation_status() -> None:
    assert OperationStatus.from_value("OK") is OperationStatus.OK
    assert OperationStatus.from_value("fail") is OperationStatus.FAIL
    with pytest.raises(InvalidCodingContractError):
        OperationStatus.from_value("maybe")


# --------------------------------------------------------------- edit shape


def test_edit_action_replace_mode() -> None:
    action = EditAction(path="src/main.py", old="a * b", new="a / b")
    assert action.mode == "replace"
    assert action.content is None
    assert action.replace_all is True


def test_edit_action_rewrite_mode() -> None:
    action = EditAction(path="src/new.py", content="print('hi')\n")
    assert action.mode == "rewrite"


def test_edit_action_rejects_both_modes() -> None:
    with pytest.raises(InvalidCodingContractError):
        EditAction(path="a.py", old="x", new="y", content="z")


def test_edit_action_rejects_half_replace() -> None:
    with pytest.raises(InvalidCodingContractError):
        EditAction(path="a.py", old="x", new="")


def test_edit_action_rejects_empty_path_and_normalizes() -> None:
    with pytest.raises(InvalidCodingContractError):
        EditAction(path="   ")
    assert EditAction(path="src\\deep\\mod.py", old="a", new="b").path == (
        "src/deep/mod.py"
    )


def test_edit_action_round_trip() -> None:
    action = EditAction(path="main.py", old="return a * b", new="return a / b")
    revived = EditAction.from_dict(json.loads(json.dumps(action.to_dict())))
    assert revived.path == action.path
    assert revived.old == action.old
    assert revived.new == action.new
    assert revived.content == action.content
    assert revived.mode == action.mode


# --------------------------------------------------------------- plan shape


def test_plan_step_shape_and_round_trip() -> None:
    fix = EditAction(path="main.py", old="a", new="b")
    step = PlanStep(
        step_id="s1",
        description="Fix the divide function",
        target_files=("main.py",),
        actions=(fix,),
        rationale="declared recipe",
    )
    revived = PlanStep.from_dict(json.loads(json.dumps(step.to_dict())))
    assert revived.step_id == "s1"
    assert revived.target_files == ("main.py",)
    assert revived.actions[0].new == "b"


def test_plan_step_requires_id_and_description() -> None:
    with pytest.raises(InvalidCodingContractError):
        PlanStep(step_id="", description="")
    with pytest.raises(InvalidCodingContractError):
        PlanStep(step_id="s1", description="   ")


# -------------------------------------------------------------- debug shape


def test_debug_finding_round_trip_with_fix() -> None:
    finding = DebugFinding(
        test="test_main.py::test_divide_correct",
        hypothesis="assertion mismatch in main.py",
        evidence=("assert 18 == 2",),
        suggested_fix=EditAction(path="main.py", old="a * b", new="a / b"),
        lessons=("divide must divide",),
    )
    revived = DebugFinding.from_dict(json.loads(json.dumps(finding.to_dict())))
    assert revived.test == finding.test
    assert revived.suggested_fix is not None
    assert revived.suggested_fix.new == "a / b"
    assert revived.lessons == ("divide must divide",)


def test_debug_finding_requires_test_and_hypothesis() -> None:
    with pytest.raises(InvalidCodingContractError):
        DebugFinding(test="", hypothesis="h")
    with pytest.raises(InvalidCodingContractError):
        DebugFinding(test="t", hypothesis="")


# ------------------------------------------------------------- review shape


def test_review_verdict_requires_reasons() -> None:
    with pytest.raises(InvalidCodingContractError):
        ReviewVerdict(approved=True, reasons=())


def test_review_verdict_round_trip() -> None:
    verdict = ReviewVerdict(
        approved=False,
        reasons=("FAIL tests_green — 0 passed, 1 failed", "VERDICT rejected"),
        checks=(ReviewCheck(name="tests_green", passed=False, detail="1 failed"),),
    )
    revived = ReviewVerdict.from_dict(json.loads(json.dumps(verdict.to_dict())))
    assert revived.approved is False
    assert revived.checks[0].name == "tests_green"
    assert revived.checks[0].passed is False


# ------------------------------------------------------- session/ops shapes


def test_coding_session_record_round_trip() -> None:
    record = CodingSessionRecord(
        session_id="cs_0123456789ab",
        goal="fix divide",
        started_at="2026-09-09T00:00:00Z",
        status="closed",
        files_read=("main.py",),
        files_edited=("main.py", "test_main.py"),
        tool_calls=(ToolCallRecord(name="coding.test", ok=True, duration_ms=12.5),),
        commits=(),
    )
    revived = CodingSessionRecord.from_dict(json.loads(json.dumps(record.to_dict())))
    assert revived.session_id == record.session_id
    assert revived.files_read == ("main.py",)
    assert revived.files_edited == ("main.py", "test_main.py")
    assert revived.tool_calls[0].name == "coding.test"
    assert revived.tool_calls[0].duration_ms == 12.5


def test_coding_session_record_requires_id() -> None:
    with pytest.raises(InvalidCodingContractError):
        CodingSessionRecord(session_id="  ")


def test_operation_request_round_trip_and_defaults() -> None:
    request = OperationRequest(kind=CodingOperationKind.TEST, goal="prove it")
    assert request.workspace_root == ""
    assert request.payload == {}
    assert request.timeout_s == pytest.approx(120.0)
    assert request.kind is CodingOperationKind.TEST
    revived = OperationRequest.from_dict(json.loads(json.dumps(request.to_dict())))
    assert revived.kind is CodingOperationKind.TEST
    assert revived.goal == "prove it"


def test_operation_request_validation() -> None:
    with pytest.raises(InvalidCodingContractError):
        OperationRequest(kind=CodingOperationKind.PLAN, goal="   ")
    with pytest.raises(InvalidCodingContractError):
        OperationRequest(kind=CodingOperationKind.PLAN, goal="g", timeout_s=0)


def test_operation_result_factories_and_round_trip() -> None:
    ok = OperationResult.ok_result(
        CodingOperationKind.EDIT, 12.5, "1 edit(s) applied", {"applied": 1}
    )
    assert ok.ok is True
    assert ok.status is OperationStatus.OK
    assert ok.duration_ms == pytest.approx(12.5)
    fail = OperationResult.fail_result(CodingOperationKind.RUN, 3.0, "boom", "OSError")
    assert fail.ok is False
    assert fail.error == "OSError"
    revived = OperationResult.from_dict(json.loads(json.dumps(fail.to_dict())))
    assert revived.kind is CodingOperationKind.RUN
    assert revived.status is OperationStatus.FAIL
    assert revived.error == "OSError"


def test_coding_error_hierarchy() -> None:
    assert issubclass(InvalidCodingContractError, CodingError)
    assert issubclass(CodingError, Exception)
