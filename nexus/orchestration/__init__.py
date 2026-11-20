"""NEXUS Orchestration System (PHASE 24 — Multi-Agent Orchestration).

*نقل NEXUS من Agent واحد إلى Agent system.*
(Move NEXUS from one agent to an agent system.)

The four sections::

    24.1  Master Agent       — يبقى الوكيل الوحيد الذي يتعامل مع
                               المستخدم (the ONLY agent that deals
                               with the user)
    24.2  Specialist Agents  — Planner · Researcher · Architect ·
                               Coder · Browser · Computer · Tester ·
                               Debugger · Security · Reviewer · Git ·
                               Recovery · Learning (thirteen)
    24.3  Parallelism        — يُسمح به عندما: Tasks independent ·
                               Files independent · Resources
                               available (three conjunctive gates)
    24.4  Agent Ownership    — كل Agent يعرف: task · scope · parent ·
                               children · owned resources

The structural laws:

* **§24.1** — the user channel is walled by identity
  (:class:`UserChannel` raises :class:`MasterOnlyChannelError` for any
  non-master writer); the master's single door in is
  :meth:`MasterOrchestrator.submit_user_goal` and its single voice out
  is :meth:`MasterOrchestrator.report_to_user`;
* **§24.2** — the thirteen ARE §6.1 Agent records registered through
  the §6.4 AgentRegistry with deterministic ids
  (``ag_spec_<role>``); the tree (master → thirteen leaves) is
  validated on build;
* **§24.3** — three conjunctive gates, decided pairwise by
  :class:`ParallelismGate` and composed deterministically by
  :meth:`ParallelismGate.plan_waves`; every denial carries its reason;
* **§24.4** — every agent's :class:`OwnershipSpec` carries the five
  verbatim fields; scope violations are refused before work starts,
  and resource coordination is the §6.6 OwnershipManager's (a conflict
  surfaces as a result, never an overwrite).

Stdlib only.
"""

from __future__ import annotations

from .contracts import (
    AGENT_KINDS,
    ORCHESTRATION_SCHEMA_VERSION,
    OWNERSHIP_FIELDS,
    PARALLELISM_GATES,
    SPECIALIST_ROLES,
    AgentResult,
    DispatchError,
    DispatchOutcome,
    DispatchRequest,
    GateReport,
    MasterOnlyChannelError,
    OrchestrationError,
    OrchestrationReport,
    OwnershipSpec,
    ParallelismVerdict,
    ScopeViolationError,
    TreeError,
    UnknownRoleError,
    specialist_agent_id,
)
from .orchestrator import (
    DEFAULT_WAVE_TIMEOUT_SECONDS,
    MasterOrchestrator,
)
from .parallelism import ParallelismGate, gate_report_summary
from .team import ROLE_BRIEFS, Handler, SpecialistAgent, SpecialistTeam, UserChannel

__all__ = [
    "AGENT_KINDS",
    "DEFAULT_WAVE_TIMEOUT_SECONDS",
    "ORCHESTRATION_SCHEMA_VERSION",
    "OWNERSHIP_FIELDS",
    "PARALLELISM_GATES",
    "ROLE_BRIEFS",
    "SPECIALIST_ROLES",
    "AgentResult",
    "DispatchError",
    "DispatchOutcome",
    "DispatchRequest",
    "GateReport",
    "Handler",
    "MasterOnlyChannelError",
    "MasterOrchestrator",
    "OrchestrationError",
    "OrchestrationReport",
    "OwnershipSpec",
    "ParallelismGate",
    "ParallelismVerdict",
    "ScopeViolationError",
    "SpecialistAgent",
    "SpecialistTeam",
    "TreeError",
    "UnknownRoleError",
    "UserChannel",
    "gate_report_summary",
    "specialist_agent_id",
]
