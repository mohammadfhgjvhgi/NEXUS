"""Phase 25 contracts — the §25.1–§25.7 vocabulary, verbatim."""

from __future__ import annotations

import pytest

from nexus.horizon import (
    DEADLINE_SECONDS,
    DEADLINES,
    GOAL_STATES,
    HORIZON_SCHEMA_VERSION,
    RESUMABLE_STATES,
    TRANSITIONS,
    BlindResumeError,
    GoalRecord,
    HorizonError,
    IllegalTransitionError,
    ProgressNote,
    StepOutcome,
    UnknownDeadlineError,
    UnknownGoalError,
    deadline_seconds,
    new_goal_id,
)


def test_deadlines_four_verbatim() -> None:
    assert DEADLINES == (
        "30_minutes",
        "2_hours",
        "8_hours",
        "until_completion",
    )


def test_deadline_windows_honest() -> None:
    assert DEADLINE_SECONDS["30_minutes"] == 1800.0
    assert DEADLINE_SECONDS["2_hours"] == 7200.0
    assert DEADLINE_SECONDS["8_hours"] == 28800.0
    assert DEADLINE_SECONDS["until_completion"] is None
    assert deadline_seconds("8_hours") == 28800.0
    assert deadline_seconds("until_completion") is None
    with pytest.raises(UnknownDeadlineError):
        deadline_seconds("forever")


def test_goal_states_and_transition_law() -> None:
    assert GOAL_STATES == (
        "pending",
        "running",
        "paused",
        "completed",
        "failed",
        "deadline_hit",
    )
    assert TRANSITIONS["pending"] == frozenset({"running"})
    assert TRANSITIONS["running"] == frozenset(
        {"paused", "completed", "failed", "deadline_hit"}
    )
    assert TRANSITIONS["paused"] == frozenset({"running"})
    assert TRANSITIONS["completed"] == frozenset()  # terminal
    assert TRANSITIONS["failed"] == frozenset({"running"})
    assert TRANSITIONS["deadline_hit"] == frozenset({"running"})


def test_resumable_states() -> None:
    assert RESUMABLE_STATES == frozenset(
        {"paused", "failed", "deadline_hit", "running"}
    )


def test_schema_version() -> None:
    assert HORIZON_SCHEMA_VERSION == 1


def test_goal_id_family() -> None:
    gid = new_goal_id()
    assert gid.startswith("goal_") and len(gid) == len("goal_") + 12
    assert new_goal_id() != gid


def test_goal_record_roundtrip() -> None:
    record = GoalRecord(
        goal_id="goal_abc123456789",
        statement="خذ المهمة واشتغل لحد ما تخلص",
        deadline="2_hours",
        state="running",
        created_at="2026-09-10T00:00:00+00:00",
        updated_at="2026-09-10T00:01:00+00:00",
        progress_seq=7,
        last_checkpoint_id="ckpt-1",
        generation=3,
        deadline_at=1_700_000_000.0,
    )
    assert GoalRecord.from_dict(record.as_dict()) == record


def test_goal_record_unbounded_deadline_stays_none() -> None:
    record = GoalRecord(
        goal_id="goal_abc123456789",
        statement="work until done",
        deadline="until_completion",
    )
    assert GoalRecord.from_dict(record.as_dict()).deadline_at is None


def test_goal_record_validation() -> None:
    with pytest.raises(HorizonError):
        GoalRecord(goal_id=" ", statement="s", deadline="2_hours")
    with pytest.raises(HorizonError):
        GoalRecord(goal_id="goal_x", statement="  ", deadline="2_hours")
    with pytest.raises(UnknownDeadlineError):
        GoalRecord(goal_id="goal_x", statement="s", deadline="forever")
    with pytest.raises(HorizonError):
        GoalRecord(goal_id="goal_x", statement="s", deadline="2_hours", state="flying")


def test_progress_note_roundtrip() -> None:
    note = ProgressNote(seq=3, ts="2026-09-10T00:00:00+00:00", message="step 3 done")
    assert ProgressNote.from_dict(note.as_dict()) == note


def test_step_outcome_shape() -> None:
    keep = StepOutcome(done=False, note="halfway")
    done = StepOutcome(done=True)
    assert not keep.done and keep.note == "halfway"
    assert done.done and done.note == ""


def test_error_family() -> None:
    for exc in (
        UnknownDeadlineError,
        UnknownGoalError,
        IllegalTransitionError,
        BlindResumeError,
    ):
        assert issubclass(exc, HorizonError)
    err = BlindResumeError(["a", "b"])
    assert err.refusals == ("a", "b")
    assert "a" in str(err) and "b" in str(err)
