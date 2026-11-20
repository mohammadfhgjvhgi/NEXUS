"""NEXUS Harness package (Final Build Plan §7 / Spec §41 — PHASE 6).

The harness is the layer that gives the model its context, tools,
memory view, task state, rules, skills and observations (Spec §41),
and maps its answers back to action / tool_call / delegation /
decision. It is assembled NEXUS-native from the adapted patterns of
five studied ecosystems (Plan §7.1–§7.5, Super-Harness §275):

========================  ======================================  ==========
Component                 Pattern source (MODE)                   Module
========================  ======================================  ==========
Skills                    ECC SKILL.md discipline (B)            skills
Rules                     ECC rule organization (B)              rules
Hooks (8 points)          ECC hooks + Cline core hooks (B)       hooks
Session lifecycle         Cline stateful-core sessions (B)       session
Checkpoints + durability  LangGraph checkpoint layer (A/B)       checkpoint
Goals + heartbeats        Prime Agent long-horizon (D/B)         goals
§41 input/output contract Spec §41 (NEXUS-owned)                 context
========================  ======================================  ==========

Nothing imports a vendored repository — the §0.4/§0.5 rules hold
(the harness is NEXUS-owned; the references live in
``vendor-staging`` and their lessons are baked into these shapes).
All persistence uses the atomic temp+replace discipline; every event
published is one of the 28 canonical §2.2 names.

طبقة الـHarness — العقد §41 (سبع مدخلات وأربع مخرجات) بأمثلة
المستودعات الخمسة مُكيَّفة بأشكال NEXUS خالصة.

Stdlib only.
"""

from .checkpoint import CHECKPOINT_FIELDS, Checkpoint, CheckpointStore, Durability
from .context import (
    HARNESS_INPUT_FIELDS,
    HARNESS_OUTPUT_FIELDS,
    Harness,
    HarnessInputs,
    HarnessOutputs,
)
from .goals import GOAL_FIELDS, GOAL_STATUSES, Goal, GoalStore, Heartbeat
from .hooks import HOOK_POINTS, VETO_POINTS, HarnessHooks, HookContext
from .rules import RULE_FIELDS, Rule, RuleSet
from .session import (
    SESSION_FIELDS,
    SESSION_STATUSES,
    SESSION_TRANSITIONS,
    AgentSession,
    SessionTracker,
    SessionTransitionError,
)
from .skills import SKILL_FIELDS, Skill, SkillLibrary

__all__ = [
    # skills (§7.1 — ECC pattern)
    "SKILL_FIELDS",
    "Skill",
    "SkillLibrary",
    # rules (§7.1 — ECC pattern)
    "RULE_FIELDS",
    "Rule",
    "RuleSet",
    # hooks (§7.1/§7.2 — ECC + Cline pattern)
    "HOOK_POINTS",
    "VETO_POINTS",
    "HarnessHooks",
    "HookContext",
    # session (§7.2 — Cline pattern)
    "SESSION_FIELDS",
    "SESSION_STATUSES",
    "SESSION_TRANSITIONS",
    "AgentSession",
    "SessionTracker",
    "SessionTransitionError",
    # checkpoint (§7.3 — LangGraph pattern)
    "CHECKPOINT_FIELDS",
    "Checkpoint",
    "CheckpointStore",
    "Durability",
    # goals (§7.4 — Prime Agent pattern)
    "GOAL_FIELDS",
    "GOAL_STATUSES",
    "Goal",
    "GoalStore",
    "Heartbeat",
    # the §41 contract
    "HARNESS_INPUT_FIELDS",
    "HARNESS_OUTPUT_FIELDS",
    "Harness",
    "HarnessInputs",
    "HarnessOutputs",
]
