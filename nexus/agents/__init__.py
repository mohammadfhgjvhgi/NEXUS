"""NEXUS Agent Runtime (Final Build Plan §6) — Phase 5.

Turns the Phase-4 *model* into an actual *Agent*. The six plan
sections, each in its own module:

* :mod:`nexus.agents.agent`      — §6.1 the Agent abstraction (eight
                                    verbatim fields: id, role,
                                    instructions, capabilities, tools,
                                    memory policy, model policy,
                                    verification)
* :mod:`nexus.agents.loop`       — §6.2 the Agent Loop
                                    (Observe → Context → Decide →
                                    Tool/Agent call → Observe → Verify
                                    → Continue — recorded phase by
                                    phase)
* :mod:`nexus.agents.master`     — §6.3 the Master Agent (the seven
                                    verbatim behaviors, driving the
                                    §2.4 task machine: ANALYZING →
                                    PLANNING → EXECUTING → VERIFYING →
                                    COMPLETED with bounded REPAIRING)
* :mod:`nexus.agents.registry`   — §6.4 the Agent Registry (the four
                                    verbatim verbs — register /
                                    unregister / discover /
                                    getCapabilities — with atomic
                                    persistence)
* :mod:`nexus.agents.messages`   — §6.5 Agent Communication (the
                                    eight verbatim message fields,
                                    mailboxes, per-task structured log)
* :mod:`nexus.agents.ownership`  — §6.6 Agent Ownership (resource →
                                    owner; conflicts become
                                    coordination, never overwrites)

Ownership discipline (Plan §0.5): the Master Agent and the Agent
Registry are NEXUS-owned — no external agent framework owns any of
this. The reference frameworks studied in ``vendor-staging``
(langgraph / autogen / deepagents — see
``docs/REPOSITORY-INTEGRATION.md`` Round 2) informed the *patterns*
(loop shapes, registry semantics, delegation flow); none of their
code is imported, per the §0.4 abstraction rule and the Phase-5
watchlist written before this phase started.

Event discipline: only §2.2 canonical names — ``agent.started`` /
``agent.completed`` / ``agent.failed``, ``tool.called`` /
``tool.completed`` / ``tool.failed``, ``verification.started`` /
``verification.passed`` / ``verification.failed`` (plus ``task.*``
via the injected TaskEngine). The 28-event registry stays
authoritative and binding.

طبقة تشغيل الوكلاء — المرحلة 5: الوكيل والحلقة والسيد والسجل
والرسائل والملكية، كلها ملك NEXUS، والأنماط المرجعية من المستودعات
المسحوبة موثّقة في سجل التكامل.

Stdlib only.
"""

from .agent import (
    AGENT_FIELDS,
    MASTER_AGENT_ID,
    Agent,
    AgentError,
    MemoryPolicy,
    ModelPolicy,
    VerificationPolicy,
    new_agent_id,
)
from .loop import (
    DECISION_ACTIONS,
    LOOP_PHASES,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_MAX_TURNS,
    AgentLoop,
    Decision,
    DecisionParseError,
    InlineToolSink,
    LoopError,
    LoopOutcome,
    LoopStep,
    ToolResult,
    ToolSink,
    VerifyVerdict,
    parse_decision,
)
from .master import (
    MasterAgent,
    MasterError,
    MasterParseError,
    MasterPlan,
    StepReport,
    SubtaskSpec,
    Understanding,
    Verdict,
    parse_plan,
    parse_understanding,
    parse_verdict,
)
from .messages import (
    AGENT_MESSAGE_FIELDS,
    BROADCAST_RECEIVER,
    MESSAGE_TYPES,
    AgentCommunicator,
    AgentMessage,
    CommunicationError,
    Evidence,
    MessageStatus,
    MessageType,
)
from .ownership import (
    OWNERSHIP_FIELDS,
    OwnershipEntry,
    OwnershipError,
    OwnershipManager,
    ResourceOwnedError,
)
from .registry import (
    REGISTRY_FILE,
    AgentRegistry,
    AgentRegistryError,
    roster_ids,
)

__all__ = [
    # §6.1
    "AGENT_FIELDS",
    "Agent",
    "AgentError",
    "MASTER_AGENT_ID",
    "MemoryPolicy",
    "ModelPolicy",
    "VerificationPolicy",
    "new_agent_id",
    # §6.2
    "AgentLoop",
    "DECISION_ACTIONS",
    "Decision",
    "DecisionParseError",
    "InlineToolSink",
    "LOOP_PHASES",
    "LoopError",
    "LoopOutcome",
    "LoopStep",
    "OUTCOME_COMPLETED",
    "OUTCOME_FAILED",
    "OUTCOME_MAX_TURNS",
    "ToolResult",
    "ToolSink",
    "VerifyVerdict",
    "parse_decision",
    # §6.3
    "MasterAgent",
    "MasterError",
    "MasterParseError",
    "MasterPlan",
    "StepReport",
    "SubtaskSpec",
    "Understanding",
    "Verdict",
    "parse_plan",
    "parse_understanding",
    "parse_verdict",
    # §6.4
    "REGISTRY_FILE",
    "AgentRegistry",
    "AgentRegistryError",
    "roster_ids",
    # §6.5
    "AGENT_MESSAGE_FIELDS",
    "AgentCommunicator",
    "AgentMessage",
    "BROADCAST_RECEIVER",
    "CommunicationError",
    "Evidence",
    "MESSAGE_TYPES",
    "MessageStatus",
    "MessageType",
    # §6.6
    "OWNERSHIP_FIELDS",
    "OwnershipEntry",
    "OwnershipError",
    "OwnershipManager",
    "ResourceOwnedError",
]
