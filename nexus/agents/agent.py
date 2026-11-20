"""Agent abstraction (Final Build Plan §6.1 / Spec §6.1).

The eight fields are verbatim from the plan::

    Agent
    ├── id
    ├── role
    ├── instructions
    ├── capabilities
    ├── tools
    ├── memory policy
    ├── model policy
    └── verification

The plan fixes the *names*, NEXUS owns the *shapes*. The three policy
fields are typed records (documented decisions — the plan does not
prescribe their internals):

* :class:`MemoryPolicy`  — which memory namespaces the agent may read /
  write, and its retention level. The retention vocabulary deliberately
  mirrors the §2.3 session hierarchy (``user`` / ``conversation`` /
  ``task``) — an agent's memory footprint lives inside that ladder.
* :class:`ModelPolicy`   — how the agent's model is chosen: an explicit
  registry id, or the §5.7 routing inputs (``task_type`` /
  ``complexity``) when the Model Router should decide; plus generation
  limits (``max_tokens`` / ``temperature``).
* :class:`VerificationPolicy` — whether the agent's output must pass
  verification, the named criteria to check, and the bounded number of
  repair attempts before honest failure.

Nothing here imports the Model Manager, the Event Bus or any external
agent framework — the runtime injects every collaborator (§0.4/§0.5:
the Agent abstraction is NEXUS-owned; reference frameworks studied in
``vendor-staging`` never leak into these shapes).

طبقة الوكلاء — الحقول الثمانية حرفيًا كما في الخطة؛ سياسات الذاكرة
والنموذج والتحقق سجلات مطابقة بالأنواع، والتعاونات تُحقن دائمًا.

Stdlib only.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

#: The §6.1 fields, verbatim and in plan order (harness-provable).
AGENT_FIELDS: tuple[str, ...] = (
    "id",
    "role",
    "instructions",
    "capabilities",
    "tools",
    "memory_policy",
    "model_policy",
    "verification",
)

#: Retention levels — the §2.3 session hierarchy (documented mapping).
MEMORY_RETENTION_LEVELS: tuple[str, ...] = ("task", "conversation", "user")


class AgentError(Exception):
    """Invalid agent definition or misuse of the abstraction."""


def new_agent_id() -> str:
    """New agent identity: ``ag_`` + 12 hex chars (same family as
    ``task_``/``wsp_`` ids)."""
    return "ag_" + secrets.token_hex(6)


#: Fixed identity of the §6.3 Master Agent record in the registry.
MASTER_AGENT_ID = "ag_master0000"


# ----------------------------------------------------------------- policies


@dataclass(slots=True)
class MemoryPolicy:
    """§6.1 «memory policy» — read/write namespaces + retention level.

    ``read`` / ``write`` name memory namespaces (Phase 1 §2.3 ladder:
    user-level, conversation-level, task-level); an empty tuple means
    *no* memory access — the agent works from its instructions and the
    per-task context only (the honest default).
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    retention: str = "task"

    def __post_init__(self) -> None:
        self.read = tuple(self.read)
        self.write = tuple(self.write)
        if self.retention not in MEMORY_RETENTION_LEVELS:
            raise AgentError(
                f"memory_policy.retention must be one of {MEMORY_RETENTION_LEVELS},"
                f" got {self.retention!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "read": list(self.read),
            "write": list(self.write),
            "retention": self.retention,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> MemoryPolicy:
        data = data or {}
        return cls(
            read=tuple(data.get("read") or ()),
            write=tuple(data.get("write") or ()),
            retention=str(data.get("retention") or "task"),
        )


@dataclass(slots=True)
class ModelPolicy:
    """§6.1 «model policy» — explicit model or §5.7 routing inputs."""

    model_id: str | None = None
    task_type: str = "chat"
    complexity: float = 0.5  # 0..1 (§5.7 «Complexity»)
    max_tokens: int = 512
    temperature: float = 0.7

    def __post_init__(self) -> None:
        if not 0.0 <= self.complexity <= 1.0:
            raise AgentError(f"model_policy.complexity must be 0..1, got {self.complexity}")
        if self.max_tokens <= 0:
            raise AgentError(f"model_policy.max_tokens must be > 0, got {self.max_tokens}")
        if not 0.0 <= self.temperature <= 2.0:
            raise AgentError(
                f"model_policy.temperature must be 0..2, got {self.temperature}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task_type": self.task_type,
            "complexity": self.complexity,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ModelPolicy:
        data = data or {}
        return cls(
            model_id=data.get("model_id") or None,
            task_type=str(data.get("task_type") or "chat"),
            complexity=float(data.get("complexity", 0.5)),
            max_tokens=int(data.get("max_tokens", 512)),
            temperature=float(data.get("temperature", 0.7)),
        )


@dataclass(slots=True)
class VerificationPolicy:
    """§6.1 «verification» — required flag, named criteria, repair bound."""

    required: bool = True
    criteria: tuple[str, ...] = ()
    max_repairs: int = 2

    def __post_init__(self) -> None:
        self.criteria = tuple(self.criteria)
        if self.max_repairs < 0:
            raise AgentError(
                f"verification.max_repairs must be >= 0, got {self.max_repairs}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "criteria": list(self.criteria),
            "max_repairs": self.max_repairs,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> VerificationPolicy:
        data = data or {}
        return cls(
            required=bool(data.get("required", True)),
            criteria=tuple(data.get("criteria") or ()),
            max_repairs=int(data.get("max_repairs", 2)),
        )


# -------------------------------------------------------------------- agent


@dataclass(slots=True)
class Agent:
    """One §6.1 Agent — the eight verbatim fields, nothing else."""

    id: str
    role: str
    instructions: str
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    memory_policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    model_policy: ModelPolicy = field(default_factory=ModelPolicy)
    verification: VerificationPolicy = field(default_factory=VerificationPolicy)

    def __post_init__(self) -> None:
        self.capabilities = tuple(self.capabilities)
        self.tools = tuple(self.tools)
        if not self.id or not str(self.id).strip():
            raise AgentError("agent id must be a non-empty string")
        if not self.role or not str(self.role).strip():
            raise AgentError(f"agent {self.id}: role must be a non-empty string")
        if not self.instructions or not str(self.instructions).strip():
            raise AgentError(f"agent {self.id}: instructions must be a non-empty string")

    # ------------------------------------------------------------- factory

    @classmethod
    def create(
        cls,
        *,
        role: str,
        instructions: str,
        capabilities: Sequence[str] = (),
        tools: Sequence[str] = (),
        memory_policy: MemoryPolicy | None = None,
        model_policy: ModelPolicy | None = None,
        verification: VerificationPolicy | None = None,
        agent_id: str | None = None,
    ) -> Agent:
        return cls(
            id=agent_id or new_agent_id(),
            role=role,
            instructions=instructions,
            capabilities=tuple(capabilities),
            tools=tuple(tools),
            memory_policy=memory_policy or MemoryPolicy(),
            model_policy=model_policy or ModelPolicy(),
            verification=verification or VerificationPolicy(),
        )

    @classmethod
    def master_record(cls) -> Agent:
        """The §6.3 Master Agent's registry record (fixed identity)."""
        return cls(
            id=MASTER_AGENT_ID,
            role="master",
            instructions=(
                "You are the NEXUS Master Agent: understand the user's goal, "
                "decompose the work, delegate to capable agents, follow their "
                "progress, receive results, decide continuation, and decide "
                "when the task reaches Verification."
            ),
            capabilities=("orchestration", "delegation", "verification"),
        )

    # --------------------------------------------------------- round-trips

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "instructions": self.instructions,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "memory_policy": self.memory_policy.to_dict(),
            "model_policy": self.model_policy.to_dict(),
            "verification": self.verification.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Agent:
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise AgentError(f"unknown agent fields: {sorted(unknown)}")
        return cls(
            id=str(data["id"]),
            role=str(data["role"]),
            instructions=str(data["instructions"]),
            capabilities=tuple(data.get("capabilities") or ()),
            tools=tuple(data.get("tools") or ()),
            memory_policy=MemoryPolicy.from_dict(data.get("memory_policy")),
            model_policy=ModelPolicy.from_dict(data.get("model_policy")),
            verification=VerificationPolicy.from_dict(data.get("verification")),
        )

    def with_capabilities(self, capabilities: Sequence[str]) -> Agent:
        """Copy with replaced capabilities (registry bookkeeping helper)."""
        return Agent(
            id=self.id,
            role=self.role,
            instructions=self.instructions,
            capabilities=tuple(capabilities),
            tools=self.tools,
            memory_policy=self.memory_policy,
            model_policy=self.model_policy,
            verification=self.verification,
        )
