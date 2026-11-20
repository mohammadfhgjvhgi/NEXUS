"""Specialist team (PHASE 24 §24.2 + §24.4).

The §24.2 thirteen, verbatim and in plan order — each one IS a §6.1
Agent record (the eight fields) registered through the §6.4
AgentRegistry, and each one KNOWS its §24.4 ownership (task · scope ·
parent · children · owned resources) as an
:class:`~nexus.orchestration.contracts.OwnershipSpec`.

Tree law: the §6.3 Master Agent (``ag_master0000``) is the root; its
children are exactly the thirteen specialists; every specialist's
parent is the master.  The tree is validated on build — a tangled web
raises :class:`~nexus.orchestration.contracts.TreeError`, it is never
shipped.

Channel law (§24.1): a specialist holds a reference to the user
channel only so the refusal can be *proven* — every write names its
agent and the channel walls out non-masters.  The specialist's
legitimate reporting path is its parent (the master), via results.

Handlers are injected, never imagined: a specialist without a bound
handler returns an honest ``ok=False`` result ("no handler bound"),
never a fabricated success.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from nexus.agents import MASTER_AGENT_ID, Agent, AgentRegistry

from .contracts import (
    OWNERSHIP_FIELDS,
    SPECIALIST_ROLES,
    AgentResult,
    DispatchRequest,
    MasterOnlyChannelError,
    OrchestrationError,
    OwnershipSpec,
    ScopeViolationError,
    TreeError,
    UnknownRoleError,
    specialist_agent_id,
)

logger = logging.getLogger("nexus.orchestration")

#: A §24.2 handler: one request in, one honest result out.
Handler = Callable[[DispatchRequest], AgentResult]


class UserChannel:
    """§24.1 — the master's channel to the user, walled by identity.

    Every write names its agent; a non-master writer hits
    :class:`MasterOnlyChannelError`.  The transcript is the audit:
    what the user was told, by whom, in what order.
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, str]] = []

    def write(self, agent_id: str, text: str) -> dict[str, str]:
        """Deliver one message to the user — master only, by identity."""
        if agent_id != MASTER_AGENT_ID:
            raise MasterOnlyChannelError(
                f"§24.1: agent {agent_id!r} may not address the user —"
                f" the channel belongs to {MASTER_AGENT_ID!r} alone;"
                " report to your parent instead"
            )
        if not text.strip():
            raise OrchestrationError("user-channel messages must be non-empty")
        entry = {"from": agent_id, "text": text}
        self._entries.append(entry)
        logger.debug("user-channel: master delivered %d chars", len(text))
        return entry

    def transcript(self) -> tuple[dict[str, str], ...]:
        """Everything the user was ever told, in order."""
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# --------------------------------------------------------------- briefs

#: The §24.2 briefs — honest defaults: real capability words, real §6.1
#: instructions, real tool names from the existing NEXUS systems.
#: ``scope`` defaults are deliberately narrow prefixes (§24.4: narrower
#: by default); a build call may override any of them.
ROLE_BRIEFS: dict[str, dict[str, Any]] = {
    "planner": {
        "instructions": (
            "Decompose the user's goal into ordered, verifiable steps;"
            " name dependencies and the roles each step needs."
        ),
        "capabilities": ("planning", "decomposition", "scheduling"),
        "tools": ("memory",),
        "scope": ("plans/",),
    },
    "researcher": {
        "instructions": (
            "Gather facts from documents and the web; cite sources;"
            " separate what is proven from what is claimed."
        ),
        "capabilities": ("research", "web", "documents"),
        "tools": ("research", "documents", "remote"),
        "scope": ("research/",),
    },
    "architect": {
        "instructions": (
            "Turn requirements into contracts and module boundaries;"
            " keep the shapes NEXUS-owned and stdlib-first."
        ),
        "capabilities": ("design", "contracts", "boundaries"),
        "tools": ("codeintel",),
        "scope": ("docs/", "plans/"),
    },
    "coder": {
        "instructions": (
            "Write and edit code within the declared scope; small diffs,"
            " typed, stdlib-first, verified by the tester afterwards."
        ),
        "capabilities": ("coding", "editing", "refactoring"),
        "tools": ("coding", "codeintel"),
        "scope": ("src/", "nexus/"),
    },
    "browser": {
        "instructions": (
            "Drive the browser runtime: navigate, extract, verify marks;"
            " every claim tied to a page state."
        ),
        "capabilities": ("browser", "navigation", "extraction"),
        "tools": ("browser",),
        "scope": ("research/browser/",),
    },
    "computer": {
        "instructions": (
            "Drive the computer runtime: windows, input, screen — inside"
            " the arbitration rules, never outside them."
        ),
        "capabilities": ("computer", "windows", "input"),
        "tools": ("computer", "windows"),
        "scope": ("research/computer/",),
    },
    "tester": {
        "instructions": (
            "Prove the work: run the suites, read the failures honestly,"
            " report pass counts — no green without a run."
        ),
        "capabilities": ("testing", "pytest", "verification"),
        "tools": ("harness",),
        "scope": ("tests/",),
    },
    "debugger": {
        "instructions": (
            "Diagnose failures to root cause with evidence; propose the"
            " smallest fix; never hand-wave a symptom away."
        ),
        "capabilities": ("debugging", "diagnosis", "tracing"),
        "tools": ("codeintel", "harness"),
        "scope": ("tests/", "docs/debug/"),
    },
    "security": {
        "instructions": (
            "Guard the §21 system: classify risk, run the gates and the"
            " scanners, refuse the unsafe path by the book."
        ),
        "capabilities": ("security", "scanning", "redaction"),
        "tools": ("security",),
        "scope": ("docs/security/",),
    },
    "reviewer": {
        "instructions": (
            "Review diffs and results against the stated criteria;"
            " approve or reject with reasons a machine can check."
        ),
        "capabilities": ("review", "quality", "criteria"),
        "tools": ("codeintel",),
        "scope": ("docs/review/",),
    },
    "git": {
        "instructions": (
            "Own version control: stage, commit, branch, push — atomic"
            " commits with messages that tell the truth."
        ),
        "capabilities": ("git", "commits", "branches"),
        "tools": ("git", "github"),
        "scope": (".git/",),
    },
    "recovery": {
        "instructions": (
            "Own the §22 checkpoints: capture before risky change,"
            " reconcile before resume, never resume blind."
        ),
        "capabilities": ("recovery", "checkpoints", "resume"),
        "tools": ("recovery",),
        "scope": ("checkpoints/",),
    },
    "learning": {
        "instructions": (
            "Feed the §12/§13 systems: record what worked, distill"
            " patterns, keep model artifacts out of memory."
        ),
        "capabilities": ("learning", "memory", "patterns"),
        "tools": ("memory", "learning"),
        "scope": ("memory/",),
    },
}

assert set(ROLE_BRIEFS) == set(SPECIALIST_ROLES), "briefs must cover the thirteen"


# ----------------------------------------------------------- specialist


class SpecialistAgent:
    """One §24.2 specialist at runtime: a §6.1 record + §24.4 ownership
    + an injected handler.

    The specialist never grows a user-facing method — its reporting
    path is its parent.  The channel reference it holds exists only to
    be refused (the §21.3 ghost law: the wall must be provable).
    """

    def __init__(
        self,
        spec: Agent,
        ownership: OwnershipSpec,
        channel: UserChannel,
        handler: Handler | None = None,
    ) -> None:
        self.spec = spec
        self.ownership = ownership
        self.channel = channel  # held for the refusal — see UserChannel.write
        self._handler = handler

    # ------------------------------------------------------------ identity

    @property
    def agent_id(self) -> str:
        return self.spec.id

    @property
    def role(self) -> str:
        return self.spec.role

    # ------------------------------------------------------------- wiring

    def bind_handler(self, handler: Handler) -> None:
        """Bind the executor for this role (injected, never imagined)."""
        self._handler = handler

    def knows(self) -> tuple[str, ...]:
        """The §24.4 fields this agent knows — the five, verbatim."""
        return OWNERSHIP_FIELDS

    # ------------------------------------------------------------ request

    def check_scope(self, request: DispatchRequest) -> None:
        """§24.4 scope enforcement — outside the scope is refused.

        Empty scope = a no-file agent: any request carrying files is
        refused.  Prefix match elsewhere.
        """
        for path in request.files:
            if not self.ownership.in_scope(path):
                raise ScopeViolationError(
                    f"§24.4: {self.agent_id!r} ({self.role}) may not touch"
                    f" {path!r} — scope is {list(self.ownership.scope)}"
                )

    def execute(self, request: DispatchRequest) -> AgentResult:
        """Run one request inside the ownership — honestly.

        Scope violations raise (a law break, not a work failure);
        handler exceptions become ``ok=False`` results (work failure,
        reported truthfully); no handler bound → honest ``ok=False``.
        """
        self.check_scope(request)
        if self._handler is None:
            return AgentResult(
                request_id=request.request_id,
                agent_id=self.agent_id,
                role=self.role,
                ok=False,
                detail=f"no handler bound for role {self.role!r}",
            )
        try:
            return self._handler(request)
        except Exception as exc:  # noqa: BLE001 — the failure is the result
            return AgentResult(
                request_id=request.request_id,
                agent_id=self.agent_id,
                role=self.role,
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
            )

    def try_user_channel(self, text: str) -> None:
        """The §24.1 proof hook: a specialist's attempt at the user
        channel — always refused.  (Do not use this to talk to users;
        that is exactly the point.)"""
        self.channel.write(self.agent_id, text)


# ----------------------------------------------------------------- team


class SpecialistTeam:
    """The §24.2 thirteen as one owned tree under the §6.3 master."""

    def __init__(
        self,
        registry: AgentRegistry,
        ownerships: dict[str, OwnershipSpec],
        specialists: dict[str, SpecialistAgent],
        master_ownership: OwnershipSpec,
        channel: UserChannel,
    ) -> None:
        self._registry = registry
        self._ownerships = ownerships
        self._specialists = specialists
        self.master_ownership = master_ownership
        self.channel = channel

    # ------------------------------------------------------------- build

    @classmethod
    def build(
        cls,
        registry: AgentRegistry,
        task: str,
        *,
        scopes: Mapping[str, tuple[str, ...]] | None = None,
        handlers: Mapping[str, Handler] | None = None,
    ) -> SpecialistTeam:
        """Build the thirteen on the §6.4 registry — idempotent per task.

        Deterministic ids (``ag_spec_<role>``), master seeded first,
        every specialist registered (registerAgent), every §24.4 spec
        filled, the tree validated before it ships.
        """
        registry.seed_master()
        channel = UserChannel()
        master_spec = registry.get(MASTER_AGENT_ID)
        ownerships: dict[str, OwnershipSpec] = {}
        specialists: dict[str, SpecialistAgent] = {}
        scope_map = dict(scopes or {})
        handler_map = dict(handlers or {})

        for role in SPECIALIST_ROLES:
            brief = ROLE_BRIEFS[role]
            agent_id = specialist_agent_id(role)
            spec = Agent.create(
                role=role,
                instructions=brief["instructions"],
                capabilities=brief["capabilities"],
                tools=brief["tools"],
                agent_id=agent_id,
            )
            registry.register_agent(spec)
            ownerships[role] = OwnershipSpec(
                agent_id=agent_id,
                task=task,
                scope=scope_map.get(role, tuple(brief["scope"])),
                parent=MASTER_AGENT_ID,
                children=(),
            )
            specialists[role] = SpecialistAgent(
                spec, ownerships[role], channel, handler_map.get(role)
            )

        master_ownership = OwnershipSpec(
            agent_id=MASTER_AGENT_ID,
            task=task,
            parent=None,
            children=tuple(specialist_agent_id(r) for r in SPECIALIST_ROLES),
        )
        _ = master_spec  # the §6.3 record is the root; ownership above names it
        team = cls(registry, ownerships, specialists, master_ownership, channel)
        team.validate_tree()
        return team

    # -------------------------------------------------------------- reads

    @property
    def registry(self) -> AgentRegistry:
        """The §6.4 registry the team lives on."""
        return self._registry

    @property
    def roster(self) -> tuple[SpecialistAgent, ...]:
        """The thirteen in plan order (§24.2 order is the roster order)."""
        return tuple(self._specialists[role] for role in SPECIALIST_ROLES)

    @property
    def roles(self) -> tuple[str, ...]:
        return SPECIALIST_ROLES

    def get(self, role: str) -> SpecialistAgent:
        if role not in self._specialists:
            raise UnknownRoleError(
                f"no specialist for role {role!r} — the thirteen are"
                f" {SPECIALIST_ROLES}"
            )
        return self._specialists[role]

    def ownership_of(self, role: str) -> OwnershipSpec:
        return self.get(role).ownership

    def ownerships(self) -> dict[str, OwnershipSpec]:
        return dict(self._ownerships)

    def specialists_map(self) -> dict[str, SpecialistAgent]:
        """Copy of the role → specialist map (tree-tamper tests / audit)."""
        return dict(self._specialists)

    def __len__(self) -> int:
        return len(self._specialists)

    # --------------------------------------------------------------- tree

    def validate_tree(self) -> None:
        """§24.4 tree integrity — a tree, provably.

        * the master's children are exactly the thirteen ids;
        * every specialist's parent is the master;
        * no specialist has children (two levels — the plan's shape).
        """
        expected_children = tuple(specialist_agent_id(r) for r in SPECIALIST_ROLES)
        if self.master_ownership.children != expected_children:
            raise TreeError(
                "master's children must be exactly the §24.2 thirteen"
                f" — got {self.master_ownership.children}"
            )
        for role, spec in self._ownerships.items():
            if spec.parent != MASTER_AGENT_ID:
                raise TreeError(
                    f"specialist {role} parent must be {MASTER_AGENT_ID!r},"
                    f" got {spec.parent!r}"
                )
            if spec.children:
                raise TreeError(
                    f"specialist {role} must be a leaf — got children"
                    f" {spec.children}"
                )

    # ---------------------------------------------------------- snapshot

    def snapshot(self) -> dict[str, Any]:
        """Serializable team view (checkpoint / audit)."""
        return {
            "task": self.master_ownership.task,
            "master_id": MASTER_AGENT_ID,
            "master": self.master_ownership.as_dict(),
            "specialists": {
                role: self._ownerships[role].as_dict()
                for role in SPECIALIST_ROLES
            },
            "roster_ids": [s.agent_id for s in self.roster],
        }
