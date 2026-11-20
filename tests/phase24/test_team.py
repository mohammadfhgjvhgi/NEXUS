"""Phase 24 team — the §24.2 thirteen on the §6.4 registry, owned (§24.4)."""

from __future__ import annotations

import dataclasses

import pytest

from nexus.agents import MASTER_AGENT_ID
from nexus.orchestration import (
    OWNERSHIP_FIELDS,
    ROLE_BRIEFS,
    SPECIALIST_ROLES,
    DispatchRequest,
    MasterOnlyChannelError,
    ScopeViolationError,
    SpecialistTeam,
    TreeError,
    UnknownRoleError,
    specialist_agent_id,
)


def test_build_thirteen_in_plan_order(team: SpecialistTeam) -> None:
    assert len(team) == 13
    assert [s.role for s in team.roster] == list(SPECIALIST_ROLES)


def test_every_specialist_is_a_registered_61_record(team, registry) -> None:
    for specialist in team.roster:
        assert registry.has(specialist.agent_id)
        record = registry.get(specialist.agent_id)
        assert record.role == specialist.role
        assert record.instructions.strip()
        assert record.capabilities  # real capability words, never empty
        assert record.tools


def test_deterministic_ids(team: SpecialistTeam) -> None:
    for role in SPECIALIST_ROLES:
        assert team.get(role).agent_id == specialist_agent_id(role)
    assert team.get("git").agent_id == "ag_spec_git"


def test_master_is_the_root(team: SpecialistTeam) -> None:
    assert team.master_ownership.agent_id == MASTER_AGENT_ID
    assert team.master_ownership.parent is None
    assert team.master_ownership.children == tuple(
        specialist_agent_id(r) for r in SPECIALIST_ROLES
    )


def test_every_specialist_knows_parent_and_is_a_leaf(team: SpecialistTeam) -> None:
    for specialist in team.roster:
        assert specialist.ownership.parent == MASTER_AGENT_ID
        assert specialist.ownership.children == ()
        assert specialist.ownership.task == "fixture task"


def test_tree_validation_catches_tampering(team: SpecialistTeam) -> None:
    broken_master = dataclasses.replace(
        team.master_ownership,
        children=(specialist_agent_id("coder"),),  # a pruned tree
    )
    broken = SpecialistTeam(
        team.registry, team.ownerships(), team.specialists_map(),
        broken_master, team.channel,
    )
    with pytest.raises(TreeError):
        broken.validate_tree()


def test_tree_validation_catches_orphan(team: SpecialistTeam) -> None:
    orphaned = dict(team.ownerships())
    orphaned["coder"] = dataclasses.replace(
        orphaned["coder"], parent="ag_someone_else"
    )
    broken = SpecialistTeam(
        team.registry, orphaned, team.specialists_map(),
        team.master_ownership, team.channel,
    )
    with pytest.raises(TreeError):
        broken.validate_tree()


def test_knowledge_is_the_five_verbatim_fields(team: SpecialistTeam) -> None:
    for specialist in team.roster:
        assert specialist.knows() == OWNERSHIP_FIELDS


def test_scope_enforcement_prefix_match(team: SpecialistTeam) -> None:
    coder = team.get("coder")
    inside = DispatchRequest(request_id="r1", task_id="t1", role="coder")
    coder.check_scope(dataclasses.replace(inside, files=("nexus/agents/agent.py",)))
    with pytest.raises(ScopeViolationError):
        coder.check_scope(dataclasses.replace(inside, files=("docs/readme.md",)))


def test_empty_scope_refuses_any_file(registry, ownership) -> None:
    team = SpecialistTeam.build(
        registry, "no files", scopes={"planner": ()}
    )
    planner = team.get("planner")
    with pytest.raises(ScopeViolationError):
        planner.check_scope(
            DispatchRequest(request_id="r1", task_id="t1", role="planner",
                            files=("plans/any.md",))
        )


def test_execute_without_handler_is_honestly_false(team: SpecialistTeam) -> None:
    result = team.get("tester").execute(
        DispatchRequest(request_id="r1", task_id="t1", role="tester")
    )
    assert result.ok is False
    assert "no handler bound" in result.detail


def test_execute_with_handler_and_with_failure(team: SpecialistTeam) -> None:
    tester = team.get("tester")

    def good(request: DispatchRequest):
        from nexus.orchestration import AgentResult

        return AgentResult(
            request_id=request.request_id, agent_id=tester.agent_id,
            role="tester", ok=True, detail="ran",
        )

    def boom(request: DispatchRequest):
        raise RuntimeError("device gone")

    tester.bind_handler(good)
    ok = tester.execute(DispatchRequest(request_id="r1", task_id="t1", role="tester"))
    assert ok.ok and ok.detail == "ran"

    tester.bind_handler(boom)
    bad = tester.execute(DispatchRequest(request_id="r2", task_id="t1", role="tester"))
    assert not bad.ok
    assert "RuntimeError" in bad.detail and "device gone" in bad.detail


def test_scope_violation_raises_through_execute(team: SpecialistTeam) -> None:
    with pytest.raises(ScopeViolationError):
        team.get("coder").execute(
            DispatchRequest(request_id="r1", task_id="t1", role="coder",
                            files=("outside.txt",))
        )


def test_user_channel_walls_out_specialists(team: SpecialistTeam) -> None:
    with pytest.raises(MasterOnlyChannelError):
        team.get("security").try_user_channel("let me talk to the user")


def test_unknown_role_refused(team: SpecialistTeam) -> None:
    with pytest.raises(UnknownRoleError):
        team.get("workflow-engine")


def test_build_is_idempotent_on_the_registry(registry, ownership) -> None:
    SpecialistTeam.build(registry, "first")
    SpecialistTeam.build(registry, "second")
    assert len(registry) == 14  # master + thirteen — no duplicates


def test_briefs_cover_the_thirteen_with_honest_defaults() -> None:
    assert set(ROLE_BRIEFS) == set(SPECIALIST_ROLES)
    for _role, brief in ROLE_BRIEFS.items():
        assert brief["instructions"].strip()
        assert brief["capabilities"]
