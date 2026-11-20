"""Master Agent (Final Build Plan §6.3).

The seven behaviors, verbatim from the plan:

* يتعامل مع المستخدم      — :meth:`MasterAgent.handle` is the user-facing
                              entry: the Task (goal + prompt) is the user's
                              ask, routed through the conversation flow;
* يفهم الهدف              — ANALYZING: one model call produces the goal
                              understanding (requirements + focus);
* يوزع العمل              — PLANNING: one model call decomposes the goal
                              into subtasks, which land on the §2.5
                              ``task.plan.steps`` (PlanStep records — the
                              persisted plan field), each delegated to a
                              matching registered agent (§6.4 role
                              discovery; no match → the master executes
                              the step itself);
* يتابع Agents            — the master's mailbox receives every §6.5
                              progress/result/error message the loops send;
* يستقبل النتائج          — RESULT messages carry evidence + confidence;
* يقرر الاستمرار          — the continuation decision: failed steps get
                              bounded repair rounds (step re-runs); the
                              master proceeds to verification when every
                              step was worked (DONE, or honestly failed
                              after exhausting repairs);
* يقرر الوصول إلى Verification — VERIFYING: the model verdict is mapped
                              onto the §2.5 ``task.verification`` record
                              (VerificationCheck list) — pass →
                              ``task.completed`` (engine.complete), fail →
                              bounded REPAIRING rounds, exhausted →
                              COMPLETED with ``success=False`` (the 13-state
                              machine is honored: completion only ever
                              passes through VERIFYING).

Task-state choreography (the §2.4 machine, driven via the injected
TaskEngine): ``CREATED → ANALYZING → PLANNING → EXECUTING → VERIFYING
→ COMPLETED`` with ``REPAIRING`` loops, every event from the canonical
§2.2 set (``task.*`` via the engine, ``agent.*`` via the loops,
``verification.started/passed/failed`` for the gate).

The §2.5 ``task.agents`` list records every agent that worked the
task; agent slots honor the ResourceManager budget
(``agents.max_parallel``) — the master registers each working agent
and releases it at teardown.

Model contracts (strict JSON, one corrective retry each — the §6.2
discipline):

* understanding — ``{"understanding": str, "requirements": [str]}``;
* plan — ``{"subtasks": [{"description": str, "role": str?}],
           "verification_criteria": [str]}``;
* verdict — ``{"verdict": "pass"|"fail", "summary": str,
               "checks": [{"name": str, "passed": bool, "detail": str?}]}``.

Honesty rules: a model failure at understanding/plan/verdict fails
the task with a recorded error (no invented understanding); a failed
step fails honestly into the repair ladder.

Import note (mirrors the ``nexus.core.engine`` ``__init__`` docstring
discipline): this module imports ``nexus.core`` vocabulary **lazily,
inside the methods that use it** — ``nexus.core.config.runtime``
imports ``nexus.agents`` at module scope, so a top-level core import
here would create a partially-initialized-module cycle when
``nexus.agents`` is imported first. Injected collaborators
(TaskEngine, ModelManager…) stay type-only.

الوكيل الرئيسي — السلوكيات السبع حرفيًا، يقود آلة الحالات الثلاث
عشرة عبر TaskEngine، والتحقق من بوابة Verification مسجّل في المهمة.

Delegation-flow reference: the deepagents subagent middleware
(studied in vendor-staging, Repository-Integration Round 2, MODE D —
zero imports, patterns only).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..events import EventBus, EventName
from ..harness import Harness, HookContext
from ..models import GenerateRequest, ProviderError, RoutingRequest
from .agent import MASTER_AGENT_ID, Agent
from .loop import AgentLoop, LoopOutcome, ToolSink, Verifier
from .messages import AgentCommunicator, AgentMessage, MessageType
from .ownership import OwnershipManager
from .registry import AgentRegistry

if TYPE_CHECKING:  # injected collaborators — annotation-only
    from ..core.engine.machine import TaskEngine
    from ..core.session.models import Task
    from ..models import ModelManager
    from ..resources import ResourceManager

logger = logging.getLogger("nexus.agents")

#: Master model-call protocols (strict JSON, documented contracts).
_UNDERSTANDING_PROTOCOL = (
    "Answer with ONE JSON object only: "
    '{"understanding": "<one-paragraph understanding of the goal>", '
    '"requirements": ["<requirement>", ...]}'
)

_PLAN_PROTOCOL = (
    "Answer with ONE JSON object only: "
    '{"subtasks": [{"description": "<concrete step>", "role": "<agent role>"}, ...], '
    '"verification_criteria": ["<checkable criterion>", ...]}'
)

_VERDICT_PROTOCOL = (
    "Answer with ONE JSON object only: "
    '{"verdict": "pass"|"fail", "summary": "<one paragraph>", '
    '"checks": [{"name": "<criterion>", "passed": true|false, "detail": "<why>"}]}'
)


class MasterError(Exception):
    """Master-agent misuse (wrong state, wiring problems)."""


class MasterParseError(Exception):
    """A master model call violated its JSON contract twice."""


@dataclass(slots=True)
class Understanding:
    """The §6.3 goal understanding («يفهم الهدف»)."""

    understanding: str
    requirements: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "understanding": self.understanding,
            "requirements": list(self.requirements),
        }


@dataclass(slots=True)
class SubtaskSpec:
    """One planned subtask («يوزع العمل») before assignment."""

    description: str
    role: str | None = None


@dataclass(slots=True)
class MasterPlan:
    """The decomposed work + the verification criteria for the gate."""

    subtasks: tuple[SubtaskSpec, ...] = ()
    verification_criteria: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtasks": [
                {"description": s.description, "role": s.role} for s in self.subtasks
            ],
            "verification_criteria": list(self.verification_criteria),
        }


@dataclass(slots=True)
class Verdict:
    """The §6.3 verification decision («يقرر الوصول إلى Verification»)."""

    verdict: str  # "pass" | "fail"
    summary: str = ""
    checks: tuple[tuple[str, bool, str], ...] = ()  # (name, passed, detail)

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "checks": [
                {"name": n, "passed": p, "detail": d} for n, p, d in self.checks
            ],
        }


# ------------------------------------------------------------ pure parsers


def _extract_json(text: str) -> dict[str, Any]:
    """First balanced JSON object in the text (prose-tolerant)."""
    if not text or not text.strip():
        raise MasterParseError("empty model answer")
    start = text.find("{")
    if start < 0:
        raise MasterParseError("no JSON object in model answer")
    depth = 0
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
                try:
                    payload = json.loads(text[start : index + 1])
                except json.JSONDecodeError as exc:
                    raise MasterParseError(f"invalid JSON: {exc}") from exc
                if not isinstance(payload, dict):
                    raise MasterParseError("model answer must be a JSON object")
                return payload
    raise MasterParseError("unbalanced JSON object in model answer")


def parse_understanding(text: str) -> Understanding:
    """Parse the understanding contract (pure)."""
    payload = _extract_json(text)
    understanding = str(payload.get("understanding") or "").strip()
    if not understanding:
        raise MasterParseError("'understanding' must be a non-empty string")
    requirements = payload.get("requirements") or []
    if not isinstance(requirements, list):
        raise MasterParseError("'requirements' must be a list")
    return Understanding(
        understanding=understanding,
        requirements=tuple(str(item) for item in requirements),
    )


def parse_plan(text: str) -> MasterPlan:
    """Parse the plan contract (pure)."""
    payload = _extract_json(text)
    subtasks_raw = payload.get("subtasks")
    if not isinstance(subtasks_raw, list) or not subtasks_raw:
        raise MasterParseError("'subtasks' must be a non-empty list")
    subtasks: list[SubtaskSpec] = []
    for item in subtasks_raw:
        if not isinstance(item, Mapping) or not str(
            item.get("description") or ""
        ).strip():
            raise MasterParseError("each subtask needs a non-empty 'description'")
        subtasks.append(
            SubtaskSpec(
                description=str(item["description"]),
                role=str(item.get("role") or "") or None,
            )
        )
    criteria = payload.get("verification_criteria") or []
    if not isinstance(criteria, list):
        raise MasterParseError("'verification_criteria' must be a list")
    return MasterPlan(
        subtasks=tuple(subtasks),
        verification_criteria=tuple(str(item) for item in criteria),
    )


def parse_verdict(text: str) -> Verdict:
    """Parse the verdict contract (pure)."""
    payload = _extract_json(text)
    verdict = str(payload.get("verdict") or "")
    if verdict not in ("pass", "fail"):
        raise MasterParseError("'verdict' must be 'pass' or 'fail'")
    checks_raw = payload.get("checks") or []
    if not isinstance(checks_raw, list):
        raise MasterParseError("'checks' must be a list")
    checks: list[tuple[str, bool, str]] = []
    for item in checks_raw:
        if not isinstance(item, Mapping) or "name" not in item:
            raise MasterParseError("each check needs a 'name'")
        checks.append(
            (
                str(item["name"]),
                bool(item.get("passed", False)),
                str(item.get("detail") or ""),
            )
        )
    return Verdict(verdict=verdict, summary=str(payload.get("summary") or ""), checks=tuple(checks))


# ------------------------------------------------------------------ master


@dataclass(slots=True)
class StepReport:
    """Bookkeeping for one executed plan step."""

    step_index: int
    agent_id: str
    status: str
    summary: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "agent_id": self.agent_id,
            "status": self.status,
            "summary": self.summary,
            "confidence": self.confidence,
        }


class MasterAgent:
    """The §6.3 Master Agent — NEXUS-owned (§0.5), orchestrating the
    task lifecycle through the §6.2 loops of registered §6.1 agents."""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        communicator: AgentCommunicator,
        ownership: OwnershipManager,
        model_manager: ModelManager,
        engine: TaskEngine,
        bus: EventBus,
        resources: ResourceManager | None = None,
        tools: ToolSink | None = None,
        verifier: Verifier | None = None,
        max_parallel: int = 3,
        repair_limit: int = 2,
        loop_max_turns: int = 8,
        session_id: str | None = None,
        harness: Harness | None = None,
    ) -> None:
        self._registry = registry
        self._communicator = communicator
        self._ownership = ownership
        self._models = model_manager
        self._engine = engine
        self._bus = bus
        self._resources = resources
        self._tools = tools
        self._verifier = verifier
        self._max_parallel = max(1, max_parallel)
        self._repair_limit = max(0, repair_limit)
        self._loop_max_turns = max(1, loop_max_turns)
        self._session_id = session_id
        self._harness = harness

    @property
    def id(self) -> str:
        return MASTER_AGENT_ID

    # ---------------------------------------------------------------- run

    def handle(self, task: Task, *, session_id: str | None = None) -> Task:
        """The user-facing entry: run the task to a terminal state."""
        from ..core.engine.states import TERMINAL_STATES

        if task.state in TERMINAL_STATES:
            raise MasterError(
                f"task {task.id} is already terminal ({task.state.value})"
            )
        session = session_id or self._session_id
        agent_session = self._begin_harness_session(task)
        # «يتعامل مع المستخدم» — the task *is* the conversation with the user.
        self._engine.start(task, session_id=session, reason="master took the task")

        # «يفهم الهدف» — ANALYZING (honest failure: a model failure here
        # cancels the task with a recorded error — the 13-state machine
        # allows CANCELLED from every non-terminal state).
        try:
            understanding = self._understand(task)
        except (MasterError, MasterParseError, ProviderError) as exc:
            return self._fail_early(task, exc, "understanding", session)
        self._engine.transition(
            task, "PLANNING", reason="goal understood", session_id=session
        )

        # «يوزع العمل» — PLANNING: subtasks onto the §2.5 plan steps.
        try:
            plan = self._plan(task, understanding)
        except (MasterError, MasterParseError, ProviderError) as exc:
            return self._fail_early(task, exc, "planning", session)
        self._engine.transition(
            task,
            "EXECUTING",
            reason=f"{len(plan.subtasks)} step(s) planned",
            session_id=session,
        )

        # «يتابع» + «يستقبل النتائج» + «يقرر الاستمرار» — EXECUTING/REPAIRING.
        reports = self._execute(task, plan, session)

        # «يقرر الوصول إلى Verification» — VERIFYING → terminal.
        result = self._verify_and_finish(task, plan, reports, session)
        self._end_harness_session(agent_session, result)
        return result

    # ------------------------------------------------- §7.2 session lifecycle

    def _begin_harness_session(self, task: Task) -> str | None:
        """Harness wiring (Plan §7.2): fire session_start per master run.

        The §7.2 session ledger (``SessionTracker``) is runtime-owned;
        the master contributes the lifecycle hook points only.
        """
        if self._harness is None or self._harness.hooks is None:
            return None
        self._harness.hooks.fire(
            "session_start",
            HookContext(
                point="session_start",
                agent_id=MASTER_AGENT_ID,
                task_id=task.id,
                detail={"goal": task.goal},
            ),
        )
        return task.id

    def _end_harness_session(self, marker: str | None, result: Task) -> None:
        if marker is None or self._harness is None or self._harness.hooks is None:
            return
        self._harness.hooks.fire(
            "session_end",
            HookContext(
                point="session_end",
                agent_id=MASTER_AGENT_ID,
                task_id=result.id,
                detail={"final_state": str(getattr(result.state, "value", result.state))},
            ),
        )

    # ------------------------------------------------------- model phases

    def _fail_early(
        self, task: Task, exc: Exception, phase: str, session: str | None
    ) -> Task:
        """Model failure before EXECUTING — record + cancel (legal from
        every non-terminal state; no invented verdict)."""
        self._engine.record_error(
            task,
            code=f"master.{phase}_failure",
            message=str(exc),
            source="nexus.agents.master",
        )
        self._bus.publish(
            EventName.AGENT_FAILED,
            payload={
                "agent_id": MASTER_AGENT_ID,
                "phase": phase,
                "detail": str(exc),
            },
            source="nexus.agents.master",
            task_id=task.id,
            session_id=session,
        )
        return self._engine.cancel(
            task, reason=f"master {phase} failed: {exc}", session_id=session
        )

    def _understand(self, task: Task) -> Understanding:
        prompt = (
            f"USER GOAL: {task.goal}\n"
            f"USER PROMPT: {task.prompt}\n\n"
            "Understand the goal and extract the requirements."
        )
        return self._with_retry(prompt, _UNDERSTANDING_PROTOCOL, parse_understanding)

    def _plan(self, task: Task, understanding: Understanding) -> MasterPlan:
        prompt = (
            f"GOAL: {task.goal}\n"
            f"UNDERSTANDING: {understanding.understanding}\n"
            f"REQUIREMENTS: {', '.join(understanding.requirements) or '(none)'}\n\n"
            "Decompose the goal into concrete subtasks and list the "
            "verification criteria."
        )
        return self._with_retry(prompt, _PLAN_PROTOCOL, parse_plan)

    def _verify_model(
        self, task: Task, plan: MasterPlan, reports: Mapping[str, StepReport]
    ) -> Verdict:
        step_lines = "\n".join(
            f"- [{report.status}] {report.summary or '(no summary)'}"
            for report in reports.values()
        )
        prompt = (
            f"GOAL: {task.goal}\n"
            f"CRITERIA: {', '.join(plan.verification_criteria) or '(none)'}\n"
            f"STEP REPORTS:\n{step_lines or '(none)'}\n\n"
            "Decide the verification verdict."
        )
        return self._with_retry(prompt, _VERDICT_PROTOCOL, parse_verdict)

    def _model_call(self, prompt: str, protocol: str) -> str:
        routing = self._models.select(
            RoutingRequest(task_type="chat", complexity=0.6)
        )
        model_id = routing.selected_model_id
        if model_id is None:
            raise MasterError(f"no model available for the master ({routing.reason})")
        request = GenerateRequest(
            model_id=model_id,
            prompt=f"{prompt}\n\n{protocol}",
            system=(
                "You are the NEXUS Master Agent. Follow the answer "
                "protocol exactly."
            ),
            max_tokens=768,
            temperature=0.4,
            auto_load=True,
        )
        return self._models.generate(request).text

    def _with_retry(
        self,
        prompt: str,
        protocol: str,
        parser: Any,
    ) -> Any:
        """One call + strict parse, one corrective retry (§6.2 discipline)."""
        attempts = 0
        last_error: Exception | None = None
        while attempts < 2:
            attempts += 1
            text = self._model_call(prompt, protocol)
            try:
                return parser(text)
            except MasterParseError as exc:
                last_error = exc
                prompt = (
                    f"{prompt}\n\nYour previous answer violated the protocol "
                    f"({exc}). Follow the protocol exactly."
                )
        raise MasterParseError(f"protocol violated twice: {last_error}") from last_error

    # ---------------------------------------------------- execution phases

    def _execute(
        self, task: Task, plan: MasterPlan, session: str | None
    ) -> dict[str, StepReport]:
        """Run every subtask through an agent loop; repair failures."""
        # Lazy core vocabulary (import-order safety — module docstring).
        from ..core.session.models import PlanStep, StepStatus

        if not task.plan.steps:
            for spec in plan.subtasks:
                task.plan.steps.append(PlanStep.create(spec.description))
        if MASTER_AGENT_ID not in task.agents:
            task.agents.append(MASTER_AGENT_ID)
        task.touch()

        reports: dict[str, StepReport] = {}
        repair_rounds = 0
        index = 0
        while index < len(task.plan.steps):
            step = task.plan.steps[index]
            spec = (
                plan.subtasks[index]
                if index < len(plan.subtasks)
                else SubtaskSpec(description=step.description)
            )
            if step.status is StepStatus.DONE:
                index += 1
                continue
            agent = self._pick_agent(spec)
            self._register_slot(agent.id)
            step.agent = agent.id
            step.status = StepStatus.IN_PROGRESS
            task.touch()
            if agent.id not in task.agents:
                task.agents.append(agent.id)

            # «يوزع العمل» — the delegation message (§6.5).
            self._communicator.send(
                AgentMessage.create(
                    task_id=task.id,
                    sender=MASTER_AGENT_ID,
                    receiver=agent.id,
                    type=MessageType.TASK,
                    data={"instruction": step.description},
                )
            )
            loop = AgentLoop(
                agent=agent,
                model_manager=self._models,
                communicator=self._communicator,
                ownership=self._ownership,
                bus=self._bus,
                tools=self._tools,
                verifier=self._verifier,
                max_turns=self._loop_max_turns,
                session_id=session,
                harness=self._harness,
            )
            outcome: LoopOutcome = loop.run(
                task, goal=task.goal, instruction=step.description
            )
            self._release_slot(agent.id)

            # «يستقبل النتائج» — drain the master mailbox.
            self._communicator.receive(MASTER_AGENT_ID)

            step.status = (
                StepStatus.DONE if outcome.completed else StepStatus.FAILED
            )
            task.touch()
            reports[step.id] = StepReport(
                step_index=index,
                agent_id=agent.id,
                status="done" if outcome.completed else "failed",
                summary=(outcome.response or outcome.detail)[:500],
                confidence=outcome.confidence,
            )
            if outcome.completed:
                index += 1
                continue
            # «يقرر الاستمرار» — bounded repair rounds for failed steps.
            if repair_rounds < self._repair_limit:
                repair_rounds += 1
                self._engine.transition(
                    task,
                    "REPAIRING",
                    reason=f"step {index + 1} failed — repair round {repair_rounds}",
                    session_id=session,
                )
                self._engine.transition(
                    task,
                    "EXECUTING",
                    reason="re-running the failed step",
                    session_id=session,
                )
                continue
            index += 1  # honest failure — record it and move on
        return reports

    def _pick_agent(self, spec: SubtaskSpec) -> Agent:
        """§6.4 discovery: role match first, else a worker, else the
        master itself executes the step (documented Phase-5 policy:
        first match; a dedicated Agent Router arrives with the
        delegation phases)."""
        if spec.role:
            found = self._registry.discover_agents(role=spec.role)
            if found:
                return found[0]
        workers = [
            agent
            for agent in self._registry.discover_agents()
            if agent.id != MASTER_AGENT_ID
        ]
        if workers and spec.role is None:
            return workers[0]
        if self._registry.has(MASTER_AGENT_ID):
            return self._registry.get(MASTER_AGENT_ID)
        return Agent.master_record()

    def _register_slot(self, agent_id: str) -> None:
        if self._resources is not None:
            self._resources.register_agent(agent_id)

    def _release_slot(self, agent_id: str) -> None:
        if self._resources is not None:
            self._resources.unregister_agent(agent_id)

    # ------------------------------------------------- verification phase

    def _verify_and_finish(
        self,
        task: Task,
        plan: MasterPlan,
        reports: dict[str, StepReport],
        session: str | None,
    ) -> Task:
        """VERIFYING → COMPLETED (bounded REPAIRING on a failed gate)."""
        # Lazy core vocabulary (import-order safety — module docstring).
        from ..core.session.models import (
            VerificationCheck,
            VerificationRecord,
            VerificationStatus,
            utc_now,
        )

        self._engine.transition(
            task, "VERIFYING", reason="master decided to verify", session_id=session
        )
        self._bus.publish(
            EventName.VERIFICATION_STARTED,
            payload={
                "task_id": task.id,
                "criteria": list(plan.verification_criteria),
            },
            source="nexus.agents.master",
            task_id=task.id,
            session_id=session,
        )

        repairs_left = self._repair_limit
        while True:
            try:
                verdict = self._verify_model(task, plan, reports)
            except (MasterError, MasterParseError, ProviderError) as exc:
                # honest failure — no invented verdict
                self._engine.record_error(
                    task,
                    code="verification.model_failure",
                    message=str(exc),
                    source="nexus.agents.master",
                )
                self._bus.publish(
                    EventName.VERIFICATION_FAILED,
                    payload={"task_id": task.id, "error": str(exc)},
                    source="nexus.agents.master",
                    task_id=task.id,
                    session_id=session,
                )
                return self._engine.complete(
                    task,
                    summary=f"verification could not run: {exc}",
                    success=False,
                    reason="verification model failure",
                    session_id=session,
                )

            record = VerificationRecord()
            record.status = (
                VerificationStatus.PASSED if verdict.passed else VerificationStatus.FAILED
            )
            record.started_at = utc_now()
            for name, passed, detail in verdict.checks:
                record.checks.append(
                    VerificationCheck(name=name, passed=passed, detail=detail or None)
                )
            record.completed_at = utc_now()
            task.verification = record
            task.touch()

            if verdict.passed:
                self._bus.publish(
                    EventName.VERIFICATION_PASSED,
                    payload={
                        "task_id": task.id,
                        "checks": len(verdict.checks),
                        "summary": verdict.summary[:500],
                    },
                    source="nexus.agents.master",
                    task_id=task.id,
                    session_id=session,
                )
                return self._engine.complete(
                    task,
                    summary=verdict.summary or "all verification checks passed",
                    artifacts=self._artifacts_from(reports),
                    success=True,
                    reason="master verification passed",
                    session_id=session,
                )

            self._bus.publish(
                EventName.VERIFICATION_FAILED,
                payload={
                    "task_id": task.id,
                    "checks": len(verdict.checks),
                    "summary": verdict.summary[:500],
                },
                source="nexus.agents.master",
                task_id=task.id,
                session_id=session,
            )
            if repairs_left > 0:
                repairs_left -= 1
                self._engine.transition(
                    task,
                    "REPAIRING",
                    reason="verification failed — repair round",
                    session_id=session,
                )
                self._engine.transition(
                    task,
                    "VERIFYING",
                    reason="re-verification after repair",
                    session_id=session,
                )
                continue
            return self._engine.complete(
                task,
                summary=verdict.summary or "verification failed",
                artifacts=self._artifacts_from(reports),
                success=False,
                reason="verification failed; repair limit exhausted",
                session_id=session,
            )

    def _artifacts_from(self, reports: dict[str, StepReport]) -> list[str]:
        artifacts: list[str] = []
        for report in reports.values():
            if report.status == "done" and report.summary:
                artifacts.append(f"step {report.step_index + 1}: {report.summary}")
        return artifacts

    # ------------------------------------------------------- introspection

    def mailbox(self) -> tuple[AgentMessage, ...]:
        """The master's current mailbox (progress/result messages)."""
        return self._communicator.peek(MASTER_AGENT_ID)
