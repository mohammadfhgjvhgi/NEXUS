"""The harness contract (Spec §41) — what the model receives and returns.

The Agent Harness is the layer that gives the model::

    Harness inputs (Spec §41, verbatim, seven)
    ├── context      — the assembled working context (goal + harness sections)
    ├── tools        — the tool manifest available this turn
    ├── memory       — the memory snapshot per the agent's §6.1 policy
    ├── task_state   — the §2.4 task machine position
    ├── rules        — the compiled §7.1 rule section
    ├── skills       — the matched §7.1 skill section
    └── observations — what the loop has seen so far

and expects back::

    Harness outputs (Spec §41, verbatim, four)
    ├── action     — continue / respond / done / …
    ├── tool_call  — the tool name + arguments (when acting)
    ├── delegation — the sub-agent hand-off (when delegating)
    └── decision   — the parsed §6.2 decision record

:class:`Harness` is the assembler: it merges the rule section, the
matched skills, the active goals and the memory snapshot into the
loop's context, and maps a §6.2 :class:`~nexus.agents.loop.Decision`
into the §41 output record. This is the §275 Super-Harness seam —
NEXUS-owned adapters, external ecosystems studied in staging and
never imported.

The memory snapshot honors the §6.1 memory policy against the §2.3
ladder (user / conversation / task): the Memory *System* is Plan
§13/PHASE 12 — until then the harness reports the policy view (what
the agent may read/write, retention level) instead of inventing
content. Honest placeholders, not fake memory.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .goals import GoalStore
from .hooks import HarnessHooks
from .rules import RuleSet
from .skills import SkillLibrary

if TYPE_CHECKING:  # pragma: no cover - import cycle guard (docs §6.2)
    from ..agents.agent import Agent
    from ..agents.loop import Decision, ToolSink
    from ..core.session.models import Task

logger = logging.getLogger("nexus.harness")

#: Spec §41 — the seven model inputs, verbatim (harness-provable).
HARNESS_INPUT_FIELDS: tuple[str, ...] = (
    "context",
    "tools",
    "memory",
    "task_state",
    "rules",
    "skills",
    "observations",
)

#: Spec §41 — the four model outputs, verbatim (harness-provable).
HARNESS_OUTPUT_FIELDS: tuple[str, ...] = (
    "action",
    "tool_call",
    "delegation",
    "decision",
)

_MEMORY_NOTE = (
    "memory system lands in a later phase — the §6.1 policy view is "
    "reported verbatim (namespaces + retention), never fabricated content"
)


@dataclass(slots=True)
class HarnessInputs:
    """What the model receives this turn (Spec §41, seven fields)."""

    context: str = ""
    tools: tuple[str, ...] = ()
    memory: dict[str, Any] = field(default_factory=dict)
    task_state: str = ""
    rules: str = ""
    skills: str = ""
    observations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context,
            "tools": list(self.tools),
            "memory": dict(self.memory),
            "task_state": self.task_state,
            "rules": self.rules,
            "skills": self.skills,
            "observations": list(self.observations),
        }


@dataclass(slots=True)
class HarnessOutputs:
    """What the model returns (Spec §41, four fields)."""

    action: str = ""
    tool_call: dict[str, Any] = field(default_factory=dict)
    delegation: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "tool_call": dict(self.tool_call),
            "delegation": dict(self.delegation),
            "decision": dict(self.decision),
        }


class Harness:
    """The §41 assembler + the §275 Super-Harness seam.

    Collaborators are injected (skills, rules, goals) and every one is
    optional — a harness with empty libraries stays silent. The loop
    asks for ``context_section``; the master asks for ``inputs`` /
    ``outputs``; nothing imports the vendored reference projects.
    """

    def __init__(
        self,
        *,
        skills: SkillLibrary | None = None,
        rules: RuleSet | None = None,
        goals: GoalStore | None = None,
        hooks: HarnessHooks | None = None,
    ) -> None:
        self._skills = skills
        self._rules = rules
        self._goals = goals
        self._hooks = hooks

    # ------------------------------------------------------------- inputs

    @property
    def skills(self) -> SkillLibrary | None:
        return self._skills

    @property
    def rules(self) -> RuleSet | None:
        return self._rules

    @property
    def goals(self) -> GoalStore | None:
        return self._goals

    @property
    def hooks(self) -> HarnessHooks | None:
        return self._hooks

    def memory_snapshot(self, agent: Agent) -> dict[str, Any]:
        """The §6.1 policy view (read/write namespaces + retention)."""
        policy = agent.memory_policy
        return {
            "read_namespaces": list(policy.read),
            "write_namespaces": list(policy.write),
            "retention": policy.retention,
            "note": _MEMORY_NOTE,
        }

    def build_inputs(
        self,
        agent: Agent,
        task: Task,
        *,
        directive: str = "",
        observations: Sequence[str] = (),
        tools: ToolSink | None = None,
    ) -> HarnessInputs:
        """Assemble the §41 inputs for one turn."""
        goal_text = (directive or task.goal).strip()
        skills_section = (
            self._skills.context_section(goal_text) if self._skills else ""
        )
        rules_section = (
            self._rules.context_section() if self._rules else ""
        )
        goals_section = (
            self._goals.context_section() if self._goals else ""
        )
        sections = [part for part in (rules_section, skills_section, goals_section) if part]
        context = goal_text if not sections else "\n\n".join([goal_text, *sections])
        tool_names = tuple(tools.available()) if tools is not None else tuple(agent.tools)
        return HarnessInputs(
            context=context,
            tools=tool_names,
            memory=self.memory_snapshot(agent),
            task_state=task.state.value if hasattr(task.state, "value") else str(task.state),
            rules=rules_section,
            skills=skills_section,
            observations=tuple(observations),
        )

    # ------------------------------------------------------------ outputs

    def parse_outputs(self, decision: Decision) -> HarnessOutputs:
        """Map a §6.2 decision into the §41 output record."""
        tool_call: dict[str, Any] = {}
        if decision.action == "call_tool":
            tool_call = {
                "name": decision.tool or "",
                "arguments": dict(decision.arguments),
            }
        delegation: dict[str, Any] = {}
        if decision.action == "delegate":
            delegation = {
                "to": decision.delegate or "",
                "message": decision.message,
            }
        return HarnessOutputs(
            action=decision.action,
            tool_call=tool_call,
            delegation=delegation,
            decision={
                "response": decision.response,
                "confidence": decision.confidence,
                "reason": decision.reason,
            },
        )

    # ------------------------------------------------------------ context

    def context_section(
        self, agent: Agent, directive: str, *,
        observations: Sequence[str] = (),
    ) -> str:
        """The harness contribution to the §6.2 CONTEXT phase.

        Rules always ship (they are binding); matching skills and the
        active goals follow. An empty harness contributes nothing —
        the §6.2 prompt is untouched and every Phase-5 behavior is
        preserved verbatim (the regression proves it).
        """
        sections: list[str] = []
        if self._rules is not None:
            rules_section = self._rules.context_section()
            if rules_section:
                sections.append(rules_section)
        if self._skills is not None:
            skills_section = self._skills.context_section(directive)
            if skills_section:
                sections.append(skills_section)
        if self._goals is not None:
            goals_section = self._goals.context_section()
            if goals_section:
                sections.append(goals_section)
        if not sections:
            return ""
        return "\n\n".join(sections)
