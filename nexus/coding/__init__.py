"""NEXUS Coding Agent package (New Plan §15 — PHASE 15).

NEXUS becomes a real Developer Agent: it stops *understanding* code
(phase 14) and starts *changing* it — analyzed, planned, edited,
built, tested, debugged and reviewed through one contract.

========================  ======================================  ==========
Component                 Plan source                             Module
========================  ======================================  ==========
Coding Agent Contract     §15.1 (7 operations, one dispatcher)    contracts · operations
Specialist Agents (10)    §15.2 (registry-backed specs)           specialists
OpenHands reference       §15.3 (MODE B/D — zero imports)         vendor-staging/phase-15
OpenCode reference        §15.4 (MODE B/D — zero imports)         vendor-staging/phase-15
Cline reference           §15.5 (MODE D session architecture)     contracts · session
Coding Loop (8 stages)    §15.6 (Understand → … → Review)         loop
========================  ======================================  ==========

The §15.6 loop, verbatim::

    Understand → Plan → Edit → Build → Test → Debug → Retest → Review

drives the §15.1 operations (:class:`~nexus.coding.operations.CodingAgent`)
through the §2.4 task machine, publishes only the canonical §2.2
events, and keeps the Debug→Retest cycle bounded
(``max_debug_cycles`` — honest REJECTED verdicts, never spins).

The three studied ecosystems (OpenHands · OpenCode · Cline) stayed
MODE B/D — patterns only, zero imports; ``vendor-staging/phase-15``
holds the audit trail. The §14 code-intelligence engine answers
``analyze``; the §13 learning store feeds ``debug``; the §7 harness
observation path is the probe target for ``test``.

وكيل البرمجة — عقد واحد بسبع عمليات، عشرة مختصين في السجل الحقيقي،
وحلقة من ثماني مراحل تنتهي دائمًا بحكم.

Stdlib only.
"""

from .contracts import (
    CODING_LOOP_STAGES,
    CODING_OPERATION_KINDS,
    LOOP_STAGE_ORDER,
    SPECIALIST_ROLES,
    AnalyzeSummary,
    CodingError,
    CodingLoopStage,
    CodingOperationKind,
    CodingSessionRecord,
    DebugFinding,
    DebugOutcome,
    EditAction,
    EditOutcome,
    FileDiff,
    InvalidCodingContractError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    PlanOutcome,
    PlanStep,
    ReviewCheck,
    ReviewOutcome,
    ReviewVerdict,
    RunOutcome,
    TestOutcome,
    ToolCallRecord,
    parse_edit_actions,
)
from .loop import (
    STAGE_TASK_STATES,
    CodingLoop,
    CodingLoopError,
    CodingLoopResult,
    StageTrace,
)
from .operations import CodingAgent
from .session import (
    SESSION_STATUSES,
    CodingSession,
    CodingSessionError,
    discover_task_commits,
    link_task_commits,
    new_session_id,
)
from .specialists import (
    CODING_SPECIALIST_SPECS,
    CODING_SPECIALISTS,
    SpecialistSpec,
    register_coding_specialists,
    specialist_agent,
    specialists_for_stage,
)

__all__ = [
    # §15.1 contract (contracts)
    "CODING_OPERATION_KINDS",
    "CodingOperationKind",
    "OperationRequest",
    "OperationResult",
    "OperationStatus",
    "EditAction",
    "PlanStep",
    "DebugFinding",
    "ReviewCheck",
    "ReviewVerdict",
    "ToolCallRecord",
    "CodingSessionRecord",
    "AnalyzeSummary",
    "PlanOutcome",
    "EditOutcome",
    "FileDiff",
    "RunOutcome",
    "TestOutcome",
    "DebugOutcome",
    "ReviewOutcome",
    "parse_edit_actions",
    "CodingError",
    "InvalidCodingContractError",
    # §15.2 specialists
    "SPECIALIST_ROLES",
    "CODING_SPECIALISTS",
    "CODING_SPECIALIST_SPECS",
    "SpecialistSpec",
    "specialist_agent",
    "register_coding_specialists",
    "specialists_for_stage",
    # §15.6 loop
    "CODING_LOOP_STAGES",
    "LOOP_STAGE_ORDER",
    "CodingLoopStage",
    "STAGE_TASK_STATES",
    "CodingLoop",
    "CodingLoopError",
    "CodingLoopResult",
    "StageTrace",
    # the agent + the session
    "CodingAgent",
    "CodingSession",
    "CodingSessionError",
    "SESSION_STATUSES",
    "new_session_id",
    "discover_task_commits",
    "link_task_commits",
]
