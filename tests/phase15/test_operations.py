"""Phase 15 — §15.1 operations on a real (temp) project, stdlib + pytest."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest
from coding_project import (
    BAD_FIX,
    FAILING_TEST,
    GOOD_FIX,
    MAIN_BUGGY,
    MAIN_FIXED,
    make_buggy_project,
)

from nexus.coding import (
    CodingAgent,
    CodingError,
    CodingOperationKind,
    EditAction,
    OperationRequest,
    OperationStatus,
)
from nexus.learning.contracts import LearningRecord
from nexus.learning.store import SQLiteLearningStore


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_buggy_project(tmp_path / "workspace")


@pytest.fixture()
def agent(project: Path) -> CodingAgent:
    return CodingAgent(project)


def _request(
    kind: CodingOperationKind,
    goal: str = "fix the divide function",
    payload: dict | None = None,
    timeout_s: float = 180.0,
) -> OperationRequest:
    return OperationRequest(
        kind=kind, goal=goal, workspace_root="", payload=payload or {}, timeout_s=timeout_s
    )


# --------------------------------------------------------------- analyze


def test_analyze_returns_files_and_symbols(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(_request(CodingOperationKind.ANALYZE))
    assert result.ok, result.error
    assert result.kind is CodingOperationKind.ANALYZE
    assert result.duration_ms >= 0.0
    payload = result.payload
    assert payload["files_indexed"] >= 2
    assert payload["symbols"] >= 3  # divide + the two test functions
    assert "main.py" in payload["top_files"] or any(
        path == "main.py" for path, _score in payload["top_files"]
    )
    assert payload["test_files"] == ["test_main.py"]
    assert payload["map_text"].strip()
    assert payload["engine"] == "codeintel"


# ------------------------------------------------------------------ plan


def test_plan_targets_main_py_with_fix_recipe(agent: CodingAgent, project: Path) -> None:
    analyze = agent.execute(_request(CodingOperationKind.ANALYZE))
    result = agent.execute(
        _request(
            CodingOperationKind.PLAN,
            payload={"analyze": analyze.payload, "fixes": [GOOD_FIX.to_dict()]},
        )
    )
    assert result.ok, result.error
    assert result.payload["target_files"] == ["main.py"]
    steps = result.payload["steps"]
    assert steps
    assert steps[0]["target_files"] == ["main.py"]
    assert steps[0]["actions"]
    assert steps[0]["actions"][0]["new"] == "return a / b"


def test_plan_without_recipes_is_honest(agent: CodingAgent, project: Path) -> None:
    analyze = agent.execute(_request(CodingOperationKind.ANALYZE))
    result = agent.execute(
        _request(CodingOperationKind.PLAN, payload={"analyze": analyze.payload})
    )
    assert result.ok
    assert all(not step["actions"] for step in result.payload["steps"])


# ------------------------------------------------------------------ edit


def test_edit_applies_fix_and_records_before_after(
    agent: CodingAgent, project: Path
) -> None:
    before = (project / "main.py").read_text(encoding="utf-8")
    result = agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [GOOD_FIX.to_dict()]})
    )
    assert result.ok, result.error
    diff = result.payload["diffs"][0]
    assert diff["applied"] is True
    assert diff["before_sha"] != diff["after_sha"]
    assert diff["before_lines"] == 2
    assert diff["occurrences"] == 1
    assert (project / "main.py").read_text(encoding="utf-8") == MAIN_FIXED
    assert before == MAIN_BUGGY


def test_edit_fails_honestly_when_pattern_missing(
    agent: CodingAgent, project: Path
) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.EDIT,
            payload={
                "actions": [
                    EditAction(path="main.py", old="not present", new="x").to_dict()
                ]
            },
        )
    )
    assert result.status is OperationStatus.FAIL
    assert result.payload["applied"] == 0
    assert "pattern not found" in result.error
    assert (project / "main.py").read_text(encoding="utf-8") == MAIN_BUGGY


def test_edit_refuses_workspace_escape(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.EDIT,
            payload={"actions": [EditAction(path="../outside.py", old="a", new="b").to_dict()]},
        )
    )
    assert result.status is OperationStatus.FAIL
    assert "escapes the workspace" in result.error
    assert not (project.parent / "outside.py").exists()


def test_edit_requires_actions(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(_request(CodingOperationKind.EDIT, payload={}))
    assert result.status is OperationStatus.FAIL


def test_edit_rewrite_mode_creates_content(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.EDIT,
            payload={
                "actions": [
                    EditAction(path="docs/note.md", content="# notes\n").to_dict()
                ]
            },
        )
    )
    assert result.ok
    assert (project / "docs" / "note.md").read_text(encoding="utf-8") == "# notes\n"


def test_edit_invalidates_stale_bytecode(agent: CodingAgent, project: Path) -> None:
    """The CI's catch (2026-09-09): a same-size fix landing within the
    same mtime second must not leave a stale ``.pyc`` lying to the next
    import. CPython validates ``.pyc`` by (int-seconds mtime, size) —
    ``* → /`` preserves size, and a fast runner writes within the same
    second, so the interpreter served the BUGGY module to the retest.
    The edit operation must purge the caches for every file it writes.
    """
    import os
    import subprocess

    # arm the trap: build the buggy source first, then fix it
    build = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(project)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert build.returncode == 0
    stale = sorted((project / "__pycache__").glob("main.cpython-*.pyc"))
    assert stale, "compileall must have written the cache (the trap is armed)"

    result = agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [GOOD_FIX.to_dict()]})
    )
    assert result.ok
    assert result.payload["bytecode_purged"] >= 1, "the stale cache was not purged"
    assert not stale[0].exists(), "the stale .pyc survived the edit"

    # worst case, forced: same mtime second as the write that armed it
    mtime = os.path.getmtime(project / "main.py")
    os.utime(project / "main.py", (mtime, mtime))
    probe = subprocess.run(
        [sys.executable, "-c", "import main; print(main.divide(6, 3))"],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.stdout.strip() == "2.0", (
        f"stale bytecode served to the next import: {probe.stdout!r}"
    )


# ------------------------------------------------------------------- run


def test_run_executes_command(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.RUN,
            payload={"command": [sys.executable, "-c", "print(6 / 3)"]},
        )
    )
    assert result.ok, result.error
    assert result.payload["exit_code"] == 0
    assert result.payload["stdout"].strip() == "2.0" or result.payload["stdout"].strip() == "2"
    assert result.payload["command"][0] == sys.executable


def test_run_reports_failure(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.RUN,
            payload={"command": [sys.executable, "-c", "import sys; sys.exit(3)"]},
        )
    )
    assert result.status is OperationStatus.FAIL
    assert result.payload["exit_code"] == 3


def test_run_timeout_is_bounded(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(
        _request(
            CodingOperationKind.RUN,
            payload={"command": [sys.executable, "-c", "import time; time.sleep(30)"]},
            timeout_s=1.0,
        )
    )
    assert result.status is OperationStatus.FAIL
    assert result.payload["timed_out"] is True
    assert "timeout" in result.error.lower()


def test_run_requires_command(agent: CodingAgent, project: Path) -> None:
    result = agent.execute(_request(CodingOperationKind.RUN, payload={}))
    assert result.status is OperationStatus.FAIL


# ------------------------------------------------------------------ test


def test_test_detects_exactly_the_failing_test(
    agent: CodingAgent, project: Path
) -> None:
    result = agent.execute(_request(CodingOperationKind.TEST))
    assert result.status is OperationStatus.FAIL
    assert result.payload["failed"] == 1
    assert result.payload["passed"] == 1
    assert list(result.payload["failing_tests"]) == [FAILING_TEST]
    assert result.payload["runner"] == "pytest"


# ----------------------------------------------------------------- debug


def test_debug_names_failing_test_and_hypothesis(
    agent: CodingAgent, project: Path
) -> None:
    test_run = agent.execute(_request(CodingOperationKind.TEST))
    result = agent.execute(
        _request(
            CodingOperationKind.DEBUG,
            payload={"test_outcome": test_run.payload, "fixes": [GOOD_FIX.to_dict()]},
        )
    )
    assert result.ok, result.error
    finding = result.payload["findings"][0]
    assert finding["test"] == FAILING_TEST
    assert "assert" in finding["hypothesis"].lower()
    assert finding["evidence"]
    assert finding["suggested_fix"]["new"] == "return a / b"
    assert result.payload["fixes_available"] == 1


def test_debug_consults_learning_lessons(project: Path) -> None:
    store = SQLiteLearningStore(project.parent / "learning.db")
    store.add_record(
        LearningRecord(
            id="les_" + "ab12" * 4,
            experience_id="exp_debug0001",
            lesson="divide must divide: the / operator, not multiplication",
            source_task="task_debug0001",
            confidence=0.6,
        )
    )
    agent = CodingAgent(project, learning_store=store)
    result = agent.execute(
        _request(
            CodingOperationKind.DEBUG,
            payload={"failing_tests": [FAILING_TEST], "stderr": "assert 18 == 2"},
        )
    )
    assert result.ok
    assert result.payload["lessons_consulted"] >= 1
    assert any(
        "divide must divide" in lesson
        for lesson in result.payload["findings"][0]["lessons"]
    )
    store.close()


# ---------------------------------------------------------------- review


def test_review_approves_after_fix(agent: CodingAgent, project: Path) -> None:
    agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [GOOD_FIX.to_dict()]})
    )
    result = agent.execute(
        _request(
            CodingOperationKind.REVIEW,
            payload={"edits_applied": 1, "debug_cycles": 1, "max_debug_cycles": 3},
        )
    )
    assert result.ok, result.error
    verdict = result.payload["verdict"]
    assert verdict["approved"] is True
    assert any(reason.startswith("PASS tests_green") for reason in verdict["reasons"])
    assert any("VERDICT approved" in reason for reason in verdict["reasons"])


def test_review_rejects_permanent_bug_with_reasons(
    agent: CodingAgent, project: Path
) -> None:
    agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [BAD_FIX.to_dict()]})
    )
    result = agent.execute(
        _request(
            CodingOperationKind.REVIEW,
            payload={"edits_applied": 1, "debug_cycles": 3, "max_debug_cycles": 3},
        )
    )
    assert result.ok
    verdict = result.payload["verdict"]
    assert verdict["approved"] is False
    failed_rules = [reason for reason in verdict["reasons"] if reason.startswith("FAIL")]
    assert "FAIL tests_green — " in failed_rules[0]
    assert any("VERDICT rejected" in reason for reason in verdict["reasons"])
    assert any(
        check["name"] == "no_outstanding_failures" and not check["passed"]
        for check in verdict["checks"]
    )


def test_review_reuses_supplied_test_outcome(agent: CodingAgent, project: Path) -> None:
    agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [GOOD_FIX.to_dict()]})
    )
    green = {
        "exit_code": 0,
        "passed": 2,
        "failed": 0,
        "failing_tests": [],
    }
    result = agent.execute(
        _request(
            CodingOperationKind.REVIEW, payload={"test_outcome": green, "edits_applied": 1}
        )
    )
    assert result.payload["verdict"]["approved"] is True


# ------------------------------------------------------------- dispatcher


def test_execute_is_the_one_contract(agent: CodingAgent, project: Path) -> None:
    """agent.execute(request) → result — all seven through one callable."""
    seen = set()
    for kind in CodingOperationKind:
        result = agent.execute(_request(kind, goal="smoke"))
        assert result.kind is kind
        assert isinstance(result.duration_ms, float)
        seen.add(kind)
    assert len(seen) == 7


def test_execute_coerces_string_kinds(agent: CodingAgent, project: Path) -> None:
    request = OperationRequest(
        kind=cast(CodingOperationKind, "run"),  # runtime coerces (the contract)
        goal="g",
        payload={"command": [sys.executable, "-c", "1"]},
    )
    assert request.kind is CodingOperationKind.RUN
    result = agent.execute(request)
    assert result.ok


def test_execute_rejects_foreign_workspace(agent: CodingAgent, project: Path) -> None:
    request = OperationRequest(
        kind=CodingOperationKind.ANALYZE,
        goal="g",
        workspace_root=str(project.parent / "elsewhere"),
    )
    with pytest.raises(CodingError):
        agent.execute(request)


def test_crashed_operation_is_a_fail_result(agent: CodingAgent, project: Path) -> None:
    """A crashing op reports fail with the error — never an exception out."""
    request = OperationRequest(
        kind=CodingOperationKind.EDIT,
        goal="g",
        payload={"actions": [{"path": "x.py", "old": "a", "new": "b", "content": "c"}]},
    )
    result = agent.execute(request)
    assert result.status is OperationStatus.FAIL
    assert result.error


def test_session_trail_recorded_through_operations(project: Path) -> None:
    from nexus.coding import CodingSession

    session = CodingSession(goal="fix divide", directory=project / "sessions")
    agent = CodingAgent(project, session=session)
    agent.execute(
        _request(CodingOperationKind.EDIT, payload={"actions": [GOOD_FIX.to_dict()]})
    )
    agent.execute(
        _request(CodingOperationKind.RUN, payload={"command": [sys.executable, "-c", "1"]})
    )
    assert session.files_read == ("main.py",)
    assert session.files_edited == ("main.py",)
    assert [call.name for call in session.tool_calls] == ["coding.edit", "coding.run"]
