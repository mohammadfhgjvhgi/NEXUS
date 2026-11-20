"""Agent Loop (Final Build Plan §6.2).

The execution cycle, verbatim from the plan::

    Observe
    → Context
    → Decide
    → Tool/Agent call
    → Observe
    → Verify
    → Continue

:class:`AgentLoop` drives exactly this seven-phase cycle for one §6.1
Agent working one task — and records a :class:`LoopStep` for *every*
phase of *every* turn, so the trace proves the literal order:

* **Observe** (1) — drain the agent's communicator mailbox (delegations,
  coordination, results) plus the pending observation from the previous
  act;
* **Context** — assemble the prompt: the agent's instructions and
  policies, the goal/directive, and the observations so far;
* **Decide** — one Model Manager call (the §6.1 model policy selects
  the model — explicit id or §5.7 routing) parsed by the strict
  :func:`parse_decision` contract; a malformed decision gets **one**
  corrective retry, then honest failure;
* **Tool/Agent call** — dispatch the decision: a tool call (through
  the :class:`ToolSink` seam — the Tool Router phase plugs in there),
  a delegation (a §6.5 ``task`` message to another agent), or a plain
  response; ownership-checked when the decision names a ``resource``
  (§6.6 — a conflict becomes a ``coordination`` message and a
  re-decide, never a silent overwrite);
* **Observe** (2) — the act's outcome joins the observation stream;
* **Verify** — every turn: a light act-integrity check (last tool act
  completed, no failed act left unobserved), and — when the agent
  decides ``done`` — the full verification gate (verifier callable or
  the structural policy check) with bounded repairs;
* **Continue** — exit on completed/failed/turn-budget, else next turn.

Events (all canonical §2.2): ``agent.started`` / ``agent.completed`` /
``agent.failed`` around the run; ``tool.called`` / ``tool.completed`` /
``tool.failed`` per tool act. No new names — the 28-event registry
stays authoritative and binding.

The Model Manager, Event Bus and Task objects are injected — this
module imports nothing from ``nexus.core`` at runtime (§0.4 seams,
zero import cycles).

حلقة الوكيل — الدورة السباعية حرفيًا وكل مرحلة مسجّلة في الأثر؛
القرار عقد JSON صارم بمحاولة تصحيح واحدة، والتحقق بوابة بحد إصلاح.

Loop-shape reference: the langgraph Pregel superstep discipline
(studied in vendor-staging, Repository-Integration Round 2, MODE D —
zero imports, patterns only).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from ..events import EventBus, EventName
from ..models import GenerateRequest, ProviderError, RoutingRequest
from .agent import MASTER_AGENT_ID, Agent
from .messages import AgentCommunicator, AgentMessage, Evidence, MessageType
from .ownership import OwnershipManager, ResourceOwnedError

if TYPE_CHECKING:  # injected collaborators — annotation-only
    from ..core.session.models import Task
    from ..harness import Harness
    from ..models import ModelManager

logger = logging.getLogger("nexus.agents")

#: The §6.2 cycle, verbatim and in plan order (Observe appears before
#: and after the act — as written).
LOOP_PHASES: tuple[str, ...] = (
    "observe",
    "context",
    "decide",
    "act",
    "observe",
    "verify",
    "continue",
)

#: Decision actions (the §6.2 «Tool/Agent call» + outcomes).
DECISION_ACTIONS: tuple[str, ...] = (
    "respond",
    "call_tool",
    "delegate",
    "done",
    "failed",
)

#: Outcome statuses of a completed run.
OUTCOME_COMPLETED = "completed"
OUTCOME_FAILED = "failed"
OUTCOME_MAX_TURNS = "max_turns"

#: The strict decision protocol the model must answer with (the
#: documented NEXUS contract — one JSON object).
_DECISION_PROTOCOL = (
    "Answer with ONE JSON object and nothing else, using exactly this "
    'shape: {"action": "respond|call_tool|delegate|done|failed", '
    '"response": "<text for the user/master>", '
    '"tool": "<tool name, when action=call_tool>", '
    '"arguments": {<tool arguments>}, '
    '"delegate": "<target agent id, when action=delegate>", '
    '"message": "<delegation message>", '
    '"resource": "<resource the act modifies, if any>", '
    '"reason": "<why>", "confidence": <0.0..1.0>}'
)


class DecisionParseError(Exception):
    """The model's decision did not satisfy the protocol."""


class LoopError(Exception):
    """Agent-loop misuse (bad wiring, no model available…)."""


@dataclass(slots=True)
class Decision:
    """One parsed §6.2 decision."""

    action: str
    response: str = ""
    tool: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    delegate: str | None = None
    message: str = ""
    resource: str | None = None
    reason: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "response": self.response,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "delegate": self.delegate,
            "message": self.message,
            "resource": self.resource,
            "reason": self.reason,
            "confidence": self.confidence,
        }


def parse_decision(text: str) -> Decision:
    """Parse one model answer into a :class:`Decision` (pure function).

    Extracts the first balanced JSON object in the text (models may
    wrap the object in prose), validates the action enum and the
    per-action required keys, and clamps confidence to ``0..1``.
    Raises :class:`DecisionParseError` on any violation.
    """
    if not text or not text.strip():
        raise DecisionParseError("empty decision text")
    start = text.find("{")
    if start < 0:
        raise DecisionParseError("no JSON object in decision text")
    depth = 0
    end = -1
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        raise DecisionParseError("unbalanced JSON object in decision text")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DecisionParseError(f"invalid decision JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionParseError("decision JSON must be an object")
    action = payload.get("action")
    if action not in DECISION_ACTIONS:
        raise DecisionParseError(
            f"decision action must be one of {DECISION_ACTIONS}, got {action!r}"
        )
    response = str(payload.get("response") or "")
    tool = payload.get("tool")
    if action == "respond" and not response.strip():
        raise DecisionParseError("action 'respond' requires a non-empty response")
    if action == "call_tool":
        if not tool or not str(tool).strip():
            raise DecisionParseError("action 'call_tool' requires a tool name")
        tool = str(tool)
    elif tool is not None:
        raise DecisionParseError("'tool' is only valid with action 'call_tool'")
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, Mapping):
        raise DecisionParseError("'arguments' must be a JSON object")
    delegate = payload.get("delegate")
    if action == "delegate":
        if not delegate or not str(delegate).strip():
            raise DecisionParseError("action 'delegate' requires a target")
        delegate = str(delegate)
    elif delegate is not None:
        raise DecisionParseError("'delegate' is only valid with action 'delegate'")
    resource = payload.get("resource")
    if resource is not None and not str(resource).strip():
        resource = None
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError) as exc:
        raise DecisionParseError(f"invalid confidence: {exc}") from exc
    return Decision(
        action=action,
        response=response,
        tool=tool,
        arguments=dict(arguments),
        delegate=delegate,
        message=str(payload.get("message") or ""),
        resource=str(resource) if resource else None,
        reason=str(payload.get("reason") or ""),
        confidence=min(1.0, max(0.0, confidence)),
    )


# -------------------------------------------------------------- tool sink


@dataclass(slots=True)
class ToolResult:
    """Outcome of one tool act (the seam the Tool Router fills later)."""

    ok: bool
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "output": self.output, "error": self.error}


class ToolSink:
    """The NEXUS-owned tool-call seam (§6.2 «Tool call»).

    Phase 5 ships :class:`InlineToolSink` — callables registered by
    name, each returning a string (or raising, which becomes an honest
    failed result). The Tool Registry / Tool Router phases replace the
    sink behind this exact interface; the loop never learns which.
    """

    def call(
        self, name: str, arguments: Mapping[str, Any], *, task_id: str
    ) -> ToolResult:
        raise NotImplementedError

    def available(self) -> tuple[str, ...]:
        raise NotImplementedError


class InlineToolSink(ToolSink):
    """In-process tool handlers (tests + early runtime)."""

    def __init__(
        self,
        handlers: Mapping[str, Callable[[Mapping[str, Any]], str]] | None = None,
    ) -> None:
        self._handlers: dict[str, Callable[[Mapping[str, Any]], str]] = dict(
            handlers or {}
        )

    def register(self, name: str, handler: Callable[[Mapping[str, Any]], str]) -> None:
        self._handlers[name] = handler

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def call(
        self, name: str, arguments: Mapping[str, Any], *, task_id: str
    ) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResult(ok=False, error=f"unknown tool: {name!r}")
        try:
            return ToolResult(ok=True, output=str(handler(arguments)))
        except Exception as exc:  # noqa: BLE001 — a tool failure is data, not a crash
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------- verify verdict


@dataclass(slots=True)
class VerifyVerdict:
    """The §6.2 Verify gate outcome for one run."""

    passed: bool
    detail: str = ""
    checks: tuple[tuple[str, bool], ...] = ()


#: Verifier contract: (agent, response, evidence, observations) → verdict.
Verifier = Callable[[Agent, str, tuple[Evidence, ...], tuple[str, ...]], VerifyVerdict]


@dataclass(slots=True)
class LoopStep:
    """One recorded cycle step (audit trail for the harness)."""

    turn: int
    phase: str
    detail: str = ""


@dataclass(slots=True)
class LoopOutcome:
    """The end-of-run report of one agent's work."""

    agent_id: str
    task_id: str
    status: str
    turns: int
    response: str
    evidence: tuple[Evidence, ...] = ()
    confidence: float = 0.5
    trace: tuple[LoopStep, ...] = ()
    detail: str = ""

    @property
    def completed(self) -> bool:
        return self.status == OUTCOME_COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "status": self.status,
            "turns": self.turns,
            "response": self.response,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "trace": [
                {"turn": step.turn, "phase": step.phase, "detail": step.detail}
                for step in self.trace
            ],
            "detail": self.detail,
        }


# ------------------------------------------------------------------- loop


class AgentLoop:
    """Drives the §6.2 cycle for one agent on one task."""

    def __init__(
        self,
        *,
        agent: Agent,
        model_manager: ModelManager,
        communicator: AgentCommunicator,
        ownership: OwnershipManager,
        bus: EventBus,
        tools: ToolSink | None = None,
        verifier: Verifier | None = None,
        max_turns: int = 8,
        session_id: str | None = None,
        harness: Harness | None = None,
    ) -> None:
        if max_turns < 1:
            raise LoopError(f"max_turns must be >= 1, got {max_turns}")
        self._agent = agent
        self._models = model_manager
        self._communicator = communicator
        self._ownership = ownership
        self._bus = bus
        self._tools = tools
        self._verifier = verifier
        self._max_turns = max_turns
        self._session_id = session_id
        self._harness = harness

    # ---------------------------------------------------------------- run

    def run(
        self, task: Task, *, goal: str | None = None, instruction: str | None = None
    ) -> LoopOutcome:
        """Run the §6.2 cycle until DONE/FAILED or the turn budget ends."""
        task_id = task.id
        directive = (instruction or goal or task.goal).strip()
        trace: list[LoopStep] = []
        evidence: list[Evidence] = []
        observations: list[str] = []
        response = ""
        status = OUTCOME_FAILED
        detail = ""
        decision: Decision | None = None
        turn = 0
        repairs_left = self._agent.verification.max_repairs

        self._publish(
            EventName.AGENT_STARTED,
            task_id,
            {"agent_id": self._agent.id, "role": self._agent.role},
        )
        try:
            while True:
                turn += 1

                # 1 — OBSERVE (cycle phase 1: the mailbox)
                inbox = self._communicator.receive(self._agent.id)
                for message in inbox:
                    observations.append(self._render_message(message))
                    evidence.extend(message.evidence)
                trace.append(LoopStep(turn, LOOP_PHASES[0], f"{len(inbox)} message(s)"))

                # 2 — CONTEXT (cycle phase 2)
                prompt = self._build_context(directive, observations)
                trace.append(LoopStep(turn, LOOP_PHASES[1], f"prompt {len(prompt)} chars"))

                # 3 — DECIDE (cycle phase 3)
                decision = self._decide(prompt)
                trace.append(LoopStep(turn, LOOP_PHASES[2], f"action={decision.action}"))

                # 4 — TOOL / AGENT CALL (cycle phase 4)
                act_observation, act_evidence = self._act(decision, task_id)
                if decision.action == "respond":
                    response = decision.response
                trace.append(LoopStep(turn, LOOP_PHASES[3], decision.action))

                # 5 — OBSERVE (cycle phase 5: the act outcome)
                observations.append(act_observation)
                evidence.extend(act_evidence)
                trace.append(LoopStep(turn, LOOP_PHASES[4], "act observed"))

                # 6 — VERIFY (cycle phase 6 — every turn)
                if decision.action == "done":
                    response = decision.response or response
                    verdict = self._verify_gate(response, evidence, observations)
                    trace.append(
                        LoopStep(
                            turn,
                            LOOP_PHASES[5],
                            f"gate passed={verdict.passed}"
                            + (f" ({verdict.detail})" if verdict.detail else ""),
                        )
                    )
                    if verdict.passed:
                        status = OUTCOME_COMPLETED
                        detail = verdict.detail or "verification gate passed"
                        break
                    if repairs_left > 0:
                        repairs_left -= 1
                        observations.append(
                            "VERIFICATION FAILED — repair the work and answer "
                            f"again. Detail: {verdict.detail or 'unspecified'}"
                        )
                        trace.append(LoopStep(turn, LOOP_PHASES[6], "repair turn"))
                        continue
                    status = OUTCOME_FAILED
                    detail = (
                        f"verification gate failed; repairs exhausted "
                        f"({verdict.detail})"
                    )
                    break
                act_failed = act_observation.startswith("tool ") and " failed" in act_observation
                conflict = act_observation.startswith("ownership ")
                trace.append(
                    LoopStep(
                        turn,
                        LOOP_PHASES[5],
                        "act integrity: conflict" if conflict else
                        ("act integrity: tool failed" if act_failed else "act integrity: ok"),
                    )
                )
                if decision.action == "failed":
                    status = OUTCOME_FAILED
                    detail = decision.reason or "agent declared failure"
                    response = decision.response or response
                    break

                # 7 — CONTINUE (cycle phase 7)
                if turn >= self._max_turns:
                    status = OUTCOME_MAX_TURNS
                    detail = f"turn budget exhausted ({self._max_turns})"
                    break
                trace.append(LoopStep(turn, LOOP_PHASES[6], "next turn"))
        except (LoopError, DecisionParseError, ProviderError) as exc:
            status = OUTCOME_FAILED
            detail = f"{type(exc).__name__}: {exc}"
        finally:
            self._release_resources()

        confidence = (
            decision.confidence
            if decision is not None and decision.action in ("done", "respond")
            else 0.5
        )
        outcome = LoopOutcome(
            agent_id=self._agent.id,
            task_id=task_id,
            status=status,
            turns=turn,
            response=response,
            evidence=tuple(evidence),
            confidence=confidence,
            trace=tuple(trace),
            detail=detail,
        )
        if status == OUTCOME_COMPLETED:
            self._publish(
                EventName.AGENT_COMPLETED,
                task_id,
                {"agent_id": self._agent.id, "turns": turn},
            )
        else:
            self._publish(
                EventName.AGENT_FAILED,
                task_id,
                {"agent_id": self._agent.id, "status": status, "detail": detail},
            )
        # §6.3 «يستقبل النتائج» — the result message to the Master Agent.
        self._communicator.send(
            AgentMessage.create(
                task_id=task_id,
                sender=self._agent.id,
                receiver=MASTER_AGENT_ID,
                type=MessageType.RESULT
                if status == OUTCOME_COMPLETED
                else MessageType.ERROR,
                data={
                    "status": status,
                    "response": response,
                    "turns": turn,
                    "detail": detail,
                },
                evidence=tuple(evidence),
                confidence=confidence,
            )
        )
        return outcome

    # ------------------------------------------------------------ internals

    def _decide(self, prompt: str) -> Decision:
        """One model call + strict parse, with a single corrective retry."""
        request = self._model_request(prompt, self._system_prompt())
        attempts = 0
        last_error: DecisionParseError | None = None
        while attempts < 2:
            attempts += 1
            result = self._models.generate(request)
            try:
                return parse_decision(result.text)
            except DecisionParseError as exc:
                last_error = exc
                request = replace(
                    request,
                    prompt=(
                        f"{request.prompt}\n\nYour previous answer violated "
                        f"the decision protocol ({exc}). Answer again with "
                        "ONE valid JSON object only."
                    ),
                )
        raise DecisionParseError(
            f"decision protocol violated twice: {last_error}"
        ) from last_error

    def _model_request(self, prompt: str, system: str) -> GenerateRequest:
        """Build the generation request honoring the §6.1 model policy."""
        policy = self._agent.model_policy
        model_id = policy.model_id
        if not model_id:
            routing = self._models.select(
                RoutingRequest(
                    task_type=policy.task_type,
                    complexity=policy.complexity,
                )
            )
            if routing.selected_model_id is None:
                raise LoopError(
                    f"no model available for agent {self._agent.id} "
                    f"({routing.reason})"
                )
            model_id = routing.selected_model_id
        return GenerateRequest(
            model_id=model_id,
            prompt=prompt,
            system=system,
            max_tokens=policy.max_tokens,
            temperature=policy.temperature,
            auto_load=True,
        )

    def _act(
        self, decision: Decision, task_id: str
    ) -> tuple[str, tuple[Evidence, ...]]:
        """Dispatch one decision → (observation, evidence)."""
        if decision.action == "respond":
            return (f"responded: {decision.response}", ())
        if decision.action == "done":
            return (f"done: {decision.response}", ())
        if decision.action == "delegate":
            target = decision.delegate or ""
            self._communicator.send(
                AgentMessage.create(
                    task_id=task_id,
                    sender=self._agent.id,
                    receiver=target,
                    type=MessageType.TASK,
                    data={"instruction": decision.message or decision.response},
                    confidence=decision.confidence,
                )
            )
            return (f"delegated to {target}: {decision.message}", ())
        if decision.action == "call_tool":
            assert decision.tool is not None
            return self._call_tool(decision, task_id)
        return (f"unknown action {decision.action!r}", ())

    def _call_tool(
        self, decision: Decision, task_id: str
    ) -> tuple[str, tuple[Evidence, ...]]:
        assert decision.tool is not None
        tool = decision.tool
        hooks = self._harness.hooks if self._harness is not None else None
        if hooks is not None:
            from ..harness import HookContext

            context = HookContext(
                point="pre_tool_call",
                agent_id=self._agent.id,
                task_id=task_id,
                tool=tool,
                arguments=dict(decision.arguments),
            )
            if not hooks.fire("pre_tool_call", context):
                return (
                    f"tool {tool!r} blocked by harness pre_tool_call hook — "
                    "choose another action",
                    (),
                )
        if tool not in self._agent.tools:
            return (
                f"tool {tool!r} refused: not in this agent's tool list "
                f"({', '.join(self._agent.tools) or 'none'})",
                (),
            )
        sink = self._tools
        if sink is None or tool not in sink.available():
            return (f"tool {tool!r} unavailable in this runtime", ())
        if decision.resource is not None:
            try:
                self._ownership.acquire(
                    decision.resource, owner=self._agent.id, task_id=task_id
                )
            except ResourceOwnedError as exc:
                # §6.6 — coordination, never a silent overwrite: notify the
                # current owner and re-decide next turn.
                self._communicator.send(
                    AgentMessage.create(
                        task_id=task_id,
                        sender=self._agent.id,
                        receiver=exc.owner,
                        type=MessageType.COORDINATION,
                        data={
                            "resource": exc.resource,
                            "request": "release or coordinate",
                            "held_by": exc.owner,
                        },
                    )
                )
                return (
                    f"ownership conflict on {exc.resource!r} (owner "
                    f"{exc.owner!r}) — coordination requested; do not modify",
                    (),
                )
        self._publish(
            EventName.TOOL_CALLED,
            task_id,
            {
                "agent_id": self._agent.id,
                "tool": tool,
                "resource": decision.resource,
            },
        )
        result = sink.call(tool, decision.arguments, task_id=task_id)
        if hooks is not None:
            from ..harness import HookContext

            hooks.fire(
                "post_tool_call",
                HookContext(
                    point="post_tool_call",
                    agent_id=self._agent.id,
                    task_id=task_id,
                    tool=tool,
                    detail={"ok": result.ok},
                ),
            )
        if result.ok:
            self._publish(
                EventName.TOOL_COMPLETED,
                task_id,
                {"agent_id": self._agent.id, "tool": tool},
            )
            return (
                f"tool {tool} completed: {result.output}",
                (Evidence(kind="tool_output", source=tool, detail=result.output),),
            )
        self._publish(
            EventName.TOOL_FAILED,
            task_id,
            {"agent_id": self._agent.id, "tool": tool, "error": result.error},
        )
        return (f"tool {tool} failed: {result.error}", ())

    def _verify_gate(
        self,
        response: str,
        evidence: list[Evidence],
        observations: list[str],
    ) -> VerifyVerdict:
        """The full §6.2 Verify gate (agent claims DONE)."""
        policy = self._agent.verification
        if not policy.required:
            return VerifyVerdict(passed=True, detail="verification not required")
        if self._verifier is not None:
            return self._verifier(
                self._agent, response, tuple(evidence), tuple(observations)
            )
        checks: list[tuple[str, bool]] = []
        checks.append(("response produced", bool(response.strip())))
        checks.append(
            ("evidence present", bool(evidence) or not policy.criteria)
        )
        for criterion in policy.criteria:
            hits = any(
                criterion.lower() in (item.detail + item.source).lower()
                for item in evidence
            )
            checks.append((criterion, hits))
        failed = [name for name, ok in checks if not ok]
        return VerifyVerdict(
            passed=not failed,
            detail="all structural checks passed" if not failed else f"failed: {failed}",
            checks=tuple(checks),
        )

    def _build_context(self, directive: str, observations: list[str]) -> str:
        parts = [f"GOAL: {directive}"]
        if observations:
            parts.append("OBSERVATIONS SO FAR:")
            parts.extend(f"- {item}" for item in observations[-12:])
        if self._harness is not None:
            section = self._harness.context_section(
                self._agent, directive, observations=observations
            )
            if section:
                parts.append("HARNESS POLICY (binding):")
                parts.append(section)
        parts.append("Decide the next action now, as ONE JSON object.")
        return "\n".join(parts)

    def _system_prompt(self) -> str:
        agent = self._agent
        parts = [agent.instructions]
        if agent.tools:
            parts.append(f"Available tools: {', '.join(agent.tools)}.")
        parts.append(_DECISION_PROTOCOL)
        return "\n".join(parts)

    def _render_message(self, message: AgentMessage) -> str:
        body = (
            message.data.get("instruction")
            or message.data.get("response")
            or message.data.get("request")
            or ""
        )
        return (
            f"message from {message.sender} ({message.type}): "
            f"{body or message.type}"
        )

    def _release_resources(self) -> None:
        released = self._ownership.release_owner(self._agent.id)
        if released:
            logger.debug(
                "agent %s released %d resource(s) at loop end",
                self._agent.id,
                len(released),
            )

    def _publish(
        self, name: EventName, task_id: str, payload: Mapping[str, Any]
    ) -> None:
        self._bus.publish(
            name,
            payload=dict(payload),
            source="nexus.agents.loop",
            task_id=task_id,
            session_id=self._session_id,
        )
