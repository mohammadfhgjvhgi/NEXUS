#!/usr/bin/env python3
"""Phase 5 verification harness — Final Build Plan §6 Exit Criteria.

Proves the Agent Runtime section by section:

* A — Agent Abstraction (§6.1): the Agent record with the eight
       verbatim fields (id, role, instructions, capabilities, tools,
       memory policy, model policy, verification), the typed policy
       records with their validation, round-trips, and the §6.3 master
       record.
* B — Agent Loop (§6.2): the seven-phase cycle verbatim
       (Observe → Context → Decide → Tool/Agent call → Observe →
       Verify → Continue — proven from the recorded trace), the strict
       decision parser (valid/invalid/prose-wrapped/clamped), the
       single corrective retry, the tool path with canonical events,
       the §6.6 conflict path (coordination, not overwrite), the turn
       budget, and honest failure modes.
* C — Master Agent (§6.3): the three strict model contracts
       (understanding / plan / verdict), the seven-behavior
       choreography over the §2.4 task machine
       (CREATED→ANALYZING→PLANNING→EXECUTING→VERIFYING→COMPLETED with
       bounded REPAIRING), verification records on the task, honest
       early failure (cancel + recorded error), and the terminal
       guard.
* D — Agent Registry (§6.4): the four verbatim verbs, discovery by
       role/capability, master-record protection, atomic persistence
       and reboot reload, corrupt-file resilience, idempotent seeding.
* E — Agent Communication (§6.5): the eight verbatim message fields,
       validation, the sent→delivered→read lifecycle, broadcast,
       per-task structured log, evidence round-trips, and the JSONL
       transcript.
* F — Agent Ownership (§6.6) + integration: the resource→owner record
       (conflict → coordination signal), acquire/release semantics,
       runtime wiring (registry/communicator/ownership/master), the
       open roster across reboots, master-disabled configuration, the
       full runtime task run, shutdown ownership release, the
       event-name guard (⊆ the 28 canonical §2.2 events), and Phases
       1–4 harnesses still green (98/98 · 143/143 · 104/104 · 106/106).

Run:  python tests/phase05/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.agents import (  # noqa: E402
    AGENT_FIELDS,
    AGENT_MESSAGE_FIELDS,
    BROADCAST_RECEIVER,
    LOOP_PHASES,
    MASTER_AGENT_ID,
    OWNERSHIP_FIELDS,
    Agent,
    AgentCommunicator,
    AgentError,
    AgentMessage,
    AgentRegistry,
    AgentRegistryError,
    CommunicationError,
    DecisionParseError,
    Evidence,
    MasterAgent,
    MasterError,
    MemoryPolicy,
    ModelPolicy,
    OwnershipError,
    OwnershipManager,
    ResourceOwnedError,
    VerificationPolicy,
    new_agent_id,
    parse_decision,
    parse_plan,
    parse_understanding,
    parse_verdict,
)
from nexus.agents.loop import (  # noqa: E402
    OUTCOME_FAILED,
    OUTCOME_MAX_TURNS,
    AgentLoop,
    InlineToolSink,
)
from nexus.core.config import NexusRuntime  # noqa: E402
from nexus.core.config.schema import build_section  # noqa: E402
from nexus.core.engine.machine import TaskEngine  # noqa: E402
from nexus.core.session.models import Task, TaskState  # noqa: E402
from nexus.events import CANONICAL_EVENTS, EventBus  # noqa: E402
from nexus.models import (  # noqa: E402
    GenerateResult,
    ModelManager,
    ProviderError,
    SimulatedProvider,
)
from nexus.resources import ResourceBudgets, ResourceManager  # noqa: E402

# The §6.1 plan fields, verbatim (harness-side independent constant).
PLAN_AGENT_FIELDS = (
    "id", "role", "instructions", "capabilities", "tools",
    "memory_policy", "model_policy", "verification",
)

# The §6.5 plan fields, verbatim.
PLAN_MESSAGE_FIELDS = (
    "task_id", "sender", "receiver", "type", "status", "data",
    "evidence", "confidence",
)

# The §6.6 plan fields, verbatim.
PLAN_OWNERSHIP_FIELDS = ("resource", "owner")

# The §6.2 plan cycle, verbatim.
PLAN_LOOP_PHASES = (
    "observe", "context", "decide", "act", "observe", "verify", "continue",
)

assert AGENT_FIELDS == PLAN_AGENT_FIELDS  # wiring sanity for this harness


# ------------------------------------------------------------------- runner

class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        line = f"  [{mark}] ({self.section}) {label}"
        if detail and not condition:
            line += f" — {detail}"
        print(line)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def summary(self) -> int:
        total = self.passed + self.failed
        print()
        print("=" * 72)
        print(f"PHASE 5 EXIT CRITERIA — {self.passed}/{total} checks passed"
              f" ({self.failed} failed)")
        print("=" * 72)
        return 0 if self.failed == 0 else 1


# ------------------------------------------------------------- test doubles


class ScriptedProvider(SimulatedProvider):
    """Deterministic model double: pops canned answers off a script.

    Raises ProviderError when the script is exhausted — the honest
    failure the loop/master paths must surface."""

    def __init__(self, script: list[str]) -> None:
        super().__init__()
        self._script = list(script)
        self.calls = 0

    def generate(self, request: Any) -> GenerateResult:
        self.calls += 1
        if not self._script:
            raise ProviderError("script exhausted")
        text = self._script.pop(0)
        return GenerateResult(
            model_id=request.model_id,
            backend="scripted",
            text=text,
            prompt_tokens=8,
            generation_tokens=max(1, len(text) // 4),
        )

    @property
    def remaining(self) -> int:
        return len(self._script)


def make_manager(
    base: str | Path,
    script: list[str],
    *,
    bus: EventBus | None = None,
) -> tuple[ModelManager, ResourceManager, ScriptedProvider]:
    """A §5.4 manager over the scripted provider, MiMo pool seeded."""
    resources = ResourceManager(
        f"{base}-res",
        budgets=ResourceBudgets(ram_mb=65536, model_memory_mb=65536,
                                vram_mb=0, max_concurrency=4, max_agents=3),
    )
    provider = ScriptedProvider(script)
    manager = ModelManager.from_config(
        f"{base}-models",
        provider=provider,
        resources=resources,
        bus=bus,
        keep_warm_seconds=300.0,
        seed_mimo_edge=True,
    )
    return manager, resources, provider


def make_worker(*, tools: tuple[str, ...] = ("write_file",)) -> Agent:
    return Agent.create(
        role="worker",
        instructions="Do the work precisely.",
        capabilities=("files", "general"),
        tools=tools,
        verification=VerificationPolicy(required=True, criteria=()),
    )


def make_master_stack(
    base: str | Path,
    script: list[str],
    *,
    workers: int = 1,
    bus: EventBus | None = None,
    resources: ResourceManager | None = None,
    repair_limit: int = 2,
) -> tuple[MasterAgent, AgentRegistry, AgentCommunicator, OwnershipManager,
           EventBus, ScriptedProvider, list[Agent]]:
    """A full §6 stack: registry(+master+workers), communicator,
    ownership, engine, scripted model manager."""
    event_bus = bus if bus is not None else EventBus()
    registry = AgentRegistry(f"{base}-agents")
    registry.seed_master()
    crew = [make_worker() for _ in range(workers)]
    for agent in crew:
        registry.register_agent(agent)
    communicator = AgentCommunicator(tasks_dir=None, persist=False)
    ownership = OwnershipManager()
    manager, res, provider = make_manager(base, script, bus=event_bus)
    master = MasterAgent(
        registry=registry,
        communicator=communicator,
        ownership=ownership,
        model_manager=manager,
        engine=TaskEngine(event_bus),
        bus=event_bus,
        resources=resources if resources is not None else res,
        repair_limit=repair_limit,
    )
    return master, registry, communicator, ownership, event_bus, provider, crew


def make_task(*, goal: str = "Write the release notes file") -> Task:
    return Task.create(
        conversation_id="conv_phase5",
        goal=goal,
        prompt=f"Please {goal.lower()}.",
    )


def event_names(bus: EventBus) -> list[str]:
    return [event.name for event in bus.history_snapshot()]


def decision_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {"action": "done", "response": "work complete"}
    payload.update(overrides)
    return json.dumps(payload)


UNDERSTANDING_OK = json.dumps({
    "understanding": "Produce the release notes file for the current release.",
    "requirements": ["cover the three fixed bugs", "mention the new agent runtime"],
})

PLAN_OK = json.dumps({
    "subtasks": [
        {"description": "Draft the release notes", "role": "worker"},
    ],
    "verification_criteria": ["file mentions release", "notes are complete"],
})

VERDICT_PASS = json.dumps({
    "verdict": "pass",
    "summary": "All steps completed and evidence is consistent.",
    "checks": [
        {"name": "file mentions release", "passed": True, "detail": "seen in output"},
        {"name": "notes are complete", "passed": True, "detail": "two sections present"},
    ],
})

VERDICT_FAIL = json.dumps({
    "verdict": "fail",
    "summary": "The notes are incomplete.",
    "checks": [
        {"name": "notes are complete", "passed": False, "detail": "missing section"},
    ],
})


# ------------------------------------------------------------------- sections

def section_a(runner: Runner) -> None:
    """A — Agent Abstraction (§6.1)."""
    runner.section = "A/§6.1"

    runner.check(
        "Agent carries exactly the eight §6.1 fields, verbatim",
        tuple(f.name for f in dc_fields(Agent)) == PLAN_AGENT_FIELDS,
        detail=f"got {tuple(f.name for f in dc_fields(Agent))}",
    )

    agent = Agent.create(
        role="analyst",
        instructions="Analyze the input.",
        capabilities=("files", "web"),
        tools=("read_file", "write_file"),
        memory_policy=MemoryPolicy(read=("task",), write=("task",)),
        model_policy=ModelPolicy(model_id="qwen3-0.6b", complexity=0.8),
        verification=VerificationPolicy(required=True, criteria=("evidence",)),
    )
    runner.check(
        "Agent.create populates every field incl. the three policies",
        agent.role == "analyst" and agent.capabilities == ("files", "web")
        and agent.tools == ("read_file", "write_file")
        and agent.memory_policy.read == ("task",)
        and agent.model_policy.model_id == "qwen3-0.6b"
        and agent.verification.criteria == ("evidence",),
    )

    ident = new_agent_id()
    runner.check(
        "agent ids follow the ag_+12hex family",
        ident.startswith("ag_") and len(ident) == 15,
    )

    for bad in ({"role": "", "instructions": "x"}, {"role": "r", "instructions": " "}):
        try:
            Agent(id=new_agent_id(), role=bad["role"], instructions=bad["instructions"])
            ok = False
        except AgentError:
            ok = True
        runner.check(
            f"Agent validation rejects empty {'role' if not bad['role'] else 'instructions'}",
            ok,
        )

    try:
        MemoryPolicy(retention="session")
        ok = False
    except AgentError:
        ok = True
    runner.check(
        "memory policy retention is the §2.3 ladder (task/conversation/user)",
        ok and set(MemoryPolicy().to_dict()) == {"read", "write", "retention"},
    )

    for kwargs, label in (
        ({"complexity": 1.5}, "complexity out of 0..1"),
        ({"max_tokens": 0}, "max_tokens <= 0"),
        ({"temperature": 5.0}, "temperature out of 0..2"),
    ):
        try:
            ModelPolicy(**kwargs)
            ok = False
        except AgentError:
            ok = True
        runner.check(f"model policy rejects {label}", ok)

    try:
        VerificationPolicy(max_repairs=-1)
        ok = False
    except AgentError:
        ok = True
    runner.check("verification policy rejects negative repair bound", ok)

    record = agent.to_dict()
    rebuilt = Agent.from_dict(record)
    runner.check(
        "Agent round-trips through its serialized form",
        rebuilt.to_dict() == record,
    )
    try:
        Agent.from_dict({**record, "surprise": 1})
        ok = False
    except AgentError:
        ok = True
    runner.check("Agent.from_dict rejects unknown fields", ok)

    master = Agent.master_record()
    runner.check(
        "the §6.3 master record exists with a fixed identity",
        master.id == MASTER_AGENT_ID and master.role == "master"
        and "delegation" in master.capabilities,
    )


def section_b(runner: Runner, base: Path) -> None:
    """B — Agent Loop (§6.2)."""
    runner.section = "B/§6.2"

    runner.check(
        "the §6.2 cycle is the seven plan phases verbatim",
        LOOP_PHASES == PLAN_LOOP_PHASES,
        detail=f"got {LOOP_PHASES}",
    )

    # ---- the strict decision parser (pure) -----------------------------
    ok_decision = parse_decision(
        'Prose before. {"action": "respond", "response": "hello",'
        ' "confidence": 0.9} prose after'
    )
    runner.check(
        "parse_decision extracts JSON wrapped in prose",
        ok_decision.action == "respond" and ok_decision.response == "hello"
        and ok_decision.confidence == 0.9,
    )

    tool_decision = parse_decision(
        '{"action": "call_tool", "tool": "write_file",'
        ' "arguments": {"path": "notes.txt"}, "resource": "notes.txt",'
        ' "reason": "create the file"}'
    )
    runner.check(
        "parse_decision accepts a full tool decision",
        tool_decision.tool == "write_file"
        and tool_decision.arguments == {"path": "notes.txt"}
        and tool_decision.resource == "notes.txt",
    )

    delegate = parse_decision(
        '{"action": "delegate", "delegate": "ag_worker", "message": "draft it"}'
    )
    runner.check(
        "parse_decision accepts a delegation decision",
        delegate.delegate == "ag_worker" and delegate.message == "draft it",
    )

    high = parse_decision('{"action": "done", "response": "x", "confidence": 1.7}')
    low = parse_decision('{"action": "done", "response": "x", "confidence": -0.4}')
    runner.check(
        "parse_decision clamps confidence into 0..1",
        high.confidence == 1.0 and low.confidence == 0.0,
    )

    bad_cases = [
        ("empty text", ""),
        ("no JSON", "I will do the work now."),
        ("unbalanced", '{"action": "respond", "response": "x"'),
        ("bad action", '{"action": "explode", "response": "x"}'),
        ("respond without response", '{"action": "respond"}'),
        ("call_tool without tool", '{"action": "call_tool"}'),
        ("tool with respond", '{"action": "respond", "response": "x", "tool": "t"}'),
        ("delegate without target", '{"action": "delegate"}'),
        ("arguments not an object", '{"action": "call_tool", "tool": "t", "arguments": "flat"}'),
    ]
    for label, text in bad_cases:
        try:
            parse_decision(text)
            ok = False
        except DecisionParseError:
            ok = True
        runner.check(f"parse_decision rejects: {label}", ok)

    # ---- the loop, over the scripted provider --------------------------
    bus = EventBus()
    manager, _res, provider = make_manager(
        f"{base}-loop1", [decision_json(action="respond", response="drafting…"),
                          decision_json(response="release notes written")]
    )
    communicator = AgentCommunicator(tasks_dir=None, persist=False)
    ownership = OwnershipManager()
    worker = make_worker()
    loop = AgentLoop(
        agent=worker,
        model_manager=manager,
        communicator=communicator,
        ownership=ownership,
        bus=bus,
        max_turns=8,
    )
    task = make_task()
    outcome = loop.run(task, instruction="Draft the release notes")

    runner.check(
        "loop completes on a done decision that passes the gate",
        outcome.completed and outcome.response == "release notes written",
        detail=f"status={outcome.status} detail={outcome.detail}",
    )

    turn1 = [s.phase for s in outcome.trace if s.turn == 1]
    runner.check(
        "turn 1 walks the seven §6.2 phases in plan order",
        tuple(turn1) == PLAN_LOOP_PHASES,
        detail=f"got {turn1}",
    )
    final_turn = [s.phase for s in outcome.trace if s.turn == outcome.turns]
    runner.check(
        "the final (done) turn ends at the verify gate",
        tuple(final_turn) == PLAN_LOOP_PHASES[:6],
        detail=f"got {final_turn}",
    )

    names = event_names(bus)
    runner.check(
        "loop events are the canonical agent.started/completed pair",
        names[0] == "agent.started" and names[-1] == "agent.completed",
        detail=f"got {names}",
    )

    result_message = communicator.log(task.id)[-1]
    runner.check(
        "the loop reports its result to the §6.3 master (§6.5 message)",
        result_message.receiver == MASTER_AGENT_ID
        and result_message.type == "result"
        and result_message.data["status"] == "completed",
    )

    # ---- tool path: events, evidence, ownership acquire/release --------
    bus2 = EventBus()
    manager2, _res2, _provider2 = make_manager(
        f"{base}-loop2",
        [decision_json(action="call_tool", tool="write_file",
                       arguments={"path": "notes.txt"}, resource="notes.txt"),
         decision_json(response="file written with release notes")],
    )
    communicator2 = AgentCommunicator(tasks_dir=None, persist=False)
    ownership2 = OwnershipManager()
    sink = InlineToolSink({"write_file": lambda args: f"wrote {args.get('path')}"})
    worker2 = make_worker()
    loop2 = AgentLoop(
        agent=worker2, model_manager=manager2, communicator=communicator2,
        ownership=ownership2, bus=bus2, tools=sink, max_turns=8,
    )
    task2 = make_task()
    outcome2 = loop2.run(task2, instruction="Write notes.txt")
    names2 = event_names(bus2)
    runner.check(
        "tool acts publish tool.called + tool.completed (canonical)",
        "tool.called" in names2 and "tool.completed" in names2,
        detail=f"got {names2}",
    )
    runner.check(
        "tool output lands as §6.5 evidence on the outcome",
        any(e.kind == "tool_output" and e.source == "write_file"
            for e in outcome2.evidence),
    )
    runner.check(
        "loop end releases the §6.6 resources the agent acquired",
        ownership2.owner_of("notes.txt") is None,
        detail=f"still held: {ownership2.entries()}",
    )

    # ---- §6.6 conflict: coordination, never a silent overwrite ---------
    bus3 = EventBus()
    manager3, _res3, _provider3 = make_manager(
        f"{base}-loop3",
        [decision_json(action="call_tool", tool="write_file",
                       arguments={"path": "shared.txt"}, resource="shared.txt"),
         decision_json(response="left shared.txt to its owner")],
    )
    communicator3 = AgentCommunicator(tasks_dir=None, persist=False)
    ownership3 = OwnershipManager()
    ownership3.acquire("shared.txt", owner="ag_holder001", task_id="task_ext")
    sink3 = InlineToolSink({"write_file": lambda args: "wrote"})
    loop3 = AgentLoop(
        agent=make_worker(), model_manager=manager3, communicator=communicator3,
        ownership=ownership3, bus=bus3, tools=sink3, max_turns=8,
    )
    task3 = make_task()
    outcome3 = loop3.run(task3, instruction="Write shared.txt")
    names3 = event_names(bus3)
    coordination = [m for m in communicator3.log(task3.id)
                    if m.type == "coordination"]
    runner.check(
        "a §6.6 conflict sends a coordination message to the holder",
        len(coordination) == 1 and coordination[0].receiver == "ag_holder001"
        and coordination[0].data["resource"] == "shared.txt",
    )
    runner.check(
        "the conflicting tool act never runs (no tool events, holder intact)",
        "tool.called" not in names3
        and ownership3.owner_of("shared.txt") == "ag_holder001",
        detail=f"events={names3}",
    )
    runner.check(
        "the conflicting agent still finishes honestly (re-decide)",
        outcome3.completed,
        detail=f"status={outcome3.status}",
    )

    # ---- turn budget ---------------------------------------------------
    bus4 = EventBus()
    manager4, _res4, _provider4 = make_manager(
        f"{base}-loop4",
        [decision_json(action="respond", response="thinking…"),
         decision_json(action="respond", response="still thinking…")],
    )
    loop4 = AgentLoop(
        agent=make_worker(), model_manager=manager4,
        communicator=AgentCommunicator(tasks_dir=None, persist=False),
        ownership=OwnershipManager(), bus=bus4, max_turns=2,
    )
    outcome4 = loop4.run(make_task(), instruction="anything")
    runner.check(
        "the turn budget is reported, not silently truncated",
        outcome4.status == OUTCOME_MAX_TURNS and outcome4.turns == 2,
        detail=f"status={outcome4.status}",
    )

    # ---- one corrective retry, then honest failure ---------------------
    bus5 = EventBus()
    manager5, _res5, provider5 = make_manager(
        f"{base}-loop5",
        ["not json at all", decision_json(response="recovered")],
    )
    loop5 = AgentLoop(
        agent=make_worker(), model_manager=manager5,
        communicator=AgentCommunicator(tasks_dir=None, persist=False),
        ownership=OwnershipManager(), bus=bus5, max_turns=4,
    )
    outcome5 = loop5.run(make_task(), instruction="retry test")
    runner.check(
        "a malformed decision gets exactly one corrective retry",
        outcome5.completed and provider5.calls == 2,
        detail=f"calls={provider5.calls} status={outcome5.status}",
    )

    manager6, _res6, _provider6 = make_manager(f"{base}-loop6",
                                                ["garbage one", "garbage two"])
    loop6 = AgentLoop(
        agent=make_worker(), model_manager=manager6,
        communicator=AgentCommunicator(tasks_dir=None, persist=False),
        ownership=OwnershipManager(), bus=EventBus(), max_turns=4,
    )
    outcome6 = loop6.run(make_task(), instruction="double failure")
    runner.check(
        "two malformed decisions fail honestly (agent.failed)",
        outcome6.status == OUTCOME_FAILED
        and "protocol violated twice" in outcome6.detail
        and event_names(loop6._bus)[-1] == "agent.failed",
        detail=f"status={outcome6.status} detail={outcome6.detail}",
    )

    manager7, _res7, _provider7 = make_manager(f"{base}-loop7", [])
    loop7 = AgentLoop(
        agent=make_worker(), model_manager=manager7,
        communicator=AgentCommunicator(tasks_dir=None, persist=False),
        ownership=OwnershipManager(), bus=EventBus(), max_turns=4,
    )
    outcome7 = loop7.run(make_task(), instruction="no model")
    runner.check(
        "a model failure surfaces as an honest failed outcome",
        outcome7.status == OUTCOME_FAILED and "ProviderError" in outcome7.detail,
        detail=f"detail={outcome7.detail}",
    )


def section_c(runner: Runner, base: Path) -> None:
    """C — Master Agent (§6.3)."""
    runner.section = "C/§6.3"

    understanding = parse_understanding(UNDERSTANDING_OK)
    runner.check(
        "understanding contract parses (goal + requirements)",
        "release notes" in understanding.understanding
        and len(understanding.requirements) == 2,
    )
    plan = parse_plan(PLAN_OK)
    runner.check(
        "plan contract parses (subtasks + verification criteria)",
        len(plan.subtasks) == 1 and plan.subtasks[0].role == "worker"
        and len(plan.verification_criteria) == 2,
    )
    verdict = parse_verdict(VERDICT_PASS)
    runner.check(
        "verdict contract parses (verdict + checks)",
        verdict.passed and len(verdict.checks) == 2,
    )
    for label, text in (
        ("understanding without text", '{"understanding": "", "requirements": []}'),
        ("plan without subtasks", '{"subtasks": [], "verification_criteria": []}'),
        ("plan step without description", '{"subtasks": [{"role": "worker"}]}'),
        ("verdict with a bad value", '{"verdict": "maybe"}'),
    ):
        parser = {
            "understanding without text": parse_understanding,
            "plan without subtasks": parse_plan,
            "plan step without description": parse_plan,
            "verdict with a bad value": parse_verdict,
        }[label]
        try:
            parser(text)
            ok = False
        except Exception:
            ok = True
        runner.check(f"master parser rejects: {label}", ok)

    # ---- the seven behaviors, happy path --------------------------------
    master, registry, communicator, ownership, bus, provider, crew = (
        make_master_stack(f"{base}-m1",
                          [UNDERSTANDING_OK, PLAN_OK,
                           decision_json(response="release notes drafted"),
                           VERDICT_PASS])
    )
    task = make_task()
    master.handle(task, session_id="sess_c1")

    runner.check(
        "happy path: task reaches COMPLETED through VERIFYING",
        task.state is TaskState.COMPLETED,
        detail=f"state={task.state}",
    )
    path = [rec.to_state.value for rec in task.state_history]
    runner.check(
        "state choreography: ANALYZING→PLANNING→EXECUTING→VERIFYING→COMPLETED",
        path == ["ANALYZING", "PLANNING", "EXECUTING", "VERIFYING", "COMPLETED"],
        detail=f"got {path}",
    )
    runner.check(
        "the §2.5 plan steps carry the delegated subtask + agent",
        len(task.plan.steps) == 1 and task.plan.steps[0].agent == crew[0].id
        and task.plan.steps[0].status.value == "done",
    )
    runner.check(
        "the §2.5 agents list records master + worker",
        MASTER_AGENT_ID in task.agents and crew[0].id in task.agents,
    )
    runner.check(
        "the verification record lands on the task (checks + PASSED)",
        task.verification.status.value == "passed"
        and len(task.verification.checks) == 2,
    )
    runner.check(
        "task.completed carries the success result",
        task.result is not None and task.result.success,
    )
    names = event_names(bus)
    for expected in ("task.started", "verification.started",
                     "verification.passed", "task.completed"):
        runner.check(f"canonical event present: {expected}", expected in names)
    messages = communicator.log(task.id)
    runner.check(
        "§6.5 flow: TASK delegation out, RESULT back",
        any(m.type == "task" and m.sender == MASTER_AGENT_ID
            and m.receiver == crew[0].id for m in messages)
        and any(m.type == "result" and m.sender == crew[0].id
                and m.receiver == MASTER_AGENT_ID for m in messages),
    )
    runner.check(
        "agent slots are released after the run (agents.max_parallel budget)",
        master._resources is not None and master._resources.agent_count == 0,
    )

    # ---- repair path: verification fail → repair → pass -----------------
    master2, _reg2, comm2, _own2, bus2, _prov2, _crew2 = make_master_stack(
        f"{base}-m2",
        [UNDERSTANDING_OK, PLAN_OK,
         decision_json(response="release notes drafted"),
         VERDICT_FAIL, VERDICT_PASS],
        repair_limit=1,
    )
    task2 = make_task()
    master2.handle(task2)
    path2 = [rec.to_state.value for rec in task2.state_history]
    runner.check(
        "repair path: VERIFYING→REPAIRING→VERIFYING→COMPLETED",
        path2 == ["ANALYZING", "PLANNING", "EXECUTING", "VERIFYING",
                  "REPAIRING", "VERIFYING", "COMPLETED"],
        detail=f"got {path2}",
    )
    names2 = event_names(bus2)
    runner.check(
        "verification.failed then verification.passed are both published",
        "verification.failed" in names2 and "verification.passed" in names2
        and names2.index("verification.failed") < names2.index("verification.passed"),
    )

    # ---- repairs exhausted: honest failure ------------------------------
    master3, _reg3, _comm3, _own3, bus3, _prov3, _crew3 = make_master_stack(
        f"{base}-m3",
        [UNDERSTANDING_OK, PLAN_OK,
         decision_json(response="release notes drafted"),
         VERDICT_FAIL, VERDICT_FAIL],
        repair_limit=1,
    )
    task3 = make_task()
    master3.handle(task3)
    runner.check(
        "exhausted repairs: COMPLETED with success=False (never a fake pass)",
        task3.state is TaskState.COMPLETED
        and task3.result is not None and not task3.result.success
        and task3.verification.status.value == "failed",
    )

    # ---- early model failure: cancel + recorded error -------------------
    master4, _reg4, _comm4, _own4, bus4, _prov4, _crew4 = make_master_stack(
        f"{base}-m4", []
    )
    task4 = make_task()
    master4.handle(task4)
    runner.check(
        "early model failure cancels the task with a recorded error",
        task4.state is TaskState.CANCELLED
        and any(e.code == "master.understanding_failure" for e in task4.errors),
    )

    # ---- terminal guard -------------------------------------------------
    try:
        master.handle(task)  # the already-COMPLETED task from the happy path
        ok = False
    except MasterError:
        ok = True
    runner.check("handle() refuses an already-terminal task", ok)


def section_d(runner: Runner, base: Path) -> None:
    """D — Agent Registry (§6.4)."""
    runner.section = "D/§6.4"

    runner.check(
        "the four §6.4 verbs exist (register/unregister/discover/getCapabilities)",
        all(hasattr(AgentRegistry, name) for name in
            ("register_agent", "unregister_agent", "discover_agents",
             "get_capabilities")),
    )

    directory = f"{base}-registry"
    registry = AgentRegistry(directory)
    registry.seed_master()
    worker = make_worker()
    analyst = Agent.create(role="analyst", instructions="Analyze.",
                           capabilities=("analysis",))
    registry.register_agent(worker)
    registry.register_agent(analyst)
    runner.check(
        "register + list: the roster is open (3 records)",
        len(registry) == 3 and len(registry.list_agents()) == 3,
    )
    runner.check(
        "getCapabilities answers the §6.4 contract",
        registry.get_capabilities(worker.id) == ("files", "general")
        and registry.get_capabilities(analyst.id) == ("analysis",),
    )
    runner.check(
        "discoverAgents matches role (case-insensitive)",
        registry.discover_agents(role="ANALYST") == (analyst,),
    )
    runner.check(
        "discoverAgents matches capability",
        registry.discover_agents(capability="analysis") == (analyst,),
    )
    runner.check(
        "discoverAgents with no filters returns the full roster",
        len(registry.discover_agents()) == 3,
    )

    dropped = registry.unregister_agent(analyst.id)
    runner.check(
        "unregisterAgent removes and returns the record",
        dropped.id == analyst.id and len(registry) == 2,
    )
    try:
        registry.unregister_agent(analyst.id)
        ok = False
    except AgentRegistryError:
        ok = True
    runner.check("unregisterAgent on an unknown id raises", ok)
    try:
        registry.unregister_agent(MASTER_AGENT_ID)
        ok = False
    except AgentRegistryError:
        ok = True
    runner.check("the master record cannot be unregistered", ok)

    reloaded = AgentRegistry(directory)
    runner.check(
        "the registry persists atomically and reloads on reboot",
        reloaded.has(worker.id) and reloaded.has(MASTER_AGENT_ID)
        and len(reloaded) == 2,
    )
    reloaded.seed_master()
    runner.check(
        "seed_master is idempotent (no duplicate master)",
        len([a for a in reloaded.list_agents()
             if a.id == MASTER_AGENT_ID]) == 1,
    )

    corrupt = f"{base}-corrupt"
    Path(corrupt).mkdir(parents=True, exist_ok=True)
    (Path(corrupt) / "agents.registry.json").write_text("{ not valid", encoding="utf-8")
    resilient = AgentRegistry(corrupt)
    runner.check(
        "a corrupt registry file never kills the boot (empty start)",
        len(resilient) == 0,
    )


def section_e(runner: Runner, base: Path) -> None:
    """E — Agent Communication (§6.5)."""
    runner.section = "E/§6.5"

    runner.check(
        "AgentMessage carries exactly the eight §6.5 fields, verbatim",
        AGENT_MESSAGE_FIELDS == PLAN_MESSAGE_FIELDS,
        detail=f"got {AGENT_MESSAGE_FIELDS}",
    )

    message = AgentMessage.create(
        task_id="task_msg1", sender="ag_alpha", receiver="ag_beta",
        type="result", data={"response": "done"},
        evidence=(Evidence(kind="tool_output", source="write_file",
                           detail="wrote 3 lines"),),
        confidence=0.85,
    )
    runner.check(
        "create builds a valid 'sent' message with evidence",
        message.status == "sent" and message.confidence == 0.85
        and message.evidence[0].source == "write_file",
    )
    runner.check(
        "message round-trips through its serialized form",
        AgentMessage.from_dict(message.to_dict()).to_dict() == message.to_dict(),
    )

    for label, kwargs in (
        ("unknown type", {"type": "gossip"}),
        ("confidence above 1", {"confidence": 1.2}),
        ("confidence below 0", {"confidence": -0.1}),
        ("empty sender", {"sender": " "}),
    ):
        merged: dict[str, Any] = dict(
            task_id="task_msg1", sender="ag_alpha", receiver="ag_beta",
            type="result", confidence=0.5,
        )
        merged.update(kwargs)
        try:
            AgentMessage(**merged)
            ok = False
        except CommunicationError:
            ok = True
        runner.check(f"message validation rejects: {label}", ok)

    tasks_dir = f"{base}-tasks"
    Path(tasks_dir).mkdir(parents=True, exist_ok=True)
    communicator = AgentCommunicator(tasks_dir=tasks_dir, persist=True)
    delivered = communicator.send(message)
    runner.check(
        "send stamps sequence + timestamp and delivers to the mailbox",
        delivered.status == "delivered" and delivered.sequence == 1
        and delivered.timestamp != "",
    )
    inbox = communicator.peek("ag_beta")
    runner.check(
        "peek inspects the mailbox without draining",
        len(inbox) == 1 and communicator.mailbox_size("ag_beta") == 1,
    )
    drained = communicator.receive("ag_beta")
    runner.check(
        "receive drains the mailbox and marks the copies 'read'",
        len(drained) == 1 and drained[0].status == "read"
        and communicator.mailbox_size("ag_beta") == 0,
    )
    runner.check(
        "the structured log keeps the lifecycle record",
        communicator.log("task_msg1")[-1].status == "read"
        and communicator.message_count() == 1,
    )

    other = AgentMessage.create(
        task_id="task_msg2", sender="ag_alpha", receiver="ag_beta",
        type="progress", data={"note": "halfway"},
    )
    communicator.send(other)
    runner.check(
        "the log filters per task (§6.5 task_id)",
        len(communicator.log("task_msg1")) == 1
        and len(communicator.log("task_msg2")) == 1,
    )

    communicator.send(AgentMessage.create(
        task_id="task_msg2", sender="ag_alpha", receiver=BROADCAST_RECEIVER,
        type="coordination", data={"note": "everyone pause"},
    ))
    runner.check(
        "broadcast ('*') reaches every known mailbox (and none is invented)",
        communicator.mailbox_size("ag_beta") == 2
        and communicator.mailbox_size("ag_gamma") == 0,
    )

    transcript = Path(tasks_dir) / "task_msg2.messages.jsonl"
    runner.check(
        "the JSONL transcript persists next to the task record",
        transcript.exists(),
    )
    if transcript.exists():
        lines = [json.loads(line) for line in
                 transcript.read_text(encoding="utf-8").splitlines() if line]
        runner.check(
            "transcript lines round-trip as §6.5 messages",
            len(lines) == 2 and lines[0]["task_id"] == "task_msg2"
            and lines[1]["receiver"] == BROADCAST_RECEIVER,
        )
    sequences = [m.sequence for m in communicator.log()]
    runner.check(
        "message sequences are monotonic",
        sequences == sorted(sequences) and len(set(sequences)) == len(sequences),
    )


def section_f(runner: Runner, root: Path) -> None:
    """F — Agent Ownership (§6.6) + integration + guards + regressions."""
    runner.section = "F/§6.6"

    runner.check(
        "the ownership record is resource + owner, verbatim",
        OWNERSHIP_FIELDS == PLAN_OWNERSHIP_FIELDS,
        detail=f"got {OWNERSHIP_FIELDS}",
    )

    ownership = OwnershipManager()
    entry = ownership.acquire("M:\\docs\\notes.txt", owner="ag_writer")
    runner.check(
        "acquire records resource → owner (+ timestamp)",
        entry.resource == "M:\\docs\\notes.txt" and entry.owner == "ag_writer"
        and entry.acquired_at != "",
    )
    again = ownership.acquire("M:\\docs\\notes.txt", owner="ag_writer")
    runner.check("re-acquire by the same owner is idempotent", again is entry)
    try:
        ownership.acquire("M:\\docs\\notes.txt", owner="ag_other", task_id="task_x")
        ok = False
    except ResourceOwnedError as exc:
        ok = (exc.resource == "M:\\docs\\notes.txt"
              and exc.owner == "ag_writer" and exc.requester == "ag_other")
    runner.check(
        "a second agent cannot acquire a held resource (coordination signal)",
        ok,
    )
    runner.check(
        "check() answers who may modify; owner_of() answers who holds",
        ownership.check("M:\\docs\\notes.txt", "ag_writer")
        and not ownership.check("M:\\docs\\notes.txt", "ag_other")
        and ownership.owner_of("M:\\docs\\notes.txt") == "ag_writer",
    )
    try:
        ownership.release("M:\\docs\\notes.txt", owner="ag_other")
        ok = False
    except OwnershipError:
        ok = True
    runner.check("only the owner may release", ok)
    ownership.release("M:\\docs\\notes.txt", owner="ag_writer")
    ownership.acquire("a.txt", owner="ag_w")
    ownership.acquire("b.txt", owner="ag_w")
    released = ownership.release_owner("ag_w")
    runner.check(
        "release_owner returns everything an agent holds (teardown)",
        len(released) == 2 and len(ownership) == 0,
    )
    ownership.acquire("c.txt", owner="ag_w")
    cleared = ownership.clear()
    runner.check("clear() releases all entries at shutdown", len(cleared) == 1)

    # ---- runtime wiring (NexusRuntime) ----------------------------------
    script = [UNDERSTANDING_OK, PLAN_OK,
              decision_json(response="release notes drafted"), VERDICT_PASS]
    provider = ScriptedProvider(script)
    bus = EventBus()
    rt = NexusRuntime.boot(root, bus=bus, model_provider=provider)
    worker = make_worker()
    rt.agent_registry.register_agent(worker)
    task = make_task()
    master = rt.master_agent
    runner.check(
        "runtime wires the §6 components (registry/communicator/ownership/master)",
        isinstance(rt.agent_registry, AgentRegistry)
        and isinstance(rt.communicator, AgentCommunicator)
        and isinstance(rt.ownership, OwnershipManager)
        and master is not None,
    )
    assert master is not None
    master.handle(task, session_id="sess_f1")
    transcript = Path(str(rt.paths.tasks)) / f"{task.id}.messages.jsonl"
    runner.check(
        "full runtime run: the master takes a task to COMPLETED",
        task.state is TaskState.COMPLETED and task.result is not None
        and task.result.success,
        detail=f"state={task.state}",
    )
    runner.check(
        "the §6.5 transcript lands next to the task record (agents.message_log_enabled)",
        transcript.exists() and transcript.stat().st_size > 0,
    )
    rt.save_task(task)
    runner.check(
        "the worked task persists (§2.6) with its agents + verification",
        rt.repository.load(task.id).verification.status.value == "passed",
    )
    published = set(event_names(bus))
    runner.check(
        "event-name guard: every published name is one of the 28 canonical",
        published <= CANONICAL_EVENTS,
        detail=f"unknown: {published - CANONICAL_EVENTS}",
    )

    rt.ownership.acquire("held.txt", owner="ag_x")
    rt.shutdown()
    runner.check(
        "shutdown releases every §6.6 ownership entry",
        len(rt.ownership) == 0,
    )

    root2 = Path(tempfile.mkdtemp(prefix="nexus-phase5-root2-"))
    rt2 = NexusRuntime.boot(root2, model_provider=ScriptedProvider([]))
    runner.check(
        "second boot: master seeded exactly once (open roster survives)",
        len([a for a in rt2.agent_registry.list_agents()
             if a.id == MASTER_AGENT_ID]) == 1,
    )
    cfg = rt2.config.agents
    runner.check(
        "agents config: the §6 additive keys parse with defaults",
        cfg.loop_max_turns == 8 and cfg.master_repair_limit == 2
        and cfg.message_log_enabled and cfg.max_parallel == 3,
    )
    rt2.shutdown()

    disabled_root = Path(tempfile.mkdtemp(prefix="nexus-phase5-off-"))
    config_dir = disabled_root / "config" / "agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "agents.toml").write_text(
        "[agents]\nmaster_agent_enabled = false\n", encoding="utf-8"
    )
    rt3 = NexusRuntime.boot(disabled_root, model_provider=ScriptedProvider([]))
    runner.check(
        "agents.master_agent_enabled=false → master-less runtime (§6.3 opt-out)",
        rt3.master_agent is None and isinstance(rt3.agent_registry, AgentRegistry),
    )
    rt3.shutdown()

    try:
        build_section("agents", {"loop_max_turns": 0})
        ok = False
    except Exception:
        ok = True
    runner.check("config validation rejects loop_max_turns=0", ok)

    # ---- regression: Phases 1–4 harnesses stay green --------------------
    for phase, phrase in (("phase01", "98/98"), ("phase02", "143/143"),
                          ("phase03", "104/104"), ("phase04", "106/106")):
        proc = subprocess.run(
            [sys.executable,
             str(REPO_ROOT / "tests" / phase / "verify_exit_criteria.py")],
            capture_output=True, text=True, timeout=600,
            cwd=str(REPO_ROOT),
        )
        runner.check(
            f"{phase} harness still green ({phrase})",
            proc.returncode == 0 and phrase in proc.stdout,
        )


# ---------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=str, default=None,
                        help="runtime root for the integration section")
    args = parser.parse_args()

    runner = Runner()
    print("PHASE 5 — AGENT RUNTIME (Final Build Plan §6)")
    print()

    base = Path(tempfile.mkdtemp(prefix="nexus-phase5-"))
    root = Path(args.root) if args.root else Path(
        tempfile.mkdtemp(prefix="nexus-phase5-root-"))

    section_a(runner)
    print()
    section_b(runner, base)
    print()
    section_c(runner, base)
    print()
    section_d(runner, base)
    print()
    section_e(runner, base)
    print()
    section_f(runner, root)

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
