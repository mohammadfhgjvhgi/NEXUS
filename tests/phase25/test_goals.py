"""Phase 25 goals — §25.1 persistence + §25.3 the durable ladder."""

from __future__ import annotations

import json

import pytest

from nexus.horizon import (
    GoalRecord,
    GoalStore,
    HorizonError,
    IllegalTransitionError,
    UnknownGoalError,
)


def test_create_persists_atomically(store: GoalStore) -> None:
    goal = store.create_goal("خذ المهمة واشتغل لحد ما تخلص", "30_minutes")
    assert goal.state == "pending"
    assert goal.progress_seq == 0
    assert goal.deadline_at is None
    on_disk = json.loads(store.goal_path(goal.goal_id).read_text(encoding="utf-8"))
    assert on_disk["statement"] == "خذ المهمة واشتغل لحد ما تخلص"
    assert on_disk["deadline"] == "30_minutes"


def test_unknown_goal_refused(store: GoalStore) -> None:
    with pytest.raises(UnknownGoalError):
        store.get("goal_nope")


def test_reboot_finds_the_goal(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals")
    goal = store.create_goal("survive the reboot", "8_hours")
    # the successor process: a fresh store over the same directory
    store2 = GoalStore(tmp_path / "goals")
    found = store2.get(goal.goal_id)
    assert found.statement == "survive the reboot"
    assert found.deadline == "8_hours"
    assert found.created_at == goal.created_at


def test_list_goals(store: GoalStore) -> None:
    a = store.create_goal("first", "30_minutes")
    b = store.create_goal("second", "until_completion")
    ids = [g.goal_id for g in store.list_goals()]
    assert sorted(ids) == sorted([a.goal_id, b.goal_id])


def test_exists(store: GoalStore) -> None:
    goal = store.create_goal("x", "2_hours")
    assert store.exists(goal.goal_id)
    assert not store.exists("goal_missing")


def test_transition_law_happy_path(store: GoalStore) -> None:
    goal = store.create_goal("walk the ladder", "2_hours")
    assert store.transition(goal.goal_id, "running").state == "running"
    assert store.transition(goal.goal_id, "paused").state == "paused"
    assert store.transition(goal.goal_id, "running").state == "running"
    assert store.transition(goal.goal_id, "completed").state == "completed"


def test_illegal_transitions_refused(store: GoalStore) -> None:
    goal = store.create_goal("stay legal", "2_hours")
    with pytest.raises(IllegalTransitionError):
        store.transition(goal.goal_id, "completed")  # pending → completed: no
    store.transition(goal.goal_id, "running")
    store.transition(goal.goal_id, "completed")
    with pytest.raises(IllegalTransitionError):
        store.transition(goal.goal_id, "running")  # terminal has no exits
    with pytest.raises(HorizonError):
        store.transition(goal.goal_id, "flying")


def test_transition_updates_updated_at(store: GoalStore) -> None:
    goal = store.create_goal("timestamped", "2_hours")
    moved = store.transition(goal.goal_id, "running")
    assert moved.updated_at >= goal.created_at


def test_progress_journal_append_and_read(store: GoalStore) -> None:
    goal = store.create_goal("journalled", "until_completion")
    n1 = store.append_progress(goal.goal_id, "step one")
    n2 = store.append_progress(goal.goal_id, "step two")
    assert (n1.seq, n2.seq) == (1, 2)
    notes = store.progress(goal.goal_id)
    assert [n.message for n in notes] == ["step one", "step two"]
    assert store.get(goal.goal_id).progress_seq == 2


def test_progress_seq_survives_reboot(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals")
    goal = store.create_goal("counted", "2_hours")
    store.append_progress(goal.goal_id, "one")
    store.append_progress(goal.goal_id, "two")
    store2 = GoalStore(tmp_path / "goals")
    assert store2.get(goal.goal_id).progress_seq == 2
    third = store2.append_progress(goal.goal_id, "three")
    assert third.seq == 3  # the successor continues the count, no reset


def test_empty_progress_note_refused(store: GoalStore) -> None:
    goal = store.create_goal("quiet", "2_hours")
    with pytest.raises(HorizonError):
        store.append_progress(goal.goal_id, "   ")


def test_corrupt_state_is_refused_not_forgotten(tmp_path) -> None:
    store = GoalStore(tmp_path / "goals")
    goal = store.create_goal("corrupt me", "2_hours")
    path = store.goal_path(goal.goal_id)
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(HorizonError):
        store.get(goal.goal_id)  # a refusal, never a silent fresh start


def test_begin_run_bumps_generation_and_sets_window(store, wall) -> None:
    from nexus.horizon import deadline_window

    goal = store.create_goal("leased", "30_minutes")
    window = deadline_window("30_minutes", wall_clock=wall)
    record = store.begin_run(goal.goal_id, deadline_at=window)
    assert record.state == "running"
    assert record.generation == 1
    assert record.deadline_at == wall() + 1800.0
    again = store.begin_run(goal.goal_id, deadline_at=window)
    assert again.generation == 2  # the durable lease moves on


def test_set_checkpoint_persists(store: GoalStore) -> None:
    goal = store.create_goal("checkpointed", "2_hours")
    store.set_checkpoint(goal.goal_id, "ckpt_9")
    assert store.get(goal.goal_id).last_checkpoint_id == "ckpt_9"
    store.set_checkpoint(goal.goal_id, None)
    assert store.get(goal.goal_id).last_checkpoint_id is None


def test_unbounded_goal_carries_no_deadline_even_when_running(store, wall) -> None:
    from nexus.horizon import deadline_window

    goal = store.create_goal("forever until done", "until_completion")
    window = deadline_window("until_completion", wall_clock=wall)
    assert window is None
    record = store.begin_run(goal.goal_id, deadline_at=window)
    assert record.deadline_at is None  # no deadline exists, honestly


def test_roundtrip_via_record(store: GoalStore) -> None:
    goal = store.create_goal("round", "8_hours")
    record = store.get(goal.goal_id)
    assert GoalRecord.from_dict(record.as_dict()) == record
