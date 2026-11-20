"""Coding specialists (New Plan §15.2) — ten declarative specs.

The ten roles, verbatim from the plan::

    architect  frontend  backend  database  devops
    debugger   tester    security  performance  reviewer

Each specialist is a *declarative* :class:`SpecialistSpec` — role,
mission, instructions, capabilities, tools, real NEXUS module
mappings and §15.6 loop-stage affinity — and registers into the
Phase-5 Agent Registry through its real four-verb API
(:class:`nexus.agents.registry.AgentRegistry.register_agent`). The
specs are data, not code: the §6.1 Agent record is minted from the
spec, so the registry stays the §0.5 single source of truth for who
the agents are.

The mappings are honest: every ``module:attr`` reference names an
importable NEXUS artifact (phase 14 codeintel for structure, the §7
harness for test observation, §13 learning for lessons, §3 policy
for security, §4 resources for performance) — nothing is mapped to a
module that does not exist yet (the git seat is a placeholder, so no
specist claims it).

المختصون العشرة — مواصفات تصريحية تُسجَّل في سجل الوكلاء الحقيقي،
وكل قدرة مُسندة لوحدة NEXUS موجودة فعلًا.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nexus.agents import Agent
from nexus.agents.registry import AgentRegistry

from .contracts import CODING_LOOP_STAGES, SPECIALIST_ROLES, CodingLoopStage

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(slots=True)
class SpecialistSpec:
    """One §15.2 specialist — everything the registry needs.

    ``role``         — the verbatim plan role name.
    ``mission``      — the one-sentence charter.
    ``instructions`` — the standing instructions baked into the
                       §6.1 Agent record.
    ``capabilities`` — capability tokens (registry-discoverable).
    ``tools``        — tool names the specialist may call.
    ``modules``      — ``module:attr`` mappings to real NEXUS
                       artifacts (every one import-checked in the
                       phase-15 tests).
    ``stages``       — §15.6 loop-stage affinity (which stages this
                       specialist serves).
    """

    role: str
    mission: str
    instructions: str
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    stages: tuple[CodingLoopStage, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in SPECIALIST_ROLES:
            raise ValueError(
                f"role {self.role!r} is not one of the §15.2 ten: {SPECIALIST_ROLES}"
            )
        self.capabilities = tuple(self.capabilities)
        self.tools = tuple(self.tools)
        self.modules = tuple(self.modules)
        self.stages = tuple(
            CodingLoopStage.from_value(stage) for stage in self.stages
        )
        if not self.capabilities:
            raise ValueError(f"specialist {self.role!r} needs capabilities")
        if not self.stages:
            raise ValueError(f"specialist {self.role!r} needs loop-stage affinity")
        for stage in self.stages:
            if stage.value not in CODING_LOOP_STAGES:
                raise ValueError(f"specialist {self.role!r}: unknown stage {stage!r}")

    @property
    def agent_id(self) -> str:
        """Deterministic registry id — re-registration is a refresh."""
        return f"ag_coding_{self.role}"

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "mission": self.mission,
            "instructions": self.instructions,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "modules": list(self.modules),
            "stages": [stage.value for stage in self.stages],
            "agent_id": self.agent_id,
        }


# ------------------------------------------------------------ the ten


ARCHITECT = SpecialistSpec(
    role="architect",
    mission="Map the codebase before anyone touches it: structure, dependencies, hotspots.",
    instructions=(
        "You are the NEXUS coding architect. Read the repository through the "
        "phase-14 index — repository map, dependency graph, architecture map — "
        "never by shipping whole files to the model. Propose change plans that "
        "respect the layer boundaries; name the exact target files and the "
        "blast radius (transitive impact) of every proposed edit."
    ),
    capabilities=("architecture-analysis", "dependency-graph", "repository-map", "planning"),
    tools=("code_analyze", "repo_map", "impact_query"),
    modules=(
        "nexus.codeintel.engine:CodeIntelEngine",
        "nexus.codeintel.repomap:RepositoryMap",
        "nexus.codeintel.graphs:ImportResolver",
    ),
    stages=(CodingLoopStage.UNDERSTAND, CodingLoopStage.PLAN),
)

FRONTEND = SpecialistSpec(
    role="frontend",
    mission="Change what the user sees: UI files, markup, styles, client scripts.",
    instructions=(
        "You are the NEXUS frontend specialist. Edit the presentation layer "
        "inside the task scope — markup, styles, client scripts — through the "
        "workspace contract. Every edit is a precise old→new or full-content "
        "EditAction with a rationale; never reformat files you were not asked "
        "to touch."
    ),
    capabilities=("frontend-implementation", "ui-editing", "scoped-file-edit"),
    tools=("file_edit", "file_read"),
    modules=(
        "nexus.core.workspace:Workspace",
        "nexus.tools:ToolRegistry",
    ),
    stages=(CodingLoopStage.EDIT, CodingLoopStage.BUILD),
)

BACKEND = SpecialistSpec(
    role="backend",
    mission="Change what the machine does: services, domain logic, APIs.",
    instructions=(
        "You are the NEXUS backend specialist. Edit domain and service code "
        "through the workspace contract, keep every change minimal and "
        "test-covered, and prove it with the harness's observation path "
        "(build, then tests) before declaring done."
    ),
    capabilities=("backend-implementation", "service-editing", "api-editing"),
    tools=("file_edit", "file_read", "code_run"),
    modules=(
        "nexus.core.workspace:Workspace",
        "nexus.harness:Harness",
    ),
    stages=(CodingLoopStage.EDIT, CodingLoopStage.BUILD, CodingLoopStage.TEST),
)

DATABASE = SpecialistSpec(
    role="database",
    mission="Change what persists: schemas, migrations, query code.",
    instructions=(
        "You are the NEXUS database specialist. Treat persistence as the "
        "phase-1 discipline: atomic writes, honest migrations, query code "
        "resolved against the dependency graph. Never lose data to a clever "
        "edit."
    ),
    capabilities=("schema-editing", "migration-planning", "query-analysis"),
    tools=("file_edit", "file_read"),
    modules=(
        "nexus.core.persistence:TaskRepository",
        "nexus.codeintel.graphs:ImportResolver",
    ),
    stages=(CodingLoopStage.EDIT, CodingLoopStage.BUILD),
)

DEVOPS = SpecialistSpec(
    role="devops",
    mission="Make it run everywhere: build, packaging, CI, environments.",
    instructions=(
        "You are the NEXUS devops specialist. Own the build-and-run stages: "
        "compile checks, environment parity, event-visible progress. A build "
        "that only works on your box does not count."
    ),
    capabilities=("build-automation", "environment-management", "ci-wiring"),
    tools=("code_run", "code_run_tests"),
    modules=(
        "nexus.harness:Harness",
        "nexus.events:EventBus",
    ),
    stages=(CodingLoopStage.BUILD, CodingLoopStage.TEST, CodingLoopStage.REVIEW),
)

DEBUGGER = SpecialistSpec(
    role="debugger",
    mission="Turn failing tests into named findings with hypotheses and fixes.",
    instructions=(
        "You are the NEXUS debugger. Start from the failing test's own words "
        "(its assertion error), consult the §13 learning store for lessons "
        "that match, form one hypothesis per finding, and propose the "
        "smallest fix that could work. If you cannot fix it, say so — never "
        "loop forever."
    ),
    capabilities=("debug-analysis", "hypothesis-formation", "lesson-recall"),
    tools=("code_run_tests", "lesson_search"),
    modules=(
        "nexus.learning.store:SQLiteLearningStore",
        "nexus.codeintel.engine:CodeIntelEngine",
    ),
    stages=(CodingLoopStage.DEBUG, CodingLoopStage.RETEST),
)

TESTER = SpecialistSpec(
    role="tester",
    mission="Prove behavior: run the suite, report exactly what fails.",
    instructions=(
        "You are the NEXUS tester. Run the project's tests through the "
        "harness observation path, report pass/fail counts and the exact "
        "failing node ids, and never soften a red suite."
    ),
    capabilities=("test-execution", "test-reporting", "regression-detection"),
    tools=("code_run_tests",),
    modules=(
        "nexus.harness:Harness",
        "nexus.core.engine:TaskState",
    ),
    stages=(CodingLoopStage.TEST, CodingLoopStage.RETEST),
)

SECURITY = SpecialistSpec(
    role="security",
    mission="Keep the change inside policy: scope, permissions, blast radius.",
    instructions=(
        "You are the NEXUS security specialist. Every plan and every review "
        "passes the phase-2 policy engine: is the edit inside the task "
        "scope, is the tool call permitted, does the blast radius stay "
        "bounded. Veto early, in the plan, not late in production."
    ),
    capabilities=("policy-check", "scope-audit", "security-review"),
    tools=("policy_check", "scope_query"),
    modules=(
        "nexus.core.policy:PolicyEngine",
        "nexus.core.policy:TaskPolicy",
    ),
    stages=(CodingLoopStage.PLAN, CodingLoopStage.REVIEW),
)

PERFORMANCE = SpecialistSpec(
    role="performance",
    mission="Find the hot paths before optimizing: hotspots, budgets, resources.",
    instructions=(
        "You are the NEXUS performance specialist. Evidence first: the "
        "phase-14 hotspot ranking and the phase-3 resource ledger decide "
        "what is actually slow. Optimizations without a measured culprit "
        "are rejected in review."
    ),
    capabilities=("hotspot-analysis", "resource-budgeting", "profiling-plan"),
    tools=("hotspot_query", "resource_scan"),
    modules=(
        "nexus.codeintel.engine:CodeIntelEngine",
        "nexus.resources:ResourceManager",
    ),
    stages=(CodingLoopStage.UNDERSTAND, CodingLoopStage.DEBUG),
)

REVIEWER = SpecialistSpec(
    role="reviewer",
    mission="Render the verdict: checklist in, approved/rejected out, with reasons.",
    instructions=(
        "You are the NEXUS reviewer. The §15.6 loop ends at your desk: "
        "re-run the tests, re-read the diffs, walk the deterministic "
        "checklist, and return approved only when every rule passes. "
        "Rejections carry reasons, always."
    ),
    capabilities=("code-review", "checklist-verification", "verdict-rendering"),
    tools=("code_run_tests", "diff_read"),
    modules=(
        "nexus.events:EventBus",
        "nexus.memory:MemoryEngine",
    ),
    stages=(CodingLoopStage.REVIEW,),
)


#: The ten specs, in plan order (§15.2) — the dict key is the role.
CODING_SPECIALISTS: dict[str, SpecialistSpec] = {
    spec.role: spec
    for spec in (
        ARCHITECT,
        FRONTEND,
        BACKEND,
        DATABASE,
        DEVOPS,
        DEBUGGER,
        TESTER,
        SECURITY,
        PERFORMANCE,
        REVIEWER,
    )
}

#: The specs as a plan-ordered tuple (``CODING_SPECIALIST_SPECS`` order
#: is harness-provable against :data:`SPECIALIST_ROLES`).
CODING_SPECIALIST_SPECS: tuple[SpecialistSpec, ...] = tuple(
    CODING_SPECIALISTS[role] for role in SPECIALIST_ROLES
)


# ------------------------------------------------------------ registration


def specialist_agent(spec: SpecialistSpec) -> Agent:
    """Mint the §6.1 Agent record from one spec (deterministic id)."""
    return Agent.create(
        agent_id=spec.agent_id,
        role=spec.role,
        instructions=f"{spec.mission} {spec.instructions}",
        capabilities=spec.capabilities,
        tools=spec.tools,
    )


def register_coding_specialists(
    registry: AgentRegistry,
    specs: Sequence[SpecialistSpec] = CODING_SPECIALIST_SPECS,
) -> tuple[Agent, ...]:
    """Register the §15.2 ten into the real Phase-5 registry.

    Idempotent by construction: agent ids are deterministic
    (``ag_coding_<role>``), so a second call refreshes the records in
    place (``register_agent`` replaces by id).
    """
    registered: list[Agent] = []
    for spec in specs:
        registered.append(registry.register_agent(specialist_agent(spec)))
    return tuple(registered)


def specialists_for_stage(stage: CodingLoopStage | str) -> tuple[SpecialistSpec, ...]:
    """The specs whose loop-stage affinity includes ``stage``."""
    wanted = CodingLoopStage.from_value(stage)
    return tuple(spec for spec in CODING_SPECIALIST_SPECS if wanted in spec.stages)


def spec_from_agent_record(record: Mapping[str, object]) -> SpecialistSpec | None:
    """Reverse lookup: the spec behind a registry record (None if not ours)."""
    agent_id = str(record.get("id") or "")
    if not agent_id.startswith("ag_coding_"):
        return None
    role = agent_id.removeprefix("ag_coding_")
    return CODING_SPECIALISTS.get(role)
