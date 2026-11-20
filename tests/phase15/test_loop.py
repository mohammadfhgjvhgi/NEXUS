"""Phase 15 — §15.6 the Coding Loop: stages, states, events, bounds."""

from __future__ import annotations

from pathlib import Path

import pytest
from coding_project import BAD_FIX, GOOD_FIX, MAIN_FIXED, make_buggy_project

from nexus.coding import (
    CODING_LOOP_STAGES,
    LOOP_STAGE_ORDER,
    STAGE_TASK_STATES,
    CodingLoop,
    CodingLoopError,
    CodingLoopResult,
    CodingSession,
    StageTrace,
)
from nexus.coding.operations import CodingAgent
from nexus.events import CANONICAL_EVENTS, EventBus

#: The §15.6 order as strings, verbatim.
LOOP_ORDER = tuple(stage.value for stage in LOOP_STAGE_ORDER)

#: The §2.4 mapping the loop must honor (checked per trace).
EXPECTED_STATES = dict(STAGE_TASK_STATES)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_buggy_project(tmp_path / "workspace")


@pytest.fixture()
def agent(project: Path) -> CodingAgent:
    return CodingAgent(project)


# ------------------------------------------------------------------ happy


def test_happy_path_approved_after_one_debug_cycle(
    agent: CodingAgent, project: Path
) -> None:
    loop = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX])
    result = loop.run()
    assert result.approved is True
    assert result.debug_cycles == 1
    assert (project / "main.py").read_text(encoding="utf-8") == MAIN_FIXED
    assert result.files_touched == ("main.py",)
    assert result.verdict is not None
    assert result.verdict.approved


def test_stage_order_is_the_eight_verbatim(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    assert result.stage_order == LOOP_ORDER
    assert len(result.stage_traces) == 8


def test_task_state_mapping_per_stage(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    for trace in result.stage_traces:
        assert trace.state == EXPECTED_STATES[trace.stage]
    states = [trace.state for trace in result.stage_traces]
    assert states == [
        "ANALYZING",  # understand
        "PLANNING",   # plan
        "EXECUTING",  # edit
        "EXECUTING",  # build
        "EXECUTING",  # test
        "EXECUTING",  # debug
        "EXECUTING",  # retest
        "VERIFYING",  # review
    ]


def test_stage_traces_carry_results(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    for trace in result.stage_traces:
        assert isinstance(trace, StageTrace)
        assert trace.status in ("ok", "fail")
        assert trace.summary.strip()
        assert trace.duration_ms >= 0.0
    # the pre-fix test stage fails; the retest passes; review ok
    by_stage = {trace.stage: trace for trace in result.stage_traces}
    assert by_stage["test"].status == "fail"
    assert by_stage["retest"].status == "ok"
    assert by_stage["review"].status == "ok"
    assert "main.py" in by_stage["debug"].files_touched


# ----------------------------------------------------------------- events


def test_events_are_canonical_and_expected(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    names = set(result.events)
    assert names <= CANONICAL_EVENTS, f"non-canonical event: {names - CANONICAL_EVENTS}"
    for expected in (
        "task.started",
        "task.updated",
        "task.completed",
        "agent.started",
        "agent.completed",
        "tool.called",
        "tool.completed",
        "verification.started",
        "verification.passed",
    ):
        assert expected in names


def test_bus_receives_the_loop_events(project: Path) -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe("*", lambda event: received.append(event.name))
    agent = CodingAgent(project, bus=bus)
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    assert result.approved
    assert bus.published_count > 0
    assert set(received) == set(result.events)
    assert received[0] == "task.started"
    assert "verification.passed" in received


# -------------------------------------------------------------- unfixable


def test_unfixable_bug_is_bounded_and_rejected(
    agent: CodingAgent, project: Path
) -> None:
    loop = CodingLoop(agent, project, "fix the divide function", 2, fixes=[BAD_FIX])
    result = loop.run()
    assert result.approved is False
    assert result.debug_cycles == 2  # exactly the bound — loop terminates
    assert result.max_debug_cycles == 2
    # stage order: the first 8 verbatim, then extra (debug, retest) cycles
    assert result.stage_order[:8] == LOOP_ORDER
    assert result.stage_order[8:] == ("debug", "retest")
    assert result.verdict is not None
    assert result.verdict.approved is False
    assert any("VERDICT rejected" in reason for reason in result.verdict.reasons)


def test_no_recipes_still_bounded(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 2, fixes=[]).run()
    assert result.approved is False
    assert result.debug_cycles == 2
    assert len(result.stage_traces) == 5 + 2 * 2 + 1  # first pass + 2 cycles + review


def test_green_project_needs_no_debug_cycle(project: Path) -> None:
    (project / "main.py").write_text(MAIN_FIXED, encoding="utf-8")
    agent = CodingAgent(project)
    result = CodingLoop(agent, project, "prove the project green", 3).run()
    assert result.approved is True
    assert result.debug_cycles == 0
    assert result.stage_order == LOOP_ORDER


def test_max_debug_cycles_must_be_at_least_one(agent: CodingAgent, project: Path) -> None:
    with pytest.raises(CodingLoopError):
        CodingLoop(agent, project, "g", 0)


# ---------------------------------------------------------------- session


def test_loop_persists_the_session_trail(project: Path) -> None:
    session = CodingSession(goal="fix the divide function", directory=project / "sessions")
    agent = CodingAgent(project, session=session)
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    assert result.approved
    assert session.path is not None and session.path.exists()
    record = session.record
    assert record.status == "closed"
    assert "main.py" in record.files_edited
    assert any(call.name.startswith("coding.") for call in record.tool_calls)
    revived = CodingSession.load(session.path)
    assert revived.session_id == session.session_id
    assert revived.files_edited == ("main.py",)


# ------------------------------------------------------------ result shape


def test_result_to_dict_round_trip(agent: CodingAgent, project: Path) -> None:
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    data = result.to_dict()
    assert data["goal"] == "fix the divide function"
    assert data["approved"] is True
    assert [t["stage"] for t in data["stage_traces"]] == list(LOOP_ORDER)
    assert data["debug_cycles"] == 1
    assert set(data["stage_traces"][0]) == {
        "stage",
        "state",
        "status",
        "summary",
        "duration_ms",
        "events",
        "files_touched",
    }
    assert isinstance(result, CodingLoopResult)
    assert set(STAGE_TASK_STATES) == set(CODING_LOOP_STAGES)
