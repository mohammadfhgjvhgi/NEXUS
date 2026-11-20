"""Phase 15 — §15.2 specialists: registry, mappings, stage affinity."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from nexus.agents.registry import AgentRegistry
from nexus.coding import (
    CODING_LOOP_STAGES,
    CODING_SPECIALIST_SPECS,
    CODING_SPECIALISTS,
    LOOP_STAGE_ORDER,
    SPECIALIST_ROLES,
    CodingLoopStage,
    SpecialistSpec,
    register_coding_specialists,
    specialist_agent,
    specialists_for_stage,
)


@pytest.fixture()
def registry(tmp_path: Path) -> AgentRegistry:
    reg = AgentRegistry(tmp_path)
    reg.seed_master()
    return reg


# ------------------------------------------------------------------ roster


def test_ten_specs_in_plan_order() -> None:
    assert [spec.role for spec in CODING_SPECIALIST_SPECS] == list(SPECIALIST_ROLES)
    assert set(CODING_SPECIALISTS) == set(SPECIALIST_ROLES)
    assert len(CODING_SPECIALIST_SPECS) == 10


def test_all_ten_register_into_real_registry(registry: AgentRegistry) -> None:
    registered = register_coding_specialists(registry)
    assert len(registered) == 10
    assert len(registry) == 11  # master + the ten
    for spec in CODING_SPECIALIST_SPECS:
        assert registry.has(spec.agent_id)
        record = registry.get(spec.agent_id)
        assert record.role == spec.role
        assert record.capabilities == spec.capabilities
        assert record.tools == spec.tools
        assert record.instructions.strip()


def test_registration_is_idempotent_no_duplicates(registry: AgentRegistry) -> None:
    register_coding_specialists(registry)
    register_coding_specialists(registry)
    ids = [agent.id for agent in registry.list_agents()]
    assert len(ids) == len(set(ids))
    assert len(registry) == 11


def test_discover_by_role_and_capability(registry: AgentRegistry) -> None:
    register_coding_specialists(registry)
    debugger = registry.discover_agents(role="debugger")
    assert [agent.id for agent in debugger] == ["ag_coding_debugger"]
    testers = registry.discover_agents(capability="test-execution")
    assert {agent.role for agent in testers} == {"tester"}
    caps = registry.get_capabilities("ag_coding_security")
    assert "policy-check" in caps


def test_registry_persistence_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "agents"
    first = AgentRegistry(path)
    first.seed_master()
    register_coding_specialists(first)
    first_path = first.registry_path
    assert first_path.exists()
    second = AgentRegistry(path)
    assert second.has("ag_coding_reviewer")
    assert len([a for a in second.list_agents() if a.id.startswith("ag_coding_")]) == 10


def test_unregister_coding_specialist(registry: AgentRegistry) -> None:
    register_coding_specialists(registry)
    removed = registry.unregister_agent("ag_coding_frontend")
    assert removed.role == "frontend"
    assert not registry.has("ag_coding_frontend")


# ---------------------------------------------------------------- mappings


def test_every_mapped_module_and_attr_exists() -> None:
    """Each ``module:attr`` reference resolves in the live NEXUS tree."""
    checked = 0
    for spec in CODING_SPECIALIST_SPECS:
        assert spec.modules, f"{spec.role} maps no NEXUS module"
        for mapping in spec.modules:
            module_name, _, attr = mapping.partition(":")
            module = importlib.import_module(module_name)
            assert attr, f"{mapping}: attribute name missing"
            assert getattr(module, attr) is not None, (
                f"{spec.role} maps missing attribute {mapping!r}"
            )
            checked += 1
    assert checked >= 10


def test_capabilities_and_tools_non_empty() -> None:
    for spec in CODING_SPECIALIST_SPECS:
        assert spec.capabilities
        assert spec.tools
        assert spec.mission.strip()
        assert spec.instructions.strip()


# ---------------------------------------------------------- stage affinity


def test_loop_stage_affinity_valid() -> None:
    for spec in CODING_SPECIALIST_SPECS:
        assert spec.stages
        for stage in spec.stages:
            assert isinstance(stage, CodingLoopStage)
            assert stage.value in CODING_LOOP_STAGES


def test_every_stage_served_by_at_least_one_specialist() -> None:
    for stage in LOOP_STAGE_ORDER:
        serving = specialists_for_stage(stage)
        assert serving, f"stage {stage.value} has no serving specialist"
        assert all(stage in spec.stages for spec in serving)


def test_specialists_for_stage_lookup() -> None:
    debugger = specialists_for_stage("debug")
    assert {spec.role for spec in debugger} == {"debugger", "performance"}
    review = specialists_for_stage(CodingLoopStage.REVIEW)
    assert {spec.role for spec in review} == {"security", "devops", "reviewer"}


def test_agent_record_minted_from_spec() -> None:
    agent = specialist_agent(CODING_SPECIALISTS["architect"])
    assert agent.id == "ag_coding_architect"
    assert agent.role == "architect"


def test_spec_rejects_unknown_role_and_empty_shapes() -> None:
    with pytest.raises(ValueError):
        SpecialistSpec(role="cook", mission="m", instructions="i", capabilities=("x",))
    with pytest.raises(ValueError):
        SpecialistSpec(
            role="architect", mission="m", instructions="i", capabilities=()
        )
    with pytest.raises(ValueError):
        SpecialistSpec(
            role="architect",
            mission="m",
            instructions="i",
            capabilities=("x",),
            stages=(),
        )


def test_spec_to_dict_carries_the_verbatim_shape() -> None:
    data = CODING_SPECIALISTS["tester"].to_dict()
    assert data["role"] == "tester"
    assert data["agent_id"] == "ag_coding_tester"
    caps = data["capabilities"]
    stages = data["stages"]
    assert isinstance(caps, (list, tuple))
    assert isinstance(stages, (list, tuple))
    assert "test-execution" in caps
    assert set(stages) <= set(CODING_LOOP_STAGES)
