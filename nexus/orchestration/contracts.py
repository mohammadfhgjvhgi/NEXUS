"""Orchestration contracts (PHASE 24 — Multi-Agent Orchestration §24.1–§24.4).

The user's plan, verbatim::

    الهدف: نقل NEXUS من Agent واحد إلى Agent system.

    24.1  Master Agent      — يبقى الوكيل الوحيد الذي يتعامل مع المستخدم
                              (remains the ONLY agent that deals with
                              the user).
    24.2  Specialist Agents — Planner · Researcher · Architect · Coder ·
                              Browser · Computer · Tester · Debugger ·
                              Security · Reviewer · Git · Recovery ·
                              Learning (thirteen, in plan order).
    24.3  Parallelism       — يُسمح به عندما: Tasks independent ·
                              Files independent · Resources available
                              (three conjunctive gates — all three or
                              no parallelism).
    24.4  Agent Ownership   — كل Agent يعرف: task · scope · parent ·
                              children · owned resources (five fields,
                              verbatim).

The vocabulary below is the plan's nouns; the engines
(:mod:`nexus.orchestration.team` · ``.parallelism`` ·
``.orchestrator``) are the verbs.  Integration law: the §24.2
specialists ARE §6.1 Agent records registered through the §6.4
AgentRegistry, and §24.4 ownership coordinates through the §6.6
OwnershipManager — this phase composes the existing agent system, it
never copies it.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Orchestration schema version (bumped on breaking contract change).
ORCHESTRATION_SCHEMA_VERSION = 1

#: §24.2 Specialist Agents — the thirteen roles, verbatim and in plan
#: order (harness-provable).
SPECIALIST_ROLES: tuple[str, ...] = (
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

#: §24.4 Agent Ownership — the five fields every agent knows, verbatim
#: and in plan order (harness-provable).
OWNERSHIP_FIELDS: tuple[str, ...] = (
    "task",
    "scope",
    "parent",
    "children",
    "owned_resources",
)

#: §24.3 Parallelism — the three conjunctive gates, verbatim and in
#: plan order: parallelism is allowed only when ALL of them pass.
PARALLELISM_GATES: tuple[str, ...] = (
    "tasks_independent",
    "files_independent",
    "resources_available",
)

#: The two agent kinds of the §24 system (master + the §24.2 kind).
AGENT_KINDS: tuple[str, ...] = ("master", "specialist")


# ------------------------------------------------------------------ errors


class OrchestrationError(Exception):
    """Orchestration misuse or violated law."""


class UnknownRoleError(OrchestrationError):
    """A role outside the §24.2 thirteen was requested."""


class MasterOnlyChannelError(OrchestrationError):
    """§24.1 — a non-master agent attempted the user channel.

    The user channel is the master's alone: a specialist that tries to
    speak to the user is refused here — the attempt is the violation,
    the error is the wall.
    """


class TreeError(OrchestrationError):
    """§24.4 parent/children inconsistency (a tree, not a tangled web)."""


class ScopeViolationError(OrchestrationError):
    """§24.4 — work requested outside the agent's declared scope."""


class DispatchError(OrchestrationError):
    """A dispatch request was malformed for execution."""


# -------------------------------------------------------------- helpers


def specialist_agent_id(role: str) -> str:
    """Deterministic registry id for a §24.2 specialist role.

    Same ``ag_`` identity family as §6.1's ``new_agent_id`` — but
    stable per role, so the ownership tree is reproducible across
    boots (the roster is the system, not a roll of the dice).
    """
    if role not in SPECIALIST_ROLES:
        raise UnknownRoleError(
            f"unknown specialist role {role!r} — the §24.2 thirteen are"
            f" {SPECIALIST_ROLES}"
        )
    return f"ag_spec_{role}"


def _tup(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


# ---------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class OwnershipSpec:
    """§24.4 — the five verbatim fields every agent knows.

    * ``task``            — what this agent is for (its mission label);
    * ``scope``           — the file/path prefixes it may touch (empty
      tuple = a no-file agent: any request carrying files is refused —
      the honest default is narrower, not wider);
    * ``parent``          — the agent above (``None`` for the master);
    * ``children``        — the agents below (delegation tree);
    * ``owned_resources`` — the §6.6 resources currently held.
    """

    agent_id: str
    task: str
    scope: tuple[str, ...] = ()
    parent: str | None = None
    children: tuple[str, ...] = ()
    owned_resources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _tup(self.scope))
        object.__setattr__(self, "children", _tup(self.children))
        object.__setattr__(self, "owned_resources", _tup(self.owned_resources))
        if not self.agent_id.strip():
            raise OrchestrationError("ownership.agent_id must be non-empty")
        if not self.task.strip():
            raise OrchestrationError("ownership.task must be non-empty")

    def knows(self, field_name: str) -> bool:
        """Does the spec carry the named §24.4 field? (vocabulary check)."""
        return field_name in OWNERSHIP_FIELDS

    def in_scope(self, path: str) -> bool:
        """May this agent touch ``path``? (prefix match over ``scope``).

        Empty scope means no file access at all — narrower by default.
        """
        return any(path.startswith(prefix) for prefix in self.scope)

    def with_resources(self, resources: tuple[str, ...]) -> OwnershipSpec:
        """Copy of the spec holding ``resources`` (dispatch bookkeeping)."""
        return OwnershipSpec(
            agent_id=self.agent_id,
            task=self.task,
            scope=self.scope,
            parent=self.parent,
            children=self.children,
            owned_resources=_tup(resources),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task": self.task,
            "scope": list(self.scope),
            "parent": self.parent,
            "children": list(self.children),
            "owned_resources": list(self.owned_resources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OwnershipSpec:
        return cls(
            agent_id=str(data["agent_id"]),
            task=str(data["task"]),
            scope=_tup(data.get("scope")),
            parent=data.get("parent"),
            children=_tup(data.get("children")),
            owned_resources=_tup(data.get("owned_resources")),
        )


@dataclass(frozen=True, slots=True)
class DispatchRequest:
    """One unit of work the master hands to one §24.2 specialist.

    ``files`` and ``resources`` are the claims the §24.3 gates judge;
    ``depends_on`` names requests that must finish first (a declared
    dependency makes ``tasks_independent`` false — dependency is
    stated, never guessed).
    """

    request_id: str
    task_id: str
    role: str
    payload: str = ""
    files: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", _tup(self.files))
        object.__setattr__(self, "resources", _tup(self.resources))
        object.__setattr__(self, "depends_on", _tup(self.depends_on))
        if not self.request_id.strip():
            raise DispatchError("request_id must be non-empty")
        if not self.task_id.strip():
            raise DispatchError("task_id must be non-empty")
        if self.role not in SPECIALIST_ROLES:
            raise UnknownRoleError(
                f"dispatch to unknown role {self.role!r} — the §24.2"
                f" thirteen are {SPECIALIST_ROLES}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "role": self.role,
            "payload": self.payload,
            "files": list(self.files),
            "resources": list(self.resources),
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DispatchRequest:
        return cls(
            request_id=str(data["request_id"]),
            task_id=str(data["task_id"]),
            role=str(data["role"]),
            payload=str(data.get("payload") or ""),
            files=_tup(data.get("files")),
            resources=_tup(data.get("resources")),
            depends_on=_tup(data.get("depends_on")),
        )


@dataclass(frozen=True, slots=True)
class GateReport:
    """One §24.3 gate's verdict with its honest detail."""

    gate: str
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if self.gate not in PARALLELISM_GATES:
            raise OrchestrationError(
                f"unknown gate {self.gate!r} — the §24.3 three are"
                f" {PARALLELISM_GATES}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "passed": self.passed, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateReport:
        return cls(
            gate=str(data["gate"]),
            passed=bool(data["passed"]),
            detail=str(data.get("detail") or ""),
        )


@dataclass(frozen=True, slots=True)
class ParallelismVerdict:
    """§24.3's decision — all three gates or no parallelism.

    ``decision`` is ``"parallel"`` only when every gate passed;
    otherwise ``"sequential"`` and ``reasons`` carry each failing
    gate's detail (the denial is always explainable).
    """

    decision: str
    gates: tuple[GateReport, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", tuple(self.gates))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.decision not in ("parallel", "sequential"):
            raise OrchestrationError(
                f"decision must be 'parallel' or 'sequential', got {self.decision!r}"
            )

    @property
    def allowed(self) -> bool:
        return self.decision == "parallel"

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "gates": [g.as_dict() for g in self.gates],
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParallelismVerdict:
        return cls(
            decision=str(data["decision"]),
            gates=tuple(GateReport.from_dict(g) for g in data.get("gates") or ()),
            reasons=_tup(data.get("reasons")),
        )


@dataclass(frozen=True, slots=True)
class AgentResult:
    """What one specialist came back with — success is claimed, never
    granted: ``ok=False`` carries the honest detail."""

    request_id: str
    agent_id: str
    role: str
    ok: bool
    detail: str = ""
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", _tup(self.artifacts))

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "ok": self.ok,
            "detail": self.detail,
            "artifacts": list(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentResult:
        return cls(
            request_id=str(data["request_id"]),
            agent_id=str(data["agent_id"]),
            role=str(data["role"]),
            ok=bool(data["ok"]),
            detail=str(data.get("detail") or ""),
            artifacts=_tup(data.get("artifacts")),
        )


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """One request's journey: which wave, parallel or not, and the result."""

    request_id: str
    role: str
    wave_index: int
    ran_parallel: bool
    result: AgentResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "role": self.role,
            "wave_index": self.wave_index,
            "ran_parallel": self.ran_parallel,
            "result": self.result.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DispatchOutcome:
        return cls(
            request_id=str(data["request_id"]),
            role=str(data["role"]),
            wave_index=int(data["wave_index"]),
            ran_parallel=bool(data["ran_parallel"]),
            result=AgentResult.from_dict(data["result"]),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationReport:
    """The master's account of one orchestrated goal — the record the
    user actually sees through the §24.1 channel."""

    goal: str
    master_id: str
    wave_count: int
    outcomes: tuple[DispatchOutcome, ...] = ()
    summary: str = ""
    user_delivered: bool = False
    field_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        object.__setattr__(self, "field_notes", tuple(self.field_notes))

    @property
    def ok(self) -> bool:
        """Every dispatched request succeeded."""
        return bool(self.outcomes) and all(o.result.ok for o in self.outcomes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ORCHESTRATION_SCHEMA_VERSION,
            "goal": self.goal,
            "master_id": self.master_id,
            "wave_count": self.wave_count,
            "outcomes": [o.as_dict() for o in self.outcomes],
            "summary": self.summary,
            "user_delivered": self.user_delivered,
            "field_notes": list(self.field_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationReport:
        return cls(
            goal=str(data["goal"]),
            master_id=str(data["master_id"]),
            wave_count=int(data["wave_count"]),
            outcomes=tuple(
                DispatchOutcome.from_dict(o) for o in data.get("outcomes") or ()
            ),
            summary=str(data.get("summary") or ""),
            user_delivered=bool(data.get("user_delivered")),
            field_notes=_tup(data.get("field_notes")),
        )
